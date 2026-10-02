# syntax=docker/dockerfile:1
# CYMATIC mobile browser viewer (Vite + Three.js static SPA).
# Build context: apps/viewer.

# ── Builder ────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund --prefer-offline

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ── Runner ─────────────────────────────────────────────────────
# Production-only install: `serve` is a runtime dependency, so
# `npm install --omit=dev` yields just serve (+ its tree). Build tools
# (vite, typescript) stay in the builder stage.
FROM node:20-alpine AS runner

WORKDIR /app

RUN addgroup --system --gid 1001 viewer \
    && adduser --system --uid 1001 viewer

COPY --link --from=builder --chown=1001:1001 /app/dist ./dist
COPY --link --chown=1001:1001 package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --omit=dev --no-audit --no-fund --prefer-offline

USER viewer

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s CMD wget --spider -q http://127.0.0.1:8090 || exit 1

CMD ["./node_modules/.bin/serve", "-s", "dist", "-l", "8090"]
