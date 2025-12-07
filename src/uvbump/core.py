import logging
from collections.abc import Iterable
from dataclasses import dataclass


class UnknownPackageVersionSchemeError(Exception):
	pass


class UnsupportedPackageTypeError(Exception):
	pass


def configure_logging(level: int = logging.INFO):
	logging.basicConfig(level=level, format='%(message)s')
	return logging.getLogger(__name__)


@dataclass
class Package:
	name: str
	project_version: str
	installed_version: str | None = None
	newest_version: str | None = None


def log_table(title: str, rows: Iterable[Package], column_widths: tuple[int, int, int, int], suggested_action: str, logger) -> None:
	rows = list(rows)
	if not rows:
		return

	def fmt(value: str | None, width: int) -> str:
		text = value if value is not None else '-'
		return f'{text:<{width}}'

	name_w, installed_w, project_w, newest_w = column_widths
	header = f'{"Package Name":<{name_w}}{"Installed Version":<{installed_w}}{"Project Version":<{project_w}}{"Newest Version":<{newest_w}}Suggested Action'

	logger.info(title)
	logger.info(header)

	for package in rows:
		line = fmt(package.name, name_w) + fmt(package.installed_version, installed_w) + fmt(package.project_version, project_w) + fmt(package.newest_version, newest_w) + suggested_action
		logger.info(line)


def display_package_information(
	packages: Iterable[Package],
	logger,
	column_widths: tuple[int, int, int, int] = (50, 30, 30, 30),
	*,
	require_newest_version: bool = True,
) -> None:
	packages = list(packages)
	if not any(package.installed_version for package in packages):
		logger.info('No installed versions detected; ensure your environment is locked/installed so uvbump can compare versions.')
		return

	packages_out_of_date: list[Package] = []
	packages_can_be_bumped: list[Package] = []

	for package in packages:
		if not package.installed_version:
			continue
		if package.installed_version != package.project_version:
			packages_can_be_bumped.append(package)
		newest_differs = package.newest_version != package.project_version
		if require_newest_version:
			newest_differs = bool(package.newest_version) and newest_differs
		if newest_differs:
			packages_out_of_date.append(package)

	log_table('Packages out of date:', packages_out_of_date, column_widths, 'Update package version', logger)

	if packages_out_of_date and packages_can_be_bumped:
		logger.info('')

	log_table(
		'Packages can be bumped:',
		packages_can_be_bumped,
		column_widths,
		'Bump package version in project specification',
		logger,
	)

	if not packages_out_of_date and not packages_can_be_bumped:
		logger.info('All discovered packages match installed and newest versions.')
