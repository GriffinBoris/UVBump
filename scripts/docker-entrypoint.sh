#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/app}"
ENV_FILE="${VERSION_ENV:-${ROOT_DIR}/test/version.env}"
TEMPLATE_ROOT="${TEMPLATE_ROOT:-${ROOT_DIR}/test}"

if [[ "${SKIP_VERSION_CONFIG:-0}" != "1" ]]; then
	if [[ -f "${ENV_FILE}" ]]; then
		# shellcheck source=/dev/null
		set -a; source "${ENV_FILE}"; set +a
		echo "Loaded version env from ${ENV_FILE}"
	else
		echo "Version env not found at ${ENV_FILE}; continuing without overrides."
	fi

	if [[ "${SKIP_TEMPLATE_RENDER:-0}" != "1" ]]; then
		python "${ROOT_DIR}/scripts/render_templates.py" \
			--template-root "${TEMPLATE_ROOT}" \
			--output-root "${TEMPLATE_ROOT}" \
			--env-file "${ENV_FILE}"
	fi

	if [[ "${SKIP_INSTALL:-0}" != "1" && -n "${PYTHON_INSTALL_SPECS:-}" ]]; then
		echo "Installing pinned runtime packages: ${PYTHON_INSTALL_SPECS}"
		if ! uv pip install --system ${PYTHON_INSTALL_SPECS}; then
			python -m pip install --no-cache-dir ${PYTHON_INSTALL_SPECS}
		fi
	fi
fi

exec "$@"
