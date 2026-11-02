# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG BACKEND_URL=http://api:8000
ENV BACKEND_URL=$BACKEND_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S nexora && adduser -S nexora -G nexora
COPY --from=build --chown=nexora:nexora /app/.next/standalone ./
COPY --from=build --chown=nexora:nexora /app/.next/static ./.next/static
COPY --from=build --chown=nexora:nexora /app/public ./public
USER nexora
EXPOSE 3000
# BACKEND_URL is read at build time by next.config rewrites; pass --build-arg/ENV in CI for non-compose deployments.
CMD ["node", "server.js"]
