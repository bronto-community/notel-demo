# react-native-app (TypeScript, Expo / React Native)

## Observability removed
- hooks/useTracer.ts: deleted. It held the WebTracerProvider, OTLP HTTP trace
  exporter (`<proxy>/otlp-http/v1/traces`), W3C trace-context and baggage
  propagators, fetch and XHR instrumentation, the resource attributes, and the
  `performance.getEntriesByType` monkeypatch (it existed only to silence a
  warning triggered by `instrumentation-fetch`).
- utils/SessionIdProcessor.ts: deleted (span processor adding `session.id`).
- app/_layout.tsx: `useTracer()` and the `fontsLoaded && tracerLoaded` memo.
- app/(tabs)/settings.tsx: `trace.disable()` and the tracer provider
  re-registration after the proxy URL changes. The query cache invalidation
  stays.
- gateways/Api.gateway.ts: the `Proxy` that wrapped every API call in a
  context carrying `session.id` baggage. The default export is now `Apis()`.
- metro.config.js: the comment about `@opentelemetry/semantic-conventions/incubating`
  needing package exports. The file itself is the stock Expo template and stays.
- tsconfig.json: `"types": ["node"]`; package.json: `@types/node` devDependency
  (hidden type coupling, see Traps).
- package.json / package-lock.json: the 10 direct `@opentelemetry/*` packages
  (`npm uninstall --package-lock-only` with npm 11 in `node:22`). Only
  deletions in the lockfile; the transitive `import-in-the-middle`,
  `require-in-the-middle`, `module-details-from-path`, `cjs-module-lexer` and
  `es-module-lexer` went with them.

## Behavior-preserving replacements
- Splash screen is gated on fonts only (BREAKING.md #11).
- All API methods still return promises (the non-`async` ones return the
  `request()` promise directly), so callers and `mutationFn` usage are
  unchanged.

## Traps
- Keep `react-native-device-info`: utils/Localhost.ts uses it for emulator
  detection. It was also used for OTel resource attributes.
- The removed Proxy called `SessionGateway.getSession()` before every API call,
  which also persisted the default session on first use. The calls that need
  the session (`getCart`, `addCartItem`, `emptyCart`, `listRecommendations`)
  call it themselves, so the session is still created before it is needed.
- Hidden type coupling: `npx tsc --noEmit` already fails upstream with 3
  errors in the generated protos/demo.ts (missing `@grpc/grpc-js`, `long`,
  `protobufjs/minimal`). Upstream gets Node globals such as `Buffer` only
  through `/// <reference types="node" />` in the `@opentelemetry/otlp-exporter-base`
  and `resources` typings. TypeScript 6 defaults `types` to `[]`, so the
  `@types/node` already in node_modules (via expo) is not loaded on its own.
  Without OTel, tsc reports ~80 extra `Cannot find name 'Buffer'` errors in
  protos/demo.ts. Per maintainer, `@types/node` `^26.5.0` (the version already
  locked) is a devDependency; the lockfile change is the root entry only.
  On its own this does not restore the 3 errors, so tsconfig.json also sets
  `"types": ["node"]` (maintainer-approved). tsc is back to upstream's 3
  errors. tsc is not part of the image build (only lint).
- The lockfile is generated with npm 11/12 (see android.Dockerfile comment);
  regenerate with npm >= 11, not the npm 10 shipped in `node:22`.
- app.json `io.opentelemetry.reactnativeapp` bundle/package id and the UI text
  "OpenTelemetry demo" are branding and stay.

## Dormant transitive OTel
- none (`node_modules/@opentelemetry` does not exist after `npm ci`).

## Verify
- `docker run --rm -v "$PWD":/src:ro node:22 sh -c 'cp -r /src /app && cd /app && npm i -g npm@11 && npm ci && npm run lint && npx tsc --noEmit'`
  from `src/react-native-app`: lint 0 errors (3 pre-existing warnings); tsc
  errors only in protos/demo.ts (exactly the 3 upstream errors, see Traps).
- android.Dockerfile APK build skipped (amd64-only base image plus Gradle
  release build under emulation on arm64).
