# syntax=docker/dockerfile:1
# CYMATIC web image (Next.js standalone).
# Build context: apps/web. ARGs are declared AFTER `COPY . .` so changing a
# public URL does not invalidate the npm-install layer.

# ── Builder ────────────────────────────────────────────────────
FROM node:20-alpine AS builder

# Telemetry off (faster, quieter builds).
# NOTE: do NOT set NODE_ENV=production here — `npm ci` would then skip
# devDependencies (autoprefixer, tailwind, typescript, ...) that `next build`
# needs. `next build` sets NODE_ENV=production itself.
ENV NEXT_TELEMETRY_DISABLED=1

RUN apk add --no-cache libc6-compat

WORKDIR /app

# Manifest first for layer cache: rebuilds on src changes reuse npm layer.
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund --prefer-offline

COPY . .

# Public build args (embedded at build time) - no defaults leaked.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ARG NEXT_PUBLIC_MINIO_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_MINIO_URL=$NEXT_PUBLIC_MINIO_URL

# Merged with the public-dir guard: one layer instead of two.
RUN --mount=type=cache,target=/app/.next/cache \
    mkdir -p public && npm run build

# ── Runner ─────────────────────────────────────────────────────
FROM node:20-alpine AS runner

RUN apk add --no-cache libc6-compat

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Next's standalone server is emitted under /app/app when the build context is
# the web application. Keep public and generated assets beside server.js.
# NOTE: --link layers cannot resolve usernames, so numeric UID:GID is used.
COPY --link --from=builder /app/public ./app/public
COPY --link --from=builder --chown=1001:1001 /app/.next/standalone ./
COPY --link --from=builder --chown=1001:1001 /app/.next/static ./app/.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV API_INTERNAL_URL=http://api:8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s CMD wget --spider -q http://127.0.0.1:3000 || exit 1

CMD ["node", "app/server.js"]
