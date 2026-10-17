#!/usr/bin/env bash
# Merge the managed backend variables into the systemd EnvironmentFile.
#
# Usage: sync-backend-env.sh <env-file> <app_env> <user_pin> <admin_pin> [mapbox_secret_token]
#
# Only the listed keys are touched: any other line already present in the file
# (for example SQLITE_DB_PATH) is preserved, so the deploy never wipes manual
# host configuration. Values are validated with the same rules as the backend
# settings, so a broken release fails before systemd restarts the service.
set -euo pipefail

ENV_FILE="${1:?environment file path is required}"
APP_ENV="${2:?APP_ENV is required}"
USER_ACCESS_PIN="${3:?USER_ACCESS_PIN is required}"
ADMIN_ACCESS_PIN="${4:?ADMIN_ACCESS_PIN is required}"
MAPBOX_SECRET_TOKEN="${5:-}"

fail() {
    printf 'sync-backend-env: %s\n' "$1" >&2
    exit 1
}

[[ "${USER_ACCESS_PIN}" =~ ^[0-9]{6}$ ]] || fail "USER_ACCESS_PIN must be exactly six ASCII digits"
[[ "${ADMIN_ACCESS_PIN}" =~ ^[0-9]{6}$ ]] || fail "ADMIN_ACCESS_PIN must be exactly six ASCII digits"
[[ "${USER_ACCESS_PIN}" != "${ADMIN_ACCESS_PIN}" ]] || fail "access PINs must be different"

if [[ "${APP_ENV}" == "production" ]]; then
    if [[ "${USER_ACCESS_PIN}" == "202601" || "${ADMIN_ACCESS_PIN}" == "999999" ]]; then
        printf 'sync-backend-env: warning: production still uses the development PIN defaults, rotate them\n' >&2
    fi
    if [[ -z "${MAPBOX_SECRET_TOKEN}" ]]; then
        printf 'sync-backend-env: warning: MAPBOX_SECRET_TOKEN is empty, road distances fall back to haversine\n' >&2
    fi
fi

upsert() {
    local key="$1" value="$2" escaped
    escaped="${value//&/\\&}"
    if grep -qE "^[[:space:]]*${key}=" "${ENV_FILE}"; then
        sed -i "s|^[[:space:]]*${key}=.*|${key}=${escaped}|" "${ENV_FILE}"
    else
        printf '%s=%s\n' "${key}" "${value}" >>"${ENV_FILE}"
    fi
}

ENV_DIR="$(dirname "${ENV_FILE}")"
mkdir -p "${ENV_DIR}"
touch "${ENV_FILE}"

upsert APP_ENV "${APP_ENV}"
upsert USER_ACCESS_PIN "${USER_ACCESS_PIN}"
upsert ADMIN_ACCESS_PIN "${ADMIN_ACCESS_PIN}"
if [[ -n "${MAPBOX_SECRET_TOKEN}" ]]; then
    upsert MAPBOX_SECRET_TOKEN "${MAPBOX_SECRET_TOKEN}"
fi

printf 'sync-backend-env: %s updated\n' "${ENV_FILE}"
