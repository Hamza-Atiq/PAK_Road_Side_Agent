#!/usr/bin/env bash
# ============================================================
# Self-signed TLS fallback for staging / local end-to-end testing.
# Do NOT use in production — browsers reject self-signed certs and Twilio
# webhook signature verification will fail (callback URL must match a
# publicly-trusted certificate).
# ============================================================
set -euo pipefail

DOMAIN="${SERVER_DOMAIN:?Set SERVER_DOMAIN, e.g. SERVER_DOMAIN=roadside.local}"
CERTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/nginx/certs/$DOMAIN"

mkdir -p "$CERTS_DIR"

openssl req -x509 -nodes -newkey rsa:4096 \
  -days 365 \
  -keyout "$CERTS_DIR/privkey.pem" \
  -out    "$CERTS_DIR/fullchain.pem" \
  -subj "/CN=$DOMAIN" \
  -addext "subjectAltName=DNS:$DOMAIN,DNS:customer.$DOMAIN,DNS:provider.$DOMAIN,DNS:admin.$DOMAIN,DNS:api.$DOMAIN"

chmod 600 "$CERTS_DIR/privkey.pem"
echo "==> Self-signed cert written to $CERTS_DIR"
