import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from tomlkit import parse

from uvbump.core import (
	DependencyOrigin,
	Package,
	UnknownPackageVersionSchemeError,
)

_MIN_LINES_FOR_VERSIONS = 2
_SPEC_PATTERN = re.compile(r'(~=|==|!=|<=|>=|<|>)\s*([^,]+)')


@dataclass
class DependencyEntry:
	requirement: Requirement
	raw_spec: str
	pyproject_path: Path
	path_keys: tuple[str, ...]
	index: int


def _extract_primary_spec(spec: str) -> tuple[str | None, str | None]:
	base = spec.split(';', 1)[0].strip()
	match = _SPEC_PATTERN.search(base)
	if not match:
		return None, None
	return match.group(1), match.group(2).strip()


def _parse_requirement(spec: str) -> Requirement:
	try:
		return Requirement(spec)
	except InvalidRequirement as exc:
		message = f'Unknown package versioning scheme for package listing: {spec}'
		raise UnknownPackageVersionSchemeError(message) from exc


def _collect_dependency_entries(data: dict, pyproject_path: Path) -> list[DependencyEntry]:
	entries: list[DependencyEntry] = []
	project = data.get('project', {})
	for index, spec in enumerate(project.get('dependencies', []) or []):
		requirement = _parse_requirement(spec)
		entries.append(DependencyEntry(requirement, spec, pyproject_path, ('project', 'dependencies'), index))

	for group_name, deps in (project.get('dependency-groups', {}) or {}).items():
		for index, spec in enumerate(deps or []):
			requirement = _parse_requirement(spec)
			entries.append(DependencyEntry(requirement, spec, pyproject_path, ('project', 'dependency-groups', group_name), index))

	for group_name, deps in (data.get('dependency-groups', {}) or {}).items():
		for index, spec in enumerate(deps or []):
			requirement = _parse_requirement(spec)
			entries.append(DependencyEntry(requirement, spec, pyproject_path, ('dependency-groups', group_name), index))

	return entries


class UvProject:
	def __init__(self, root_path: Path) -> None:
		self.root_path = root_path

	@property
	def pyproject_path(self) -> Path:
		return self.root_path / 'pyproject.toml'

	def dependency_entries(self) -> list[DependencyEntry]:
		if not self.pyproject_path.exists():
			message = f'pyproject.toml not found at: {self.pyproject_path}'
			raise FileNotFoundError(message)

		root_data = tomllib.loads(self.pyproject_path.read_text())
		listings = _collect_dependency_entries(root_data, self.pyproject_path)

		workspace = root_data.get('tool', {}).get('uv', {}).get('workspace', {})
		for member in workspace.get('members', []) or []:
			member_pyproject = (self.root_path / member) / 'pyproject.toml'
			if member_pyproject.exists():
				member_data = tomllib.loads(member_pyproject.read_text())
				listings.extend(_collect_dependency_entries(member_data, member_pyproject))

		return listings

	def packages(self) -> list[Package]:
		packages: list[Package] = []
		for entry in self.dependency_entries():
			requirement = entry.requirement
			operator, version = _extract_primary_spec(entry.raw_spec)
			pinned_version = version if operator == '==' else None
			project_version = pinned_version or (str(requirement.specifier) if requirement.specifier else '-')

			package = Package(
				name=canonicalize_name(requirement.name),
				display_name=requirement.name,
				project_version=project_version,
				primary_operator=operator,
				primary_version=version,
				pinned_version=pinned_version,
				origin=DependencyOrigin(
					pyproject_path=entry.pyproject_path,
					path_keys=entry.path_keys,
					index=entry.index,
					raw_spec=entry.raw_spec,
				),
			)
			packages.append(package)

		return packages


def set_installed_versions_uv(packages: list[Package], root: Path, timeout: int) -> None:
	package_map: dict[str, list[Package]] = {}
	for package in packages:
		package_map.setdefault(package.name, []).append(package)
	commands = [
		[
			'uv',
			'export',
			'--locked',
			'--all-packages',
			'--all-groups',
			'--format',
			'requirements-txt',
			'--no-hashes',
		],
	]

	for args in commands:
		try:
			result = subprocess.run(  # noqa: S603
				args,
				check=True,
				capture_output=True,
				text=True,
				cwd=root,
				timeout=timeout,
			)
		except (FileNotFoundError, subprocess.SubprocessError):
			continue

		for line in result.stdout.splitlines():
			if line.startswith('#'):
				continue

			cleaned = line.split(';')[0].strip()
			if '==' not in cleaned:
				continue

			name, version = cleaned.split('==')
			for package in package_map.get(canonicalize_name(name), []):
				package.installed_version = version

	if any(package.installed_version for package in packages):
		return

	fallback_commands = [
		['uv', 'pip', 'list', '--format', 'json'],
		[sys.executable, '-m', 'pip', 'list', '--format', 'json'],
	]

	for args in fallback_commands:
		try:
			result = subprocess.run(  # noqa: S603
				args,
				check=True,
				capture_output=True,
				text=True,
				cwd=root,
				timeout=timeout,
			)
		except (FileNotFoundError, subprocess.SubprocessError):
			continue

		try:
			installed = json.loads(result.stdout)
		except json.JSONDecodeError:
			continue

		for info in installed:
			name = info.get('name')
			version = info.get('version')
			if not name or not version:
				continue

			for package in package_map.get(canonicalize_name(name), []):
				package.installed_version = version

		if any(package.installed_version for package in packages):
			return


def set_newest_versions_uv(packages: list[Package], timeout: int) -> None:
	cache: dict[str, str | None] = {}
	for package in packages:
		if package.name in cache:
			package.newest_version = cache[package.name]
			continue

		args = ['uvx', 'pip', 'index', 'versions', package.name]
		try:
			result = subprocess.run(  # noqa: S603
				args,
				check=True,
				capture_output=True,
				text=True,
				timeout=timeout,
			)
		except (FileNotFoundError, subprocess.SubprocessError):
			continue

		lines = result.stdout.splitlines()
		if len(lines) < _MIN_LINES_FOR_VERSIONS or 'Available versions:' not in lines[1]:
			continue

		versions = lines[1].replace('Available versions:', '').strip().split(',')
		if versions:
			newest = versions[0].strip()
			cache[package.name] = newest
			package.newest_version = newest
		else:
			cache[package.name] = None
			package.newest_version = None


def _format_requirement_with_version(requirement: Requirement, operator: str, version: str) -> str:
	name = requirement.name
	if requirement.extras:
		name = f'{name}[{",".join(sorted(requirement.extras))}]'
	marker = f' ; {requirement.marker}' if requirement.marker else ''
	return f'{name}{operator}{version}{marker}'


def _get_table_node(doc, path_keys: tuple[str, ...]) -> list[str]:
	node = doc
	for key in path_keys:
		node = node[key]
	return node


def collect_upgrade_entries(packages: list[Package]) -> tuple[list[tuple[DependencyOrigin, Package]], list[str]]:
	entries = []
	skipped = []
	unsupported_operators = {'<', '<=', '!='}

	for package in packages:
		if not package.origin or not isinstance(package.origin, DependencyOrigin):
			continue

		if not package.newest_version:
			skipped.append(f'{package.origin.pyproject_path}: {package.origin.raw_spec} (missing newest version)')
			continue

		if not package.primary_operator or not package.primary_version:
			skipped.append(f'{package.origin.pyproject_path}: {package.origin.raw_spec} (no version specifier)')
			continue

		if package.primary_operator in unsupported_operators:
			skipped.append(f'{package.origin.pyproject_path}: {package.origin.raw_spec} (unsupported operator {package.primary_operator})')
			continue

		entries.append((package.origin, package))

	return entries, skipped


def upgrade_project_versions(
	entries: list[tuple[DependencyOrigin, Package]],
	dry_run: bool = False,
) -> tuple[int, list[str]]:
	updates_by_file = {}
	for origin, package in entries:
		updates_by_file.setdefault(origin.pyproject_path, []).append((origin, package))

	updated = 0
	skipped = []

	for path, file_entries in updates_by_file.items():
		if not path.exists():
			skipped.append(f'{path}: file missing')
			continue

		doc = parse(path.read_text())
		changed = False

		for origin, package in file_entries:
			requirement = _parse_requirement(origin.raw_spec)
			operator = package.primary_operator or ''
			version = package.newest_version or ''
			new_spec = _format_requirement_with_version(requirement, operator, version)

			try:
				list_node = _get_table_node(doc, origin.path_keys)
				list_node[origin.index] = new_spec

			except (KeyError, IndexError, TypeError):
				skipped.append(f'{path}: {origin.raw_spec} (could not locate entry)')
				continue

			updated += 1
			changed = True

		if changed and not dry_run:
			path.write_text(doc.as_string())

	return updated, skipped
