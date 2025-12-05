import json
import subprocess
from pathlib import Path

from uvbump.core import Package, UnsupportedPackageTypeError


def _normalize_spec(spec: str) -> str:
	for op in ('^', '~', '>=', '<=', '>', '<', '='):
		if spec.startswith(op):
			return spec[len(op) :]
	return spec


class NpmProject:
	def __init__(self, root_path: Path) -> None:
		self.root_path = root_path

	@property
	def package_json_path(self) -> Path:
		return self.root_path / 'package.json'

	def dependency_specs(self) -> dict[str, str]:
		if not self.package_json_path.exists():
			message = f'package.json not found at: {self.package_json_path}'
			raise FileNotFoundError(message)

		data = json.loads(self.package_json_path.read_text())
		listings: dict[str, str] = {}
		for key in (
			'dependencies',
			'devDependencies',
			'peerDependencies',
			'optionalDependencies',
		):
			listings.update(data.get(key, {}))
		return listings

	def packages(self) -> list[Package]:
		packages: list[Package] = []
		for name, spec in self.dependency_specs().items():
			if spec.startswith(('git+', 'file:', 'http:', 'https:')):
				message = f'Unsupported non-registry spec for {name}: {spec}'
				raise UnsupportedPackageTypeError(message)
			packages.append(Package(name=name, project_version=_normalize_spec(spec)))
		return packages


def set_installed_versions_npm(packages: list[Package], root: Path, timeout: int) -> None:
	package_map = {p.name: p for p in packages}
	args = ['npm', 'ls', '--depth=0', '--json']

	try:
		result = subprocess.run(  # noqa: S603
			args,
			check=True,
			capture_output=True,
			text=True,
			cwd=root,
			timeout=timeout,
		)
	except (FileNotFoundError, subprocess.SubprocessError):
		return

	data = json.loads(result.stdout)
	installed = data.get('dependencies', {})
	for name, info in installed.items():
		package = package_map.get(name)
		if package:
			package.installed_version = info.get('version')


def set_newest_versions_npm(packages: list[Package], root: Path, timeout: int) -> None:
	for package in packages:
		args = ['npm', 'view', package.name, 'version']
		try:
			result = subprocess.run(  # noqa: S603
				args,
				check=True,
				capture_output=True,
				text=True,
				cwd=root,
				timeout=timeout,
			)
		except (FileNotFoundError, subprocess.SubprocessError):
			continue

		package.newest_version = result.stdout.strip()
