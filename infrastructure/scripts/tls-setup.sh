#!/usr/bin/env bash
# ============================================================
# RoadSide Agent — TLS bootstrap (Let's Encrypt via certbot)
# Run ONCE per server to issue certs for all four hostnames.
# ============================================================
set -euo pipefail

DOMAIN="${SERVER_DOMAIN:?Set SERVER_DOMAIN, e.g. SERVER_DOMAIN=roadside.example.com}"
EMAIL="${LETS_ENCRYPT_EMAIL:?Set LETS_ENCRYPT_EMAIL for renewal notices}"
WEBROOT="${WEBROOT:-/var/www/certbot}"
CERTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/nginx/certs"

mkdir -p "$WEBROOT" "$CERTS_DIR/$DOMAIN"

# Subdomains the edge proxy serves:
SUBDOMAINS=(
  "$DOMAIN"
  "customer.$DOMAIN"
  "provider.$DOMAIN"
  "admin.$DOMAIN"
  "api.$DOMAIN"
)
DOMAIN_ARGS=()
for sd in "${SUBDOMAINS[@]}"; do
  DOMAIN_ARGS+=("-d" "$sd")
done

echo "==> Requesting cert for: ${SUBDOMAINS[*]}"
docker run --rm \
  -v "$WEBROOT:/var/www/certbot" \
  -v "$CERTS_DIR:/etc/letsencrypt" \
  certbot/certbot:latest \
    certonly \
    --webroot --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos --no-eff-email \
    --rsa-key-size 4096 \
    --non-interactive \
    "${DOMAIN_ARGS[@]}"

# certbot writes under live/<DOMAIN>/; symlink to the path nginx server blocks expect.
SRC="$CERTS_DIR/live/$DOMAIN"
DST="$CERTS_DIR/$DOMAIN"
ln -sf "$SRC/fullchain.pem" "$DST/fullchain.pem"
ln -sf "$SRC/privkey.pem"   "$DST/privkey.pem"

echo "==> Certs in place at $DST. Reload edge:"
echo "    docker compose -f infrastructure/docker-compose.yml -f infrastructure/docker-compose.prod.yml exec edge nginx -s reload"
