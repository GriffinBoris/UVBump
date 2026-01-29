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
		'--group-by',
		choices=['workspace', 'package'],
		default='workspace',
		help='Grouping used in interactive mode (workspace or package).',
	)
	parser.add_argument(
		'--dry-run',
		action='store_true',
		help='Preview upgrade changes without writing files.',
	)
	parser.add_argument(
		'--show-up-to-date',
		action='store_true',
		help='Include dependencies that already match the newest version in upgrade selection.',
	)
	return parser


def _run_with_status(message: str, action) -> None:
	logger.info('%s', message)
	action()
	logger.info('%s done', message)


def _load_packages(args: argparse.Namespace) -> tuple[list[Package], int | None]:
	if args.kind == 'uv':
		project = UvProject(args.root)
		try:
			packages = project.packages()
		except FileNotFoundError:
			logger.exception('pyproject.toml not found')
			return [], 2

		_run_with_status(
			'Collecting installed versions...',
			lambda: set_installed_versions_uv(packages, args.root, args.timeout),
		)
		_run_with_status(
			'Checking newest versions...',
			lambda: set_newest_versions_uv(packages, args.timeout),
		)
		return packages, None

	project = NpmProject(args.root)
	try:
		packages = project.packages()
	except FileNotFoundError:
		logger.exception('package.json not found')
		return [], 2

	_run_with_status(
		'Collecting installed versions...',
		lambda: set_installed_versions_npm(packages, args.root, args.timeout),
	)
	_run_with_status(
		'Checking newest versions...',
		lambda: set_newest_versions_npm(packages, args.root, args.timeout),
	)
	return packages, None


def _entry_group_key(entry, group_by: str) -> str:
	origin, package = entry
	if group_by == 'package':
		return package.display_name
	return str(getattr(origin, 'pyproject_path', None) or getattr(origin, 'package_json_path', None))


def _group_entries(entries, group_by: str) -> list:
	grouped_entries = {}
	groups = []
	for entry in entries:
		group_key = _entry_group_key(entry, group_by)

		if group_key not in grouped_entries:
			grouped_entries[group_key] = []
			groups.append((group_key, grouped_entries[group_key]))
		grouped_entries[group_key].append(entry)

	return groups


def _render_grouped_entries(groups, group_by: str) -> tuple[dict, dict]:
	logger.info('')
	logger.info('Upgradable entries (grouped by %s):', group_by)
	group_map = {}
	item_map = {}
	for group_index, (path, group_entries) in enumerate(groups, start=1):
		group_key = str(group_index)
		group_map[group_key] = group_entries
		logger.info('%s) %s', group_key, path)

		for item_index, entry in enumerate(group_entries, start=1):
			origin, package = entry
			item_key = f'{group_index}.{item_index}'
			item_map[item_key] = entry
			logger.info('  %s) %s (%s -> %s)', item_key, package.display_name, origin.raw_spec, package.newest_version)

	return group_map, item_map


def _select_entries(entries, group_map, item_map, response) -> list:
	if response in ('', 'a', 'all'):
		return entries

	if response in ('n', 'none'):
		logger.info('No entries selected for upgrade.')
		return []

	selected_entries = []
	seen_entries = set()
	for raw_part in response.split(','):
		part = raw_part.strip()
		if not part:
			continue

		if part in group_map:
			for entry in group_map[part]:
				entry_id = id(entry)

				if entry_id not in seen_entries:
					selected_entries.append(entry)
					seen_entries.add(entry_id)
			continue

		if part in item_map:
			entry = item_map[part]
			entry_id = id(entry)

			if entry_id not in seen_entries:
				selected_entries.append(entry)
				seen_entries.add(entry_id)
			continue

	if not selected_entries:
		logger.info('No valid entries selected for upgrade.')
		return []

	if len(selected_entries) != len(entries):
		logger.info('Not selected: %s entries.', len(entries) - len(selected_entries))
	return selected_entries


def _choose_entries_interactive(entries, group_by: str) -> list:
	groups = _group_entries(entries, group_by)
	group_map, item_map = _render_grouped_entries(groups, group_by)
	response = input('Select entries to upgrade [a=all, n=none, 1=group, 1.2=item]: ').strip().lower()
	return _select_entries(entries, group_map, item_map, response)


def _handle_upgrade(args: argparse.Namespace, packages: list[Package]) -> int:
	if args.kind == 'uv':
		entries, skipped = collect_upgrade_entries(packages, include_up_to_date=args.show_up_to_date)

		def upgrade(selected) -> tuple[int, list[str]]:
			return upgrade_project_versions(selected, dry_run=args.dry_run)
	else:
		entries, skipped = collect_upgrade_entries_npm(packages, include_up_to_date=args.show_up_to_date)

		def upgrade(selected) -> tuple[int, list[str]]:
			return upgrade_project_versions_npm(selected, dry_run=args.dry_run)

	if not entries:
		logger.info('No upgradable dependency entries found.')
		return 0

	if args.interactive:
		entries = _choose_entries_interactive(entries, args.group_by)
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
