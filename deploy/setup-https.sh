#!/usr/bin/env bash
# Issue or refresh the Let's Encrypt certificate for the AgroLogistix origin.
#
# The script is idempotent: it installs an HTTP-only bootstrap config, runs
# certbot with the webroot authenticator, then installs the TLS config from
# deploy/nginx/agrologistix.conf and enables automatic renewal.
#
# Required environment:
#   DEPLOY_HOST, DEPLOY_USER, DEPLOY_DOMAIN, DEPLOY_WEB_ROOT
# Optional:
#   DEPLOY_SSH_KEY_PATH, DEPLOY_SSH_STRICT (default: accept-new),
#   LETSENCRYPT_EMAIL (only needed for a fresh ACME account)
set -euo pipefail

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${DEPLOY_DOMAIN:?DEPLOY_DOMAIN is required}"
: "${DEPLOY_WEB_ROOT:?DEPLOY_WEB_ROOT is required}"

SSH_STRICT="${DEPLOY_SSH_STRICT:-accept-new}"
SSH_OPTS=(-o "StrictHostKeyChecking=${SSH_STRICT}" -o ConnectTimeout=20)
if [[ -n "${DEPLOY_SSH_KEY_PATH:-}" ]]; then
    SSH_OPTS+=(-i "${DEPLOY_SSH_KEY_PATH}")
fi
SSH_CMD="ssh $(printf '%q ' "${SSH_OPTS[@]}")"

REMOTE="${DEPLOY_USER}@${DEPLOY_HOST}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TLS_DIR="/etc/letsencrypt/live/${DEPLOY_DOMAIN}"

printf '==> Installing the HTTP bootstrap config on %s\n' "${REMOTE}"
rsync -az -e "${SSH_CMD}" \
    "${ROOT_DIR}/deploy/nginx/agrologistix-http-bootstrap.conf" \
    "${REMOTE}:/etc/nginx/sites-available/agrologistix-http-bootstrap.conf"
# The server config references limit_req zones, so the http-context file with
# the zone declarations must exist before the first nginx -t.
rsync -az -e "${SSH_CMD}" \
    "${ROOT_DIR}/deploy/nginx/agrologistix-limits.conf" \
    "${REMOTE}:/etc/nginx/conf.d/agrologistix-limits.conf"

ssh "${SSH_OPTS[@]}" "${REMOTE}" "bash -s" <<REMOTE_BOOTSTRAP
set -euo pipefail
install -m 644 /etc/nginx/sites-available/agrologistix-http-bootstrap.conf \
    /etc/nginx/sites-available/agrologistix.conf
ln -sf /etc/nginx/sites-available/agrologistix.conf \
    /etc/nginx/sites-enabled/agrologistix.conf
mkdir -p "${DEPLOY_WEB_ROOT}/.well-known/acme-challenge"
nginx -t
systemctl reload nginx
REMOTE_BOOTSTRAP

printf '==> Requesting a certificate for %s\n' "${DEPLOY_DOMAIN}"
EMAIL_ARGS=""
if [[ -n "${LETSENCRYPT_EMAIL:-}" ]]; then
    EMAIL_ARGS="--email ${LETSENCRYPT_EMAIL}"
fi
ssh "${SSH_OPTS[@]}" "${REMOTE}" "certbot certonly --webroot -w '${DEPLOY_WEB_ROOT}' \
    -d '${DEPLOY_DOMAIN}' --non-interactive --agree-tos --keep-until-expiring ${EMAIL_ARGS}"

printf '==> Installing the TLS config\n'
rsync -az -e "${SSH_CMD}" \
    "${ROOT_DIR}/deploy/nginx/agrologistix.conf" \
    "${REMOTE}:/etc/nginx/sites-available/agrologistix.conf"

ssh "${SSH_OPTS[@]}" "${REMOTE}" "bash -s" <<REMOTE_TLS
set -euo pipefail
nginx -t
systemctl reload nginx
systemctl enable --now certbot.timer
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
printf '%s\n' '#!/bin/sh' 'systemctl reload nginx' \
    > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
printf 'certificate=%s\n' "\$(openssl x509 -in '${TLS_DIR}/fullchain.pem' -noout -subject -dates | tr '\n' ' ')"
printf 'https_health=%s\n' "\$(curl -fsS --resolve '${DEPLOY_DOMAIN}:443:127.0.0.1' 'https://${DEPLOY_DOMAIN}/api/v1/health')"
REMOTE_TLS

printf '==> HTTPS is configured for https://%s\n' "${DEPLOY_DOMAIN}"
