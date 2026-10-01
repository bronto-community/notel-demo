# frontend (Next.js, TypeScript)

## Observability removed
- `utils/telemetry/Instrumentation.js`: Node SDK (OTLP gRPC traces, metrics,
  logs, resource detectors, auto-instrumentations). Deleted.
- `utils/telemetry/FrontendTracer.ts`: browser `WebTracerProvider`, OTLP HTTP
  exporter, W3C propagators, web auto-instrumentations,
  `demo.synthetic_request` span attribute. Deleted.
- `utils/telemetry/SessionIdProcessor.ts`: span processor adding `session.id`
  and `enduser.id`. Deleted.
- `utils/enums/AttributeNames.ts`: only used by the two items above and the
  gateway Proxy. Deleted.
- `utils/telemetry/InstrumentationMiddleware.ts`: span lookup, `context.with`,
  `recordException`, `setStatus`, `http.status_code` attribute. Replaced by
  `utils/ApiLogMiddleware.ts` (see below).
- `gateways/Api.gateway.ts`: `Proxy` that set `session.id`/`enduser.id`
  baggage around every API call. `ApiGateway` is now plain `Apis()`.
- `pages/api/checkout.ts`: `recordException` and `setStatus` in the
  `placeOrder` catch. The catch and its 422/500 responses are kept.
- `pages/_app.tsx`: `FrontendTracer()` call and the `NEXT_PUBLIC_OTEL_*` /
  `IS_SYNTHETIC_REQUEST` `window.ENV` typings.
- `pages/_document.tsx`: `synthetic_request` baggage read, OTLP endpoint
  selection (`OTEL_COLLECTOR_HOST`, `PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
  `WEB_OTEL_SERVICE_NAME`) and the matching `window.ENV` entries.
  `NEXT_PUBLIC_PLATFORM` stays.
- `next.config.js`: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_SERVICE_NAME`,
  `PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` env passthrough.
- `package.json`: all 23 `@opentelemetry/*` dependencies; the `--require`
  in `dev` (`NODE_OPTIONS`) and `start`.
- `package-lock.json`: regenerated with `npm uninstall --package-lock-only`
  in `node:25.9.0-slim` (Dockerfile version). No remaining package changed
  version (810 -> 659 entries).
- `Dockerfile`: COPY of `Instrumentation.js`, `CMD` is now `["server.js"]`,
  the `utils/telemetry/` COPY is replaced by COPYs of `utils/logger.ts` and
  `utils/ApiLogMiddleware.ts`.

## Behavior-preserving replacements
- `utils/ApiLogMiddleware.ts` (BREAKING.md #12): slim wrapper that only writes
  the pino `API request completed` (info) and `API request failed` (error,
  then rethrow) logs, with the same fields (`http.request.method`, `url.path`,
  `http.response.status_code`, `err`). The semconv constants are inlined as
  string keys so the log shape is unchanged. All 8 API routes import it.
- `utils/telemetry/logger.ts` moved unchanged to `utils/logger.ts`.

## Traps
- `npm run lint` (`next lint`) is broken upstream: Next 16 removed `next
  lint` and ESLint 9 rejects `.eslintrc`. Not fixed here. Lint was checked
  with a temporary flat config (typescript-eslint recommended) mounted into
  the builder image.
- The Dockerfile COPYs `utils/` files one by one. A new file under `utils/`
  needs its own COPY or `next build` fails on the import.
- `npm uninstall --package-lock-only` with all 23 names once returned without
  editing package.json; re-running fixed it. Always check that
  `grep -c @opentelemetry package.json` is 0 afterwards.
- Ad flag targeting loses `session.id` baggage (BREAKING.md #1, open).

## Dormant transitive OTel
- `next` vendors `next/dist/compiled/@opentelemetry/api` (known case).
- `npm ls --all` shows only `UNMET OPTIONAL DEPENDENCY @opentelemetry/api@^1.1.0`
  (an optional peer of `next`); nothing is installed under
  `node_modules/@opentelemetry`.

## Verify
- `docker build -f src/frontend/Dockerfile .` (runs `next build`, including
  the type-check).
- `docker build --load --target builder -f src/frontend/Dockerfile -t fe-b .`
  then `docker run --rm fe-b npx tsc --noEmit` and
  `docker run --rm fe-b sh -c 'npm ls --all | grep -i opentelemetry'`.
- Run the image with `-e PORT=8080`, request `/api/currency`, and check that
  the `API request completed/failed` log line appears.
