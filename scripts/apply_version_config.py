#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli_w
import tomllib

_DEFAULT_OPERATOR = '>='
_DEFAULT_SECTION = 'project.dependencies'
_OPERATORS = ('>=', '<=', '==', '>', '<')


class VersionConfigError(Exception):
	pass


def _split_listing(listing: str) -> tuple[str, str, str]:
	cleaned_listing = listing.split(',')[0]
	for operator in _OPERATORS:
		if operator in cleaned_listing:
			name, version = cleaned_listing.split(operator, 1)
			return name.strip(), operator, version.strip()
	message = f'Unsupported dependency specification: {listing}'
	raise VersionConfigError(message)


@dataclass
class PackageEntry:
	name: str
	project_version: str
	pyproject: Path
	section: str = _DEFAULT_SECTION
	operator: str | None = None
	install_version: str | None = None

	@classmethod
	def from_dict(cls, raw: dict[str, Any], repo_root: Path) -> 'PackageEntry':
		try:
			name = raw['name']
			project_version = raw['project_version']
		except KeyError as err:
			message = 'Each package entry requires "name" and "project_version" keys'
			raise VersionConfigError(message) from err

		pyproject_path = raw.get('pyproject') or raw.get('project_file')
		if not pyproject_path:
			message = 'Each package entry requires "pyproject" (or "project_file")'
			raise VersionConfigError(message)

		pyproject = (repo_root / pyproject_path).resolve()

		return cls(
			name=name,
			project_version=str(project_version),
			pyproject=pyproject,
			section=raw.get('section', _DEFAULT_SECTION),
			operator=raw.get('operator'),
			install_version=raw.get('install_version'),
		)


def _load_config(config_path: Path, repo_root: Path) -> list[PackageEntry]:
	raw = json.loads(config_path.read_text())
	packages: list[Any] | None = raw.get('python') or raw.get('packages')
	if packages is None:
		message = 'Config file must contain a "python" or "packages" list'
		raise VersionConfigError(message)
	if not isinstance(packages, list):
		message = '"python"/"packages" must be a list'
		raise VersionConfigError(message)

	return [PackageEntry.from_dict(item, repo_root) for item in packages]


def _ensure_section(root: dict[str, Any], dotted_path: str) -> list[Any]:
	current: Any = root
	parts = dotted_path.split('.')
	for index, part in enumerate(parts):
		is_last = index == len(parts) - 1
		if part not in current:
			current[part] = [] if is_last else {}
		current = current[part]
		if is_last and not isinstance(current, list):
			message = f'Section {dotted_path} is not a list in {root}'
			raise VersionConfigError(message)
		if not is_last and not isinstance(current, dict):
			message = f'Path {dotted_path} collides with non-table data'
			raise VersionConfigError(message)
	return current


def _next_operator(entries: list[str], package_name: str, fallback: str) -> str:
	for existing in entries:
		try:
			name, operator, _ = _split_listing(existing)
		except VersionConfigError:
			continue
		if name == package_name:
			return operator
	return fallback


def _update_pyproject(entry: PackageEntry) -> None:
	if not entry.pyproject.exists():
		message = f'pyproject.toml not found at {entry.pyproject}'
		raise VersionConfigError(message)

	data = tomllib.loads(entry.pyproject.read_text())
	listings = _ensure_section(data, entry.section)

	operator = entry.operator or _next_operator(listings, entry.name, _DEFAULT_OPERATOR)
	new_spec = f'{entry.name}{operator}{entry.project_version}'

	for index, listing in enumerate(listings):
		try:
			name, _, _ = _split_listing(listing)
		except VersionConfigError:
			continue
		if name == entry.name:
			listings[index] = new_spec
			break
	else:
		listings.append(new_spec)

	entry.pyproject.write_text(tomli_w.dumps(data))


def _install(entry: PackageEntry, *, installer: str = 'uv') -> None:
	if not entry.install_version:
		return

	spec = f'{entry.name}=={entry.install_version}'
	commands: list[list[str]] = []
	if installer == 'uv':
		commands.append(['uv', 'pip', 'install', '--system', spec])
	commands.append([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', spec])

	for command in commands:
		try:
			subprocess.run(command, check=True)  # noqa: S603
			return
		except FileNotFoundError:
			continue
		except subprocess.CalledProcessError as err:
			last_error = err
			continue

	message = f'Failed to install {spec}'
	if 'last_error' in locals():
		raise VersionConfigError(message) from last_error
	raise VersionConfigError(message)


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description='Install specific versions and bump project pins for tests.')
	parser.add_argument('--config', type=Path, required=True, help='Path to version config JSON file.')
	parser.add_argument(
		'--root',
		type=Path,
		default=Path(__file__).resolve().parent.parent,
		help='Repository root to resolve relative paths from the config.',
	)
	parser.add_argument('--skip-install', action='store_true', help='Skip installing packages; only rewrite pyproject files.')
	parser.add_argument(
		'--installer',
		choices=['uv', 'pip'],
		default='uv',
		help='Package installer to use when installing specific versions.',
	)
	args = parser.parse_args(argv)

	try:
		entries = _load_config(args.config, args.root)
	except (OSError, VersionConfigError) as err:
		print(err, file=sys.stderr)
		return 2

	for entry in entries:
		try:
			_update_pyproject(entry)
			if not args.skip_install:
				_install(entry, installer=args.installer)
			try:
				relative_path = entry.pyproject.relative_to(args.root)
			except ValueError:
				relative_path = entry.pyproject
			install_note = (
				'install skipped'
				if args.skip_install or not entry.install_version
				else f'installed {entry.install_version}'
			)
			print(
				f'Configured {entry.name}: {install_note} '
				f'and pinned {entry.project_version} in {relative_path} [{entry.section}]',
			)
		except VersionConfigError as err:
			print(err, file=sys.stderr)
			return 3

	return 0


if __name__ == '__main__':
	raise SystemExit(main())
