#!/usr/bin/env bash
# Renew Let's Encrypt certs. Run via cron daily; certbot only renews when
# the cert is within 30 days of expiry, so daily invocations are safe.
set -euo pipefail

WEBROOT="${WEBROOT:-/var/www/certbot}"
CERTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/nginx/certs"

docker run --rm \
  -v "$WEBROOT:/var/www/certbot" \
  -v "$CERTS_DIR:/etc/letsencrypt" \
  certbot/certbot:latest renew --quiet

# Reload nginx to pick up new cert files.
docker compose \
  -f infrastructure/docker-compose.yml \
  -f infrastructure/docker-compose.prod.yml \
  exec -T edge nginx -s reload
