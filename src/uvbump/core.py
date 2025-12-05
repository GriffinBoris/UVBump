import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Logger


class UnknownPackageVersionSchemeError(Exception):
	pass


class UnsupportedPackageTypeError(Exception):
	pass


def configure_logging(level: int = logging.INFO) -> Logger:
	logging.basicConfig(level=level, format='%(message)s')
	return logging.getLogger(__name__)


@dataclass
class Package:
	name: str
	project_version: str
	installed_version: str | None = None
	newest_version: str | None = None


def log_table(title: str, rows: Iterable[Package], column_widths: tuple[int, int, int, int], suggested_action: str, logger: Logger) -> None:
	rows = list(rows)
	if not rows:
		return

	header_fmt = f'{{:<{column_widths[0]}}}{{:<{column_widths[1]}}}{{:<{column_widths[2]}}}{{:<{column_widths[3]}}}{{}}'
	logger.info(title)
	logger.info(
		header_fmt,
		'Package Name',
		'Installed Version',
		'Project Version',
		'Newest Version',
		'Suggested Action',
	)
	for package in rows:
		logger.info(
			header_fmt,
			package.name,
			package.installed_version,
			package.project_version,
			package.newest_version,
			suggested_action,
		)


def display_package_information(
	packages: Iterable[Package],
	logger: Logger,
	column_widths: tuple[int, int, int, int] = (50, 30, 30, 30),
	*,
	require_newest_version: bool = True,
) -> None:
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
