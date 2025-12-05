from __future__ import annotations

import argparse
import json
import logging
import subprocess
import tomllib
from pathlib import Path

from uvbump.core import (
	configure_logging,
	display_package_information,
	Package,
)

__version__ = '0.1.0'
logger = logging.getLogger(__name__)
_MIN_LINES_FOR_VERSIONS = 2


class UnknownPackageVersionSchemeError(Exception):
	pass


class UnsupportedPackageTypeError(Exception):
	def __init__(self) -> None:
		super().__init__('Cannot support package extras')


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


class NpmProject:
	def __init__(self, root_path: Path) -> None:
		self.root_path = root_path

	@property
	def package_json_path(self) -> Path:
		return self.root_path / 'package.json'

	def dependency_specs(self) -> dict[str, str]:
		if not self.package_json_path.exists():
			message = f'package.json not found at: {self.package_json_path}'
			raise FileNotFoundError(message)

		data = json.loads(self.package_json_path.read_text())
		listings: dict[str, str] = {}
		for key in (
			'dependencies',
			'devDependencies',
			'peerDependencies',
			'optionalDependencies',
		):
			listings.update(data.get(key, {}))

		return listings

	def packages(self) -> list[Package]:
		packages: list[Package] = []
		for name, spec in self.dependency_specs().items():
			if spec.startswith(('git+', 'file:', 'http:', 'https:')):
				message = f'Unsupported non-registry spec for {name}: {spec}'
				raise UnsupportedPackageTypeError(message)
			packages.append(Package(name=name, project_version=_normalize_spec(spec)))
		return packages


def _normalize_spec(spec: str) -> str:
	for op in ('^', '~', '>=', '<=', '>', '<', '='):
		if spec.startswith(op):
			return spec[len(op) :]
	return spec


def _collect_dependency_listings(data: dict) -> list[str]:
	listings: list[str] = []
	project = data.get('project', {})
	listings.extend(project.get('dependencies', []) or [])
	for deps in project.get('dependency-groups', {}).values():
		listings.extend(deps or [])
	for deps in data.get('dependency-groups', {}).values():
		listings.extend(deps or [])
	return listings


def validate_package_extras(packages: list[Package]) -> None:
	extras = [p for p in packages if '[' in p.name]
	for package in extras:
		logger.error('Unsupported package with extra: %s', package.name)
	if extras:
		raise UnsupportedPackageTypeError


def set_installed_versions_uv(packages: list[Package], root: Path, timeout: int) -> None:
	package_map = {p.name: p for p in packages}
	args = [
		'uv',
		'export',
		'--locked',
		'--all-packages',
		'--all-groups',
		'--format',
		'requirements-txt',
		'--no-hashes',
	]

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
		logger.exception('`uv export` failed')
		return

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
			logger.exception('`uvx pip index versions %s` failed', package.name)
			continue

		lines = result.stdout.splitlines()
		if len(lines) < _MIN_LINES_FOR_VERSIONS or 'Available versions:' not in lines[1]:
			continue
		versions = lines[1].replace('Available versions:', '').strip().split(',')
		if versions:
			package.newest_version = versions[0].strip()


def set_installed_versions_npm(packages: list[Package], root: Path, timeout: int) -> None:
	package_map = {p.name: p for p in packages}
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
		logger.exception('`npm ls` failed')
		return

	data = json.loads(result.stdout)
	installed = data.get('dependencies', {})
	for name, info in installed.items():
		package = package_map.get(name)
		if package:
			package.installed_version = info.get('version')


def set_newest_versions_npm(packages: list[Package], root: Path, timeout: int) -> None:
	for package in packages:
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
			logger.exception('`npm view %s version` failed', package.name)
			continue

		package.newest_version = result.stdout.strip()


def _build_arg_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description='Inspect dependency versions for uv or npm projects.')
	parser.add_argument(
		'--root',
		type=Path,
		default=Path.cwd(),
		help='Path to the project root (pyproject.toml or package.json).',
	)
	parser.add_argument(
		'--kind',
		choices=['uv', 'npm'],
		default='uv',
		help='Project type to inspect (uv or npm).',
	)
	parser.add_argument(
		'--timeout',
		type=int,
		default=20,
		help='Subprocess timeout in seconds for uv/uvx/npm calls.',
	)
	return parser


def main(argv: list[str] | None = None) -> int:
	configure_logging()
	args = _build_arg_parser().parse_args(argv)

	if args.kind == 'uv':
		project = UvProject(args.root)
		try:
			packages = project.packages()
		except FileNotFoundError:
			logger.exception('pyproject.toml not found')
			return 2
		try:
			validate_package_extras(packages)
		except UnsupportedPackageTypeError:
			return 3
		set_installed_versions_uv(packages, args.root, args.timeout)
		set_newest_versions_uv(packages, args.timeout)
	else:
		project = NpmProject(args.root)
		try:
			packages = project.packages()
		except FileNotFoundError:
			logger.exception('package.json not found')
			return 2
		set_installed_versions_npm(packages, args.root, args.timeout)
		set_newest_versions_npm(packages, args.root, args.timeout)

	display_package_information(
		packages,
		logger=logger,
		column_widths=(50, 30, 30, 30),
		require_newest_version=True,
	)
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
