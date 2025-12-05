import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

CURRENT_DIRECTORY = Path(__file__).parent


class UnknownPackageVersionSchemeError(Exception):
	pass


class UnsupportedPackageTypeError(Exception):
	def __init__(self):
		super().__init__('Cannot support package extras')


@dataclass
class Package:
	name: str
	project_version: str
	installed_version: str | None = None
	newest_version: str | None = None


def split_package_from_version(listing: str) -> tuple[str, str]:
	cleaned_listing = listing.split(',')[0]

	if '>=' in cleaned_listing:
		split_by = '>='

	elif '<=' in cleaned_listing:
		split_by = '<='

	elif '==' in cleaned_listing:
		split_by = '=='

	elif '<' in cleaned_listing:
		split_by = '<'

	elif '>' in cleaned_listing:
		split_by = '>'

	else:
		message = f'Unknown package versioning scheme for package listing: {listing}'
		raise UnknownPackageVersionSchemeError(message)

	package_name, version = cleaned_listing.split(split_by)
	return package_name, version


def set_project_versions(packages: list):
	all_package_listings = []

	with Path.open(CURRENT_DIRECTORY.parent / 'pyproject.toml') as f:
		data = tomllib.loads(f.read())

	all_package_listings.extend(list(data['project']['dependencies']))
	for group_name in data['project'].get('dependency-groups', []):
		all_package_listings.extend(data['project']['dependency-groups'][group_name])

	for group_name in data.get('dependency-groups', []):
		all_package_listings.extend(data['dependency-groups'][group_name])

	with Path.open(CURRENT_DIRECTORY / 'pyproject.toml') as f:
		data = tomllib.loads(f.read())

	all_package_listings.extend(list(data['project']['dependencies']))
	for group_name in data['project'].get('dependency-groups', []):
		all_package_listings.extend(data['project']['dependency-groups'][group_name])

	for group_name in data.get('dependency-groups', []):
		all_package_listings.extend(data['dependency-groups'][group_name])

	for package_listing in all_package_listings:
		package_name, version = split_package_from_version(package_listing)
		packages.append(Package(package_name, version))


def validate_package_extras(packages: list[Package]):
	unsupported_packages = []
	for package in packages:
		if '[' in package.name:
			unsupported_packages.append(package)

	for package in unsupported_packages:
		print(f'Unsupported package with extra: {package.name}')

	if unsupported_packages:
		raise UnsupportedPackageTypeError


def set_installed_versions(packages: list):
	package_name_to_package_map = {p.name: p for p in packages}

	args = [
		'uv',
		'export',
		'--locked',
		'--all-packages',
		'--all-groups',
		'--format',
		'requirements-txt',
		'--no-hashes',
	]
	process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	output, errors = process.communicate(timeout=10)
	output = output.decode('utf-8')

	for line in output.splitlines():
		if line.startswith('#'):
			continue

		cleaned_line = line.split(';')[0].strip()
		package_name, version = cleaned_line.split('==')

		package = package_name_to_package_map.get(package_name)
		if not package:
			continue

		package.installed_version = version


def set_newest_versions(packages: list):
	package_name_to_package_map = {p.name: p for p in packages}

	for package_name, package in package_name_to_package_map.items():
		args = [
			'uvx',
			'pip',
			'index',
			'versions',
			package_name,
		]
		process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		output, errors = process.communicate(timeout=10)
		output = output.decode('utf-8')

		lines = output.splitlines()
		if not lines:
			continue

		versions = lines[1].replace('Available versions:', '').strip().split(',')
		package.newest_version = versions[0]


def display_package_information(packages: list[Package]):
	packages_out_of_date = []
	packages_can_be_bumped = []

	for package in packages:
		if not package.installed_version:
			continue

		if package.installed_version != package.project_version:
			packages_can_be_bumped.append(package)

		if package.newest_version and package.newest_version != package.project_version:
			packages_out_of_date.append(package)

	if packages_out_of_date:
		print('Packages out of date:')
		print('{:<50}{:<30}{:<30}{:<30}{}'.format('Package Name', 'Installed Version', 'Project Version', 'Newest Version', 'Suggested Action'))

		suggested_action = 'Update package version'
		for package in packages_out_of_date:
			print(f'{package.name:<50}{package.installed_version:<30}{package.project_version:<30}{package.newest_version:<30}{suggested_action}')

	if packages_out_of_date and packages_can_be_bumped:
		print()

	if packages_can_be_bumped:
		print('Packages can be bumped:')
		print('{:<50}{:<30}{:<30}{:<30}{}'.format('Package Name', 'Installed Version', 'Project Version', 'Newest Version', 'Suggested Action'))

		suggested_action = 'Bump package version in project specification'
		for package in packages_can_be_bumped:
			print(f'{package.name:<50}{package.installed_version:<30}{package.project_version:<30}{package.newest_version:<30}{suggested_action}')


def main() -> int:
	packages = []
	set_project_versions(packages)
	validate_package_extras(packages)
	set_installed_versions(packages)
	set_newest_versions(packages)
	display_package_information(packages)
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
