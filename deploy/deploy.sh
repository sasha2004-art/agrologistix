#!/usr/bin/env bash
# Deploy AgroLogistix to the target host without containers.
#
# Required environment:
#   DEPLOY_HOST, DEPLOY_USER, DEPLOY_APP_DIR, DEPLOY_WEB_ROOT, DEPLOY_SERVICE,
#   DEPLOY_DOMAIN (TLS certificate must exist, see deploy/setup-https.sh),
#   APP_ENV, USER_ACCESS_PIN, ADMIN_ACCESS_PIN
# Optional:
#   MAPBOX_SECRET_TOKEN (empty keeps the haversine road fallback),
#   DEPLOY_SSH_KEY_PATH, DEPLOY_SSH_STRICT (default: accept-new)
set -euo pipefail

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${DEPLOY_APP_DIR:?DEPLOY_APP_DIR is required}"
: "${DEPLOY_WEB_ROOT:?DEPLOY_WEB_ROOT is required}"
: "${DEPLOY_SERVICE:?DEPLOY_SERVICE is required}"
: "${DEPLOY_DOMAIN:?DEPLOY_DOMAIN is required}"
: "${APP_ENV:?APP_ENV is required}"
: "${USER_ACCESS_PIN:?USER_ACCESS_PIN is required}"
: "${ADMIN_ACCESS_PIN:?ADMIN_ACCESS_PIN is required}"
MAPBOX_SECRET_TOKEN="${MAPBOX_SECRET_TOKEN:-}"

SSH_STRICT="${DEPLOY_SSH_STRICT:-accept-new}"
SSH_OPTS=(-o "StrictHostKeyChecking=${SSH_STRICT}" -o ConnectTimeout=20)
if [[ -n "${DEPLOY_SSH_KEY_PATH:-}" ]]; then
    SSH_OPTS+=(-i "${DEPLOY_SSH_KEY_PATH}")
fi
SSH_CMD="ssh $(printf '%q ' "${SSH_OPTS[@]}")"

REMOTE="${DEPLOY_USER}@${DEPLOY_HOST}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Quoted forms keep tokens with special characters intact inside the remote script.
QUOTED_APP_ENV=${APP_ENV@Q}
QUOTED_USER_PIN=${USER_ACCESS_PIN@Q}
QUOTED_ADMIN_PIN=${ADMIN_ACCESS_PIN@Q}
QUOTED_MAPBOX=${MAPBOX_SECRET_TOKEN@Q}

if [[ ! -d frontend/dist ]]; then
    printf 'frontend/dist is missing: run "npm ci && npm run build" in frontend/ first\n' >&2
    exit 1
fi

printf '==> Syncing backend sources to %s\n' "${DEPLOY_APP_DIR}"
rsync -az --delete \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    --exclude '.ruff_cache' \
    --exclude 'data' \
    --exclude '*.egg-info' \
    -e "${SSH_CMD}" \
    backend/ "${REMOTE}:${DEPLOY_APP_DIR}/backend/"

printf '==> Syncing frontend build to %s\n' "${DEPLOY_WEB_ROOT}"
rsync -az --delete -e "${SSH_CMD}" frontend/dist/ "${REMOTE}:${DEPLOY_WEB_ROOT}/"

printf '==> Checking the TLS certificate for %s\n' "${DEPLOY_DOMAIN}"
TLS_FULLCHAIN="/etc/letsencrypt/live/${DEPLOY_DOMAIN}/fullchain.pem"
if ! ssh "${SSH_OPTS[@]}" "${REMOTE}" "test -f '${TLS_FULLCHAIN}'"; then
    printf 'TLS certificate %s is missing on the server.\n' "${TLS_FULLCHAIN}" >&2
    printf 'Run the one-time HTTPS bootstrap first:\n' >&2
    printf '  DEPLOY_HOST=%s DEPLOY_USER=%s DEPLOY_DOMAIN=%s DEPLOY_WEB_ROOT=%s bash deploy/setup-https.sh\n' \
        "${DEPLOY_HOST}" "${DEPLOY_USER}" "${DEPLOY_DOMAIN}" "${DEPLOY_WEB_ROOT}" >&2
    exit 1
fi

printf '==> Syncing service and nginx configuration\n'
rsync -az -e "${SSH_CMD}" deploy/agrologistix-backend.service \
    "${REMOTE}:/etc/systemd/system/${DEPLOY_SERVICE}"
rsync -az -e "${SSH_CMD}" deploy/nginx/agrologistix.conf \
    "${REMOTE}:/etc/nginx/sites-available/agrologistix.conf"
rsync -az -e "${SSH_CMD}" deploy/sync-backend-env.sh \
    "${REMOTE}:${DEPLOY_APP_DIR}/sync-backend-env.sh"

printf '==> Activating release on the server\n'
ssh "${SSH_OPTS[@]}" "${REMOTE}" "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
cd "${DEPLOY_APP_DIR}/backend"
uv sync --locked --no-dev
chown -R agrologistix:agrologistix "${DEPLOY_APP_DIR}"
mkdir -p "${DEPLOY_APP_DIR}/data"
bash "${DEPLOY_APP_DIR}/sync-backend-env.sh" \
    "${DEPLOY_APP_DIR}/.env" \
    ${QUOTED_APP_ENV} \
    ${QUOTED_USER_PIN} \
    ${QUOTED_ADMIN_PIN} \
    ${QUOTED_MAPBOX}
chmod 600 "${DEPLOY_APP_DIR}/.env"
chown agrologistix:agrologistix "${DEPLOY_APP_DIR}/.env"
ln -sf /etc/nginx/sites-available/agrologistix.conf /etc/nginx/sites-enabled/agrologistix.conf
systemctl daemon-reload
systemctl enable "${DEPLOY_SERVICE}" >/dev/null 2>&1 || true
systemctl restart "${DEPLOY_SERVICE}"
nginx -t
systemctl reload nginx
for _ in \$(seq 1 20); do
    if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then break; fi
    sleep 1
done
printf 'service=%s\n' "\$(systemctl is-active "${DEPLOY_SERVICE}")"
printf 'backend_health=%s\n' "\$(curl -fsS http://127.0.0.1:8000/api/v1/health)"
printf 'nginx_health=%s\n' "\$(curl -fsS http://127.0.0.1/health)"
printf 'https_health=%s\n' "\$(curl -fsS --resolve '${DEPLOY_DOMAIN}:443:127.0.0.1' 'https://${DEPLOY_DOMAIN}/api/v1/health')"
REMOTE_SCRIPT

printf '==> Deploy finished\n'
