#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/app}"
CONFIG_FILE="${VERSION_CONFIG:-${ROOT_DIR}/test/version-config.json}"

if [[ "${SKIP_VERSION_CONFIG:-0}" != "1" ]]; then
	if [[ -f "${CONFIG_FILE}" ]]; then
		args=(--config "${CONFIG_FILE}" --root "${ROOT_DIR}")
		if [[ "${SKIP_INSTALL:-0}" == "1" ]]; then
			args+=(--skip-install)
		fi
		echo "Applying version config from ${CONFIG_FILE}"
		python "${ROOT_DIR}/scripts/apply_version_config.py" "${args[@]}"
	else
		echo "Version config not found at ${CONFIG_FILE}; skipping injection."
	fi
fi

exec "$@"
