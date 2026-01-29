# AGENTS.md

Guidance for agentic coding in this repository. Keep changes simple, readable, and low‑ceremony.

## Project layout
- `src/uvbump/`: package code (CLI + core logic).
- `examples/`: sample workspaces used for manual runs and docker harness.
- `scripts/`: helper scripts for docker template rendering.
- `pyproject.toml`: project metadata, dependencies, and tooling config.

## Build / lint / test commands

### Build
```
uv build
```

### Publish
```
uv publish --token <pypi-token>
```

### Run the CLI locally
```
uv run python -m uvbump --root examples
```

### Lint / format (pre-commit parity)
These are the same commands defined in `.pre-commit-config.yaml`:
```
cd src
uv run ruff check --fix
uv run ruff format
uv run isort .
```

### Docker harness (optional)
```
task docker:build
task docker:run
```

### Tests
There is no test framework wired up yet (no pytest/nose/nox config). If tests are added later, document the single‑test command here (e.g. `pytest path::test_name`).

## Code style and conventions

### Formatting
- Ruff is the formatter and linter.
- Tabs are used for indentation (ruff format config uses tabs).
- Line length target is 300.
- Prefer single quotes in strings (ruff format config).
- Add logical blank lines between sections of code to improve readability.

### Imports
- Prefer standard library imports first, then third‑party, then local.
- Use explicit imports (avoid `import *`).
- Keep import order stable; run `ruff format` + `isort` if unsure.
- Use fully qualified imports (prefer absolute module paths over relative imports).

### Types
- Type hints are used but kept lightweight.
- Prefer `str | None` over `Optional[str]`.
- Keep type hints minimal; use primitive types where possible and only add hints that improve clarity.
- Avoid verbose variable annotations when the initializer makes the type obvious; let the IDE infer in those cases.
- Avoid heavy generic typing or complex protocols unless necessary.
- Use `dataclasses` for simple data containers.

### Naming
- `snake_case` for functions/variables.
- `CapWords` for classes.
- Constants in `UPPER_SNAKE_CASE`.

### Logging and output
- Use `logging` (see `configure_logging()` in `src/uvbump/core.py`).
- Avoid `print` in library/CLI paths; keep output consistent via logger.
- Use lazy logging formatting (`logger.info('%s', value)`).

### Error handling
- Prefer explicit exceptions with clear messages.
- Handle missing files gracefully and return non‑zero exit codes.
- When shelling out, catch `FileNotFoundError` and `subprocess.SubprocessError` and continue when possible.

### Dependency parsing and versions
- For uv/pyproject parsing, use `packaging.Requirement`.
- Normalize package names via `packaging.utils.canonicalize_name`.
- Preserve original operator style when rewriting specs.
- Keep extras/markers intact when writing updated specs.

### File writes
- For `pyproject.toml`, use `tomlkit` to preserve formatting.
- For `package.json`, write with `json.dumps(..., indent=2)` and a trailing newline.
- Avoid introducing Unicode unless the file already uses it.

### CLI behavior
- CLI entrypoint is `uvbump.__main__:main`.
- Keep flags small and predictable (`--root`, `--kind`, `--upgrade`, `--interactive`, `--dry-run`).
- Interactive mode should be optional and non‑blocking in non‑interactive runs.

## Operational guidance for agents

### Living document
- After each set of changes, reflect on any new rules, pitfalls, or context that would help future work.
- Update `AGENTS.md` whenever something new should be documented (this file is a living guide).
- Always check for new learnings like this and add them when they would reduce future mistakes.

### Edits
- Prefer small, targeted edits over sweeping refactors.
- Keep functions short; extract helpers when complexity grows.
- Avoid over‑engineering; this is a small utility CLI.
- Break logic into functions/classes when it improves clarity.
- Prefer clear, explicit variable names (avoid single-letter names outside tight scopes).
- Avoid unnecessary keyword-only markers (`*`) unless they provide real clarity.
- Avoid useless code; remove dead branches, unused variables, and unused imports.

### Files to avoid touching unless needed
- `uv.lock` (managed by uv).
- `examples/` content (used for manual test scenarios).

### Pre-commit hooks
- Run the lint/format commands listed above before finalizing.
- Do not change hooks unless explicitly asked.

## Cursor/Copilot rules
No `.cursor/rules/`, `.cursorrules`, or `.github/copilot-instructions.md` files were found in this repository.
