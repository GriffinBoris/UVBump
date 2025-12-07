#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def _load_env(env_file: Path) -> dict[str, str]:
	values: dict[str, str] = {}
	if not env_file.exists():
		return values

	for raw_line in env_file.read_text().splitlines():
		line = raw_line.strip()
		if not line or line.startswith('#'):
			continue
		if '=' not in line:
			continue
		key, value = line.split('=', 1)
		value = value.strip().strip('"').strip("'")
		values[key.strip()] = value
	return values


def render_templates(template_root: Path, output_root: Path, context: dict[str, str]) -> None:
	env = Environment(loader=FileSystemLoader(template_root))
	for template_path in template_root.rglob('*.jinja'):
		relative = template_path.relative_to(template_root)
		target = output_root / relative.with_suffix('')
		target.parent.mkdir(parents=True, exist_ok=True)

		template = env.get_template(str(relative))
		rendered = template.render(**context)
		target.write_text(rendered)
		print(f'Rendered {template_path} -> {target}')


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description='Render Jinja templates with environment variables.')
	parser.add_argument('--template-root', type=Path, required=True, help='Directory containing Jinja templates.')
	parser.add_argument('--output-root', type=Path, required=True, help='Directory where rendered files will be written.')
	parser.add_argument('--env-file', type=Path, help='Path to an env file with key=value lines.')
	args = parser.parse_args(argv)

	context: dict[str, str] = {}
	if args.env_file:
		context.update(_load_env(args.env_file))
	context.update(os.environ)

	render_templates(args.template_root, args.output_root, context)
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
