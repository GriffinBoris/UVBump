# uvbump

CLI helper that inspects a uv-managed project (or workspace) and reports which
dependencies can be bumped based on what is pinned in `pyproject.toml`, what is
installed in your lockfile environment, and what is currently available on
PyPI.

## Quick start

1. Install uv: https://docs.astral.sh/uv/.
2. Install uvbump once published: `pip install uvbump` (or `uv tool install uvbump`).
3. From a uv project root, run `uvbump` to print two tables:
   - **Packages out of date**: your pins lag behind the newest versions on PyPI.
   - **Packages can be bumped**: installed versions differ from the versions pinned in `pyproject.toml`.

```
$ uvbump --root .
Packages out of date:
Package Name                                      Installed Version             Project Version               Newest Version                Suggested Action
requests                                         2.32.3                       2.31.0                         2.32.3                        Update package version

Packages can be bumped:
Package Name                                      Installed Version             Project Version               Newest Version                Suggested Action
requests                                         2.32.3                       2.31.0                         2.32.3                        Bump package version in project specification
```

## Usage

```
uvbump --root /path/to/project
```

- `--root` (optional): path to the directory that contains `pyproject.toml`. Defaults to the current working directory.
- The command uses `uv export` and `uvx pip index versions` under the hood, so make sure `uv` is on your `PATH`.

## Development

- Run locally with `uv run python -m uvbump --root test` to exercise the sample workspace in `test/`.
- Formatting/linting is not configured yet; contributions welcome.

## Docker test harness

- Build an image that prepares custom mismatched environments: `docker build -t uvbump-tests .`
- Version scenarios live in `test/version-config.json`; mount or replace it and tweak `install_version` / `project_version` pairs per package.
- Entry point applies the config (installing the requested versions locally and rewriting the pinned versions in the referenced `pyproject.toml` files) before running the container command.
- Run a sample check: `docker run --rm -e VERSION_CONFIG=/app/test/version-config.json uvbump-tests python -m uvbump --root test`
- Opt out of installs with `SKIP_INSTALL=1` or skip pyproject rewrites entirely with `SKIP_VERSION_CONFIG=1`.

## Building & publishing to PyPI

1. Build artifacts: `uv build` (uses Hatchling under the hood).
2. Verify contents: inspect `dist/` for the wheel and sdist.
3. Publish (after configuring credentials): `uv publish --token <pypi-token>` or `python -m twine upload dist/*`.

The project metadata lives in `pyproject.toml`; update the version there before each release.
