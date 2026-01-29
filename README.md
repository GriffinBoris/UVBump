# uvbump (distribution: uvbump-cli)

CLI helper that inspects a uv-managed project (or workspace) and reports which
dependencies can be bumped based on what is pinned in `pyproject.toml`, what is
installed in your lockfile environment, and what is currently available on
PyPI.

## Quick start

1. Install uv: https://docs.astral.sh/uv/.
2. Install uvbump once published: `pip install uvbump-cli` (or `uv tool install uvbump-cli`).
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

### Install and run as a uv tool

```
uv tool install uvbump-cli
uvbump --root /path/to/project
```

Examples:

```
# uv workspace (default)
uvbump --root .

# npm project
uvbump --kind npm --root path/to/frontend

# upgrade all dependencies (uv)
uvbump --root . --upgrade

# interactively choose upgrades (npm)
uvbump --kind npm --root path/to/frontend --upgrade --interactive --group-by package

# preview upgrade changes without writing files
uvbump --root . --upgrade --dry-run
```

Common flags:

- `--root` (optional): path to the directory that contains `pyproject.toml` or `package.json`. Defaults to the current working directory.
- `--kind` (optional): `uv` or `npm` (default: `uv`).
- `--timeout` (optional): subprocess timeout in seconds for uv/uvx/npm calls.
- `--upgrade`: rewrite dependency versions to the newest available versions.
- `--interactive`: pick which dependencies to upgrade.
- `--group-by` (interactive only): `workspace` or `package` (default: `workspace`).
- `--dry-run`: preview upgrade changes without writing files.
- `--show-up-to-date`: include dependencies that already match the newest version in upgrade selection.
- `--version`: print the current uvbump version.

The command uses `uv export` and `uvx pip index versions` under the hood for uv projects, so make sure `uv` is on your `PATH`.

## Development

- Run locally with `uv run python -m uvbump --root examples` to exercise the sample workspace in `examples/`.
- Formatting/linting is handled by ruff; run `ruff check` and `ruff format` as needed.

## Docker test harness

- Build an image that prepares custom mismatched environments: `docker build -t uvbump-tests .`
- Version scenarios are driven by Jinja templates:
  - Edit `examples/version.env` for the pin you want in `pyproject.toml.jinja` files and the install versions you want in the environment.
  - On container start the entrypoint sources that env file, renders each `*.jinja` under `examples/` into `pyproject.toml`, and installs the requested runtime packages.
- Run a sample check: `docker run --rm -e VERSION_ENV=/app/examples/version.env uvbump-tests python -m uvbump --root examples`
- Opt out of installs with `SKIP_INSTALL=1`, skip template rendering with `SKIP_TEMPLATE_RENDER=1`, or skip the whole version step with `SKIP_VERSION_CONFIG=1`.

## Building & publishing to PyPI

1. Build artifacts: `uv build` (uses Hatchling under the hood).
2. Verify contents: inspect `dist/` for the wheel and sdist.
3. Publish (after configuring credentials): `uv publish --token <pypi-token>` or `python -m twine upload dist/*`.

The project metadata lives in `pyproject.toml`; update the version there before each release.
