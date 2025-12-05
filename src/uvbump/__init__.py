"""CLI to report out-of-date dependency pins in uv workspaces."""

from __future__ import annotations

import argparse
import logging
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from collections.abc import Iterable

__version__ = '0.1.0'
logger = logging.getLogger(__name__)

_MIN_LINES_FOR_VERSIONS = 2


class UnknownPackageVersionSchemeError(Exception):
	"""Raised when a dependency specifier format is not recognized."""


class UnsupportedPackageTypeError(Exception):
	"""Raised when dependency extras are encountered (unsupported)."""

	def __init__(self) -> None:
		"""Initialise the exception with a friendly message."""
		message = 'Cannot support package extras'
		super().__init__(message)


@dataclass
class Package:
	"""Represents a dependency and its known versions."""

	name: str
	project_version: str
	installed_version: str | None = None
	newest_version: str | None = None


def _read_toml(path: Path) -> dict:
	"""Load TOML from *path* into a dictionary."""
	with path.open('rb') as handle:
		return tomllib.load(handle)


def _collect_dependency_listings(data: dict) -> list[str]:
	"""Return dependency spec strings from a pyproject dictionary."""
	listings: list[str] = []
	project = data.get('project', {})
	listings.extend(project.get('dependencies', []) or [])
	for deps in project.get('dependency-groups', {}).values():
		listings.extend(deps or [])
	for deps in data.get('dependency-groups', {}).values():
		listings.extend(deps or [])
	return listings


class UVProject:
	"""Represents a uv-managed project (optionally a workspace)."""

	def __init__(self, root_path: Path) -> None:
		"""Create a UVProject rooted at *root_path*."""
		self.root_path = root_path

	@property
	def pyproject_path(self) -> Path:
		"""Return the path to the project's pyproject.toml."""
		return self.root_path / 'pyproject.toml'

	def dependency_listings(self) -> list[str]:
		"""Collect dependency specs from the root and workspace members."""
		if not self.pyproject_path.exists():
			message = f'pyproject.toml not found at: {self.pyproject_path}'
			raise FileNotFoundError(message)

		root_data = _read_toml(self.pyproject_path)
		listings = _collect_dependency_listings(root_data)

		workspace = root_data.get('tool', {}).get('uv', {}).get('workspace', {})
		for member in workspace.get('members', []) or []:
			member_pyproject = (self.root_path / member) / 'pyproject.toml'
			if member_pyproject.exists():
				member_data = _read_toml(member_pyproject)
				listings.extend(_collect_dependency_listings(member_data))

		seen: set[str] = set()
		unique_listings: list[str] = []
		for listing in listings:
			if listing not in seen:
				unique_listings.append(listing)
				seen.add(listing)

		return unique_listings


def split_package_from_version(listing: str) -> tuple[str, str]:
	"""Split ``pkg>=1.2`` style strings into (name, version)."""
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


def set_project_versions(packages: list[Package], dependency_listings: Iterable[str]) -> None:
	"""Populate Package objects from dependency spec strings."""
	for package_listing in dependency_listings:
		package_name, version = split_package_from_version(package_listing)
		packages.append(Package(package_name, version))


def validate_package_extras(packages: list[Package]) -> None:
	"""Abort if any dependency uses extras (unsupported)."""
	unsupported_packages = [p for p in packages if '[' in p.name]

	for package in unsupported_packages:
		logger.error('Unsupported package with extra: %s', package.name)

	if unsupported_packages:
		raise UnsupportedPackageTypeError


def set_installed_versions(packages: list[Package], root: Path, timeout: int) -> None:
	"""Fill installed versions by running ``uv export`` inside *root*."""
	package_name_to_package_map = {p.name: p for p in packages}
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
	except FileNotFoundError:
		logger.exception('`uv` command not found. Install uv and ensure it is on PATH.')
		return
	except subprocess.TimeoutExpired:
		logger.exception('`uv export` timed out.')
		return
	except subprocess.CalledProcessError as exc:
		logger.exception('`uv export` failed: %s', exc.stderr)
		return

	for line in result.stdout.splitlines():
		if line.startswith('#'):
			continue
		cleaned_line = line.split(';')[0].strip()
		if '==' not in cleaned_line:
			continue
		package_name, version = cleaned_line.split('==')
		package = package_name_to_package_map.get(package_name)
		if package:
			package.installed_version = version


def set_newest_versions(packages: list[Package], timeout: int) -> None:
	"""Fill newest versions from PyPI using ``uvx pip index versions``."""
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
		except FileNotFoundError:
			logger.exception('`uvx` command not found. Install uv and ensure it is on PATH.')
			return
		except subprocess.TimeoutExpired:
			logger.exception('`uvx pip index versions %s` timed out.', package.name)
			continue
		except subprocess.CalledProcessError as exc:
			logger.exception('`uvx pip index versions %s` failed: %s', package.name, exc.stderr)
			continue

		lines = result.stdout.splitlines()
		if len(lines) < _MIN_LINES_FOR_VERSIONS or 'Available versions:' not in lines[1]:
			continue
		versions = lines[1].replace('Available versions:', '').strip().split(',')
		if versions:
			package.newest_version = versions[0].strip()


def display_package_information(packages: list[Package]) -> None:
	"""Log two tables: outdated packages and bumpable packages."""
	packages_out_of_date: list[Package] = []
	packages_can_be_bumped: list[Package] = []

	for package in packages:
		if not package.installed_version:
			continue
		if package.installed_version != package.project_version:
			packages_can_be_bumped.append(package)
		if package.newest_version and package.newest_version != package.project_version:
			packages_out_of_date.append(package)

	if packages_out_of_date:
		logger.info('Packages out of date:')
		header = '{:<50}{:<30}{:<30}{:<30}{}'.format(
			'Package Name',
			'Installed Version',
			'Project Version',
			'Newest Version',
			'Suggested Action',
		)
		logger.info(header)
		suggested_action = 'Update package version'
		for package in packages_out_of_date:
			logger.info(
				'%s',
				f'{package.name:<50}{package.installed_version:<30}{package.project_version:<30}{package.newest_version:<30}{suggested_action}',
			)

	if packages_out_of_date and packages_can_be_bumped:
		logger.info('')

	if packages_can_be_bumped:
		logger.info('Packages can be bumped:')
		header = '{:<50}{:<30}{:<30}{:<30}{}'.format(
			'Package Name',
			'Installed Version',
			'Project Version',
			'Newest Version',
			'Suggested Action',
		)
		logger.info(header)
		suggested_action = 'Bump package version in project specification'
		for package in packages_can_be_bumped:
			logger.info(
				'%s',
				f'{package.name:<50}{package.installed_version:<30}{package.project_version:<30}{package.newest_version:<30}{suggested_action}',
			)


def _build_arg_parser() -> argparse.ArgumentParser:
	"""Construct the argument parser for the CLI."""
	parser = argparse.ArgumentParser(
		description='Inspect dependency versions for a uv project or workspace.',
	)
	parser.add_argument(
		'--root',
		type=Path,
		default=Path.cwd(),
		help='Path to the directory containing pyproject.toml. Default: current working directory.',
	)
	parser.add_argument(
		'--timeout',
		type=int,
		default=20,
		help='Subprocess timeout in seconds for uv/uvx calls. Default: 20.',
	)
	return parser


def main(argv: list[str] | None = None) -> int:
	"""Entry point for the `uvbump` console script."""
	logging.basicConfig(level=logging.INFO, format='%(message)s')
	args = _build_arg_parser().parse_args(argv)
	project = UVProject(args.root)

	try:
		dependency_listings = project.dependency_listings()
	except FileNotFoundError:
		logger.exception('pyproject.toml not found')
		return 2

	packages: list[Package] = []
	set_project_versions(packages, dependency_listings)

	try:
		validate_package_extras(packages)
	except UnsupportedPackageTypeError:
		return 3

	set_installed_versions(packages, args.root, args.timeout)
	set_newest_versions(packages, args.timeout)
	display_package_information(packages)
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
