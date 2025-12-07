import argparse
import logging
import sys
from pathlib import Path

from uvbump.core import configure_logging, display_package_information
from uvbump.npm import (
	NpmProject,
	set_installed_versions_npm,
	set_newest_versions_npm,
)
from uvbump.uv import (
	set_installed_versions_uv,
	set_newest_versions_uv,
	UvProject,
)

__version__ = '0.1.0'
logger = logging.getLogger(__name__)


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

		# try:
		# 	validate_package_extras(packages)
		#
		# except UnsupportedPackageTypeError:
		# 	return 3

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
	raise SystemExit(main(sys.argv[1:]))
