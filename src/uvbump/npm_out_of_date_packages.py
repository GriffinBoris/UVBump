"""Utility to inspect npm package versions (experimental)."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
CURRENT_DIRECTORY = Path(__file__).parent


class UnsupportedPackageTypeError(Exception):
	"""Raised when a non-registry npm spec is encountered."""

	def __init__(self, message: str | None = None) -> None:
		"""Create the exception with an optional message."""
		super().__init__(message or 'Unsupported npm package specification')


@dataclass
class Package:
	"""Represents an npm dependency and its versions."""

	name: str
	project_version: str
	installed_version: str | None = None
	newest_version: str | None = None


def _normalize_spec(spec: str) -> str:
	"""Remove leading range markers from an npm semver spec."""
	for op in ('^', '~', '>=', '<=', '>', '<', '='):
		if spec.startswith(op):
			return spec[len(op) :]
	return spec


def set_project_versions(packages: list[Package]) -> None:
	"""Load project specs from package.json into Package objects."""
	package_json = CURRENT_DIRECTORY / 'package.json'
	with package_json.open() as handle:
		data = json.load(handle)

	all_package_listings: dict[str, str] = {}
	for key in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
		all_package_listings.update(data.get(key, {}))

	for name, spec in all_package_listings.items():
		if spec.startswith(('git+', 'file:', 'http:', 'https:')):
			message = f'Unsupported non-registry spec for {name}: {spec}'
			raise UnsupportedPackageTypeError(message)
		packages.append(Package(name=name, project_version=_normalize_spec(spec)))


def set_installed_versions(packages: list[Package]) -> None:
	"""Populate installed versions using ``npm ls`` output."""
	package_name_to_package_map = {p.name: p for p in packages}
	args = ['npm', 'ls', '--depth=0', '--json']

	try:
		result = subprocess.run(  # noqa: S603
			args,
			check=True,
			capture_output=True,
			text=True,
			cwd=CURRENT_DIRECTORY,
			timeout=10,
		)
	except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
		logger.exception('`npm ls` failed')
		return

	data = json.loads(result.stdout)
	installed = data.get('dependencies', {})
	for name, info in installed.items():
		package = package_name_to_package_map.get(name)
		if package:
			package.installed_version = info.get('version')


def set_newest_versions(packages: list[Package]) -> None:
	"""Populate newest versions via ``npm view <pkg> version``."""
	for package in packages:
		args = ['npm', 'view', package.name, 'version']
		try:
			result = subprocess.run(  # noqa: S603
				args,
				check=True,
				capture_output=True,
				text=True,
				cwd=CURRENT_DIRECTORY,
				timeout=10,
			)
		except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
			logger.exception('`npm view %s version` failed', package.name)
			continue

		package.newest_version = result.stdout.strip()


def display_package_information(packages: list[Package]) -> None:
	"""Log tables for out-of-date and bumpable npm packages."""
	packages_out_of_date: list[Package] = []
	packages_can_be_bumped: list[Package] = []

	for package in packages:
		if not package.installed_version:
			continue
		if package.installed_version != package.project_version:
			packages_can_be_bumped.append(package)
		if package.newest_version != package.project_version:
			packages_out_of_date.append(package)

	if packages_out_of_date:
		logger.info('Packages out of date:')
		header = '{:<40}{:<25}{:<25}{:<25}{}'.format(
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
				f'{package.name:<40}{package.installed_version:<25}{package.project_version:<25}{package.newest_version:<25}{suggested_action}',
			)

	if packages_out_of_date and packages_can_be_bumped:
		logger.info('')

	if packages_can_be_bumped:
		logger.info('Packages can be bumped:')
		header = '{:<40}{:<25}{:<25}{:<25}{}'.format(
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
				f'{package.name:<40}{package.installed_version:<25}{package.project_version:<25}{package.newest_version:<25}{suggested_action}',
			)


def main() -> int:
	"""Entry point for the npm helper."""
	logging.basicConfig(level=logging.INFO, format='%(message)s')
	packages: list[Package] = []
	set_project_versions(packages)
	set_installed_versions(packages)
	set_newest_versions(packages)
	display_package_information(packages)
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
