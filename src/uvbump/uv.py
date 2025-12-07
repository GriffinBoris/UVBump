import json
import subprocess
import sys
import tomllib
from pathlib import Path

from uvbump.core import (
	Package,
	UnknownPackageVersionSchemeError,
	UnsupportedPackageTypeError,
)

_MIN_LINES_FOR_VERSIONS = 2


def split_package_from_version(listing: str) -> tuple[str, str]:
	cleaned_listing = listing.split(',')[0]

	if '>=' in cleaned_listing:
		split_by = '>='
	elif '<=' in cleaned_listing:
		split_by = '<='
	elif '==' in cleaned_listing:
		split_by = '=='
	elif '<' in cleaned_listing:
		split_by = '<'
	elif '>' in cleaned_listing:
		split_by = '>'
	else:
		message = f'Unknown package versioning scheme for package listing: {listing}'
		raise UnknownPackageVersionSchemeError(message)

	package_name, version = cleaned_listing.split(split_by)
	return package_name, version


def _collect_dependency_listings(data: dict) -> list[str]:
	listings: list[str] = []
	project = data.get('project', {})
	listings.extend(project.get('dependencies', []) or [])

	for deps in project.get('dependency-groups', {}).values():
		listings.extend(deps or [])
	for deps in data.get('dependency-groups', {}).values():
		listings.extend(deps or [])

	return listings


class UvProject:
	def __init__(self, root_path: Path) -> None:
		self.root_path = root_path

	@property
	def pyproject_path(self) -> Path:
		return self.root_path / 'pyproject.toml'

	def dependency_listings(self) -> list[str]:
		if not self.pyproject_path.exists():
			message = f'pyproject.toml not found at: {self.pyproject_path}'
			raise FileNotFoundError(message)

		root_data = tomllib.loads(self.pyproject_path.read_text())
		listings = _collect_dependency_listings(root_data)

		workspace = root_data.get('tool', {}).get('uv', {}).get('workspace', {})
		for member in workspace.get('members', []) or []:
			member_pyproject = (self.root_path / member) / 'pyproject.toml'
			if member_pyproject.exists():
				member_data = tomllib.loads(member_pyproject.read_text())
				listings.extend(_collect_dependency_listings(member_data))

		unique: list[str] = []
		seen: set[str] = set()
		for item in listings:
			if item not in seen:
				unique.append(item)
				seen.add(item)

		return unique

	def packages(self) -> list[Package]:
		return [Package(*split_package_from_version(spec)) for spec in self.dependency_listings()]


def validate_package_extras(packages: list[Package]) -> None:
	extras = [p for p in packages if '[' in p.name]
	if extras:
		message = 'Extras are not supported'
		raise UnsupportedPackageTypeError(message)


def set_installed_versions_uv(packages: list[Package], root: Path, timeout: int) -> None:
	package_map = {p.name: p for p in packages}
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
			package = package_map.get(name)
			if package:
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
			package = package_map.get(name)
			if package:
				package.installed_version = version

		if any(package.installed_version for package in packages):
			return


def set_newest_versions_uv(packages: list[Package], timeout: int) -> None:
	for package in packages:
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
			package.newest_version = versions[0].strip()
