# Edge Nginx — RoadSide Agent

Production reverse proxy that terminates TLS and routes per-host to the
three SPAs and the FastAPI backend.

## Hosts

| Hostname              | Upstream            | Purpose            |
|-----------------------|---------------------|--------------------|
| `customer.<domain>`   | frontend-customer   | Customer SPA       |
| `provider.<domain>`   | frontend-provider   | Provider SPA       |
| `admin.<domain>`      | frontend-admin (+ grafana under /grafana/) | Admin SPA + dashboards |
| `api.<domain>`        | api (FastAPI + /ws) | Backend API + WS   |

Plain HTTP is redirected to HTTPS except for the Let's Encrypt ACME challenge
path (`/.well-known/acme-challenge/`).

## Per-environment substitution

The server blocks reference `${SERVER_DOMAIN}`. Nginx itself doesn't expand
env vars in config files, so either:

1. Use the `envsubst` entrypoint trick:
   ```
   /docker-entrypoint.d/20-envsubst-on-templates.sh
   ```
   Rename each `*.conf` to `*.conf.template`, set `NGINX_ENVSUBST_TEMPLATE_SUFFIX=.template`,
   and pass `SERVER_DOMAIN=roadside.example.com` in the env.

2. Or, run `envsubst < template > /etc/nginx/conf.d/foo.conf` from the deploy
   script before bringing up the stack.

For dev/staging with a single host, the simplest path is to hard-code the
domain in the `*.conf` files before deploying.

## TLS

Mount certs at `/etc/nginx/certs/<domain>/{fullchain.pem,privkey.pem}`.
See `infrastructure/scripts/tls-setup.sh` for the Let's Encrypt bootstrap
and `tls-renew.sh` for the renewal cron.
