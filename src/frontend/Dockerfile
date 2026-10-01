# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM docker.io/library/node:26.10.0-slim@sha256:ec7758ee051e457b468b32bde57b0879010b325bb9862718e9615225ce4aaae1 AS builder

WORKDIR /app

COPY ./src/frontend/package.json package.json
COPY ./src/frontend/package-lock.json package-lock.json

RUN npm ci

COPY ./src/frontend/components/ components/
COPY ./src/frontend/gateways/ gateways/
COPY ./src/frontend/pages/ pages/
COPY ./src/frontend/protos/ protos/
COPY ./src/frontend/providers/ providers/
COPY ./src/frontend/services/ services/
COPY ./src/frontend/styles/ styles/
COPY ./src/frontend/types/ types/

COPY ./src/frontend/utils/enums/ utils/enums/
COPY ./src/frontend/utils/ApiLogMiddleware.ts utils/ApiLogMiddleware.ts
COPY ./src/frontend/utils/imageLoader.js utils/imageLoader.js
COPY ./src/frontend/utils/logger.ts utils/logger.ts
COPY ./src/frontend/utils/Request.ts utils/Request.ts

COPY ./src/frontend/next.config.js next.config.js
COPY ./src/frontend/tsconfig.json tsconfig.json

RUN npm run build

# -----------------------------------------------------------------------------

FROM docker.io/library/node:26.10.0-slim@sha256:ec7758ee051e457b468b32bde57b0879010b325bb9862718e9615225ce4aaae1 AS deps

WORKDIR /app

COPY ./src/frontend/package.json package.json
COPY ./src/frontend/package-lock.json package-lock.json

RUN npm ci --omit=dev

# -----------------------------------------------------------------------------

FROM gcr.io/distroless/nodejs24-debian13:nonroot@sha256:9eeb7f5887d0e239e78264b06f7f11d2e14be534050481803a9e4728fcdd278e

WORKDIR /app

COPY --from=builder /app/.next/standalone/ ./
COPY --from=builder /app/.next/static/ .next/static/

COPY --from=deps /app/node_modules/ node_modules/

COPY ./src/frontend/public/ public/

ARG FRONTEND_PORT=8080
EXPOSE ${FRONTEND_PORT}

CMD ["server.js"]
