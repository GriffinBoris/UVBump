import argparse
import logging
import sys
from pathlib import Path

from uvbump import __version__
from uvbump.core import (
	configure_logging,
	display_package_information,
	Package,
)
from uvbump.npm import (
	collect_upgrade_entries_npm,
	NpmProject,
	set_installed_versions_npm,
	set_newest_versions_npm,
	upgrade_project_versions_npm,
)
from uvbump.uv import (
	collect_upgrade_entries,
	set_installed_versions_uv,
	set_newest_versions_uv,
	upgrade_project_versions,
	UvProject,
)

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
	parser.add_argument('--version', action='version', version=f'uvbump {__version__}')
	parser.add_argument(
		'--upgrade',
		action='store_true',
		help='Rewrite dependency versions to newest available versions.',
	)
	parser.add_argument(
		'--interactive',
		action='store_true',
		help='Interactively choose which dependencies to upgrade.',
	)
	parser.add_argument(
		'--dry-run',
		action='store_true',
		help='Preview upgrade changes without writing files.',
	)
	return parser


def _load_packages(args: argparse.Namespace) -> tuple[list[Package], int | None]:
	if args.kind == 'uv':
		project = UvProject(args.root)
		try:
			packages = project.packages()
		except FileNotFoundError:
			logger.exception('pyproject.toml not found')
			return [], 2

		set_installed_versions_uv(packages, args.root, args.timeout)
		set_newest_versions_uv(packages, args.timeout)
		return packages, None

	project = NpmProject(args.root)
	try:
		packages = project.packages()
	except FileNotFoundError:
		logger.exception('package.json not found')
		return [], 2

	set_installed_versions_npm(packages, args.root, args.timeout)
	set_newest_versions_npm(packages, args.root, args.timeout)
	return packages, None


def _choose_entries_interactive(entries) -> list:
	logger.info('')
	logger.info('Upgradable entries:')
	for idx, (origin, package) in enumerate(entries, start=1):
		logger.info('%s. %s (%s -> %s)', idx, package.display_name, origin.raw_spec, package.newest_version)

	response = input('Select entries to upgrade [a=all, n=none, 1,2,3]: ').strip().lower()
	if response in ('', 'a', 'all'):
		return entries
	if response in ('n', 'none'):
		logger.info('No entries selected for upgrade.')
		return []

	chosen: set[int] = set()
	for raw_part in response.split(','):
		part = raw_part.strip()
		if not part:
			continue
		try:
			value = int(part)
		except ValueError:
			continue
		if 1 <= value <= len(entries):
			chosen.add(value)

	selected_entries = [entry for idx, entry in enumerate(entries, start=1) if idx in chosen]
	if not selected_entries:
		logger.info('No valid entries selected for upgrade.')
		return []

	if len(selected_entries) != len(entries):
		logger.info('Not selected: %s entries.', len(entries) - len(selected_entries))
	return selected_entries


def _handle_upgrade(args: argparse.Namespace, packages: list[Package]) -> int:
	if args.kind == 'uv':
		entries, skipped = collect_upgrade_entries(packages)

		def upgrade(selected) -> tuple[int, list[str]]:
			return upgrade_project_versions(selected, dry_run=args.dry_run)
	else:
		entries, skipped = collect_upgrade_entries_npm(packages)

		def upgrade(selected) -> tuple[int, list[str]]:
			return upgrade_project_versions_npm(selected, dry_run=args.dry_run)

	if not entries:
		logger.info('No upgradable dependency entries found.')
		return 0

	if args.interactive:
		entries = _choose_entries_interactive(entries)
		if not entries:
			return 0

	updated, upgrade_skipped = upgrade(entries)
	skipped.extend(upgrade_skipped)
	logger.info('')
	label = 'Planned' if args.dry_run else 'Updated'
	logger.info('%s %s dependency entries.', label, updated)
	if skipped:
		logger.info('Skipped entries:')
		for entry in skipped:
			logger.info('- %s', entry)
	return 0


def main(argv: list[str] | None = None) -> int:
	configure_logging()
	args = _build_arg_parser().parse_args(argv)

	packages, error_code = _load_packages(args)
	if error_code is not None:
		return error_code

	display_package_information(
		packages,
		logger=logger,
		column_widths=(50, 30, 30, 30),
		require_newest_version=True,
	)

	if not args.upgrade:
		return 0

	return _handle_upgrade(args, packages)


if __name__ == '__main__':
	raise SystemExit(main(sys.argv[1:]))
