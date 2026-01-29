import json
import subprocess
from pathlib import Path

from packaging.utils import canonicalize_name

from uvbump.core import (
	NpmDependencyOrigin,
	Package,
	UnsupportedPackageTypeError,
)


def _normalize_spec(spec: str) -> str:
	for op in ('^', '~', '>=', '<=', '>', '<', '='):
		if spec.startswith(op):
			return spec[len(op) :]

	return spec


def _parse_spec(spec: str) -> tuple[str | None, str | None]:
	if not spec:
		return None, None
	if ' ' in spec or '||' in spec:
		return None, None
	for op in ('^', '~', '>=', '<=', '>', '<', '='):
		if spec.startswith(op):
			version = spec[len(op) :].strip()
			return op, version or None
	return '', spec.strip() or None


class NpmProject:
	def __init__(self, root_path: Path) -> None:
		self.root_path = root_path

	@property
	def package_json_path(self) -> Path:
		return self.root_path / 'package.json'

	def dependency_entries(self) -> list[tuple[str, str, str]]:
		if not self.package_json_path.exists():
			message = f'package.json not found at: {self.package_json_path}'
			raise FileNotFoundError(message)

		data = json.loads(self.package_json_path.read_text())
		entries: list[tuple[str, str, str]] = []

		for key in (
			'dependencies',
			'devDependencies',
			'peerDependencies',
			'optionalDependencies',
		):
			for name, spec in (data.get(key, {}) or {}).items():
				entries.append((key, name, spec))

		return entries

	def packages(self) -> list[Package]:
		packages: list[Package] = []
		for section, name, spec in self.dependency_entries():
			if spec.startswith(('git+', 'file:', 'http:', 'https:')):
				message = f'Unsupported non-registry spec for {name}: {spec}'
				raise UnsupportedPackageTypeError(message)
			project_version = _normalize_spec(spec) or '-'
			operator, version = _parse_spec(spec)
			packages.append(
				Package(
					name=canonicalize_name(name),
					display_name=name,
					project_version=project_version,
					primary_operator=operator,
					primary_version=version,
					origin=NpmDependencyOrigin(
						package_json_path=self.package_json_path,
						section=section,
						name=name,
						raw_spec=spec,
					),
				)
			)
		return packages


def set_installed_versions_npm(packages: list[Package], root: Path, timeout: int) -> None:
	package_map = {}
	for package in packages:
		package_map.setdefault(package.name, []).append(package)
	args = ['npm', 'ls', '--depth=0', '--json']

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
		return

	data = json.loads(result.stdout)
	installed = data.get('dependencies', {})
	for name, info in installed.items():
		for package in package_map.get(canonicalize_name(name), []):
			package.installed_version = info.get('version')


def set_newest_versions_npm(packages: list[Package], root: Path, timeout: int) -> None:
	cache = {}
	for package in packages:
		if package.name in cache:
			package.newest_version = cache[package.name]
			continue

		args = ['npm', 'view', package.name, 'version']
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

		newest = result.stdout.strip()
		cache[package.name] = newest
		package.newest_version = newest


def collect_upgrade_entries_npm(
	packages: list[Package],
	include_up_to_date: bool = False,
) -> tuple[list[tuple[NpmDependencyOrigin, Package]], list[str]]:
	entries = []
	skipped = []

	for package in packages:
		origin = package.origin
		if not isinstance(origin, NpmDependencyOrigin):
			continue

		if not package.newest_version:
			skipped.append(f'{origin.package_json_path}: {origin.raw_spec} (missing newest version)')
			continue

		if package.primary_operator is None or not package.primary_version:
			skipped.append(f'{origin.package_json_path}: {origin.raw_spec} (unsupported npm spec)')
			continue

		if not include_up_to_date and package.primary_version == package.newest_version:
			continue

		entries.append((origin, package))

	return entries, skipped


def upgrade_project_versions_npm(
	entries: list[tuple[NpmDependencyOrigin, Package]],
	dry_run: bool = False,
) -> tuple[int, list[str]]:
	updates_by_file = {}
	for origin, package in entries:
		updates_by_file.setdefault(origin.package_json_path, []).append((origin, package))

	updated = 0
	skipped = []

	for path, items in updates_by_file.items():
		if not path.exists():
			skipped.append(f'{path}: file missing')
			continue

		data = json.loads(path.read_text())
		changed = False

		for origin, package in items:
			section_data = data.get(origin.section)
			if not isinstance(section_data, dict):
				skipped.append(f'{path}: {origin.raw_spec} (missing section {origin.section})')
				continue

			if origin.name not in section_data:
				skipped.append(f'{path}: {origin.raw_spec} (missing dependency)')
				continue

			operator = package.primary_operator or ''
			version = package.newest_version or ''
			section_data[origin.name] = f'{operator}{version}'
			updated += 1
			changed = True

		if changed and not dry_run:
			path.write_text(json.dumps(data, indent=2) + '\n')

	return updated, skipped
