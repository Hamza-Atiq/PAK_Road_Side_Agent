# syntax=docker/dockerfile:1.7
# ============================================================
# RoadSide Agent — Customer SPA
# Multi-stage: node builds the Vite bundle; nginx serves the static output.
# ============================================================

# ---------- Stage 1: build ----------
FROM node:20-alpine AS build
WORKDIR /app

# Copy manifests first so the npm cache layer is reused unless deps change.
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

# Public-facing build-time env. Override at build time with:
#   docker build --build-arg VITE_API_BASE_URL=https://api.example.com ...
ARG VITE_API_BASE_URL=""
ARG VITE_WS_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_WS_BASE_URL=$VITE_WS_BASE_URL

RUN npm run build

# ---------- Stage 2: serve ----------
FROM nginx:1.27-alpine AS runtime

# SPA-aware Nginx config: fall back to /index.html for unknown paths so
# react-router routes work on hard refresh. Compress text assets.
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Drop root for runtime.
USER nginx
EXPOSE 80

# Healthcheck — nginx serves the asset, so a 200 on / is a green light.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
