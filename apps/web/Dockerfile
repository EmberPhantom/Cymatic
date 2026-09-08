# syntax=docker/dockerfile:1.6
# Build stage
FROM node:20-alpine AS builder

RUN apk add --no-cache libc6-compat

WORKDIR /app

COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .

# Public build args (embedded at build time) - no defaults leaked
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ARG NEXT_PUBLIC_MINIO_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_MINIO_URL=$NEXT_PUBLIC_MINIO_URL

RUN mkdir -p public
RUN --mount=type=cache,target=/app/.next/cache npm run build

# Production stage
FROM node:20-alpine AS runner

RUN apk add --no-cache libc6-compat

WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Next's standalone server is emitted under /app/app when the build context is
# the web application. Keep public and generated assets beside server.js.
COPY --from=builder /app/public ./app/public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./app/.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV API_INTERNAL_URL=http://api:8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s CMD wget --spider -q http://127.0.0.1:3000 || exit 1

CMD ["node", "app/server.js"]
