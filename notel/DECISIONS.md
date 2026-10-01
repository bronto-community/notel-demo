# notel-demo decisions

Decisions made by the maintainer for the notel-demo fork: the OpenTelemetry
Demo with all observability removed, used as a baseline for applying
auto-instrumentation or agent-based instrumentation. Agents and skills must
follow these. If a new situation is not covered here, stop and ask the
maintainer. Do not decide on your own.

## Goal and scope

- Remove all observability: OpenTelemetry API and SDK, exporters,
  instrumentation libraries and agents, Prometheus clients and endpoints,
  Traceloop/OpenLLMetry, OpAMP, the collector, backends (Jaeger, Prometheus,
  Grafana, OpenSearch), profiling, the telemetry schema and docs, and
  telemetry tests.
- No API calls may remain, not even no-op ones.
- **No direct observability dependencies**: every direct OTel, Prometheus,
  Traceloop or instrumentation dependency, agent, build step and code call is
  removed. Transitive or vendored OTel is accepted only if it stays silent
  (see "Transitive dependencies").
- Breaking or behavior changes are flagged in `notel/BREAKING.md` first,
  then fixed. Items that could be addressed upstream are marked as such.

## Sync model

- Regenerate on every sync, not on every upstream PR. Take a fresh upstream
  commit, apply the tooling commit, run the deterministic scripts in `notel/`,
  then run the per-service skills. The previous fork diff is a reference for
  each service.
- `main` is rebuilt on every sync: the upstream commit, then the tooling
  commit, then the strip commits (deletions, infra, one per service,
  lockfiles). Each result is tagged `notel/<upstream-short-sha>`.
- Local clone: `~/Projects/notel-demo`. Remote: `bronto-community/notel-demo`,
  internal at first. Never push to upstream or to personal forks. Push only
  when the maintainer explicitly says so.

## Tooling layout

- Skills: `.agents/skills/notel-*/SKILL.md`, following the Agent Skills open
  standard. `.claude/skills` is a symlink to `.agents/skills`.
- Deterministic parts are plain scripts in `notel/scripts/`, written in Python
  or Bash. They run with nothing but Docker, and no LLM is required.
- Docs live in `notel/`. AGENTS.md has a short notel section pointing here.

## Behavior decisions

- **Logging**: where logs currently go only through OTel, replace that with
  plain stdout logging using the language's standard or already-present
  logger. Keep the same messages and levels. This applies to: Go `slog`
  TextHandler on stdout, Rust `tracing_subscriber` fmt, C++ `std::cout` and
  `std::cerr`, Python `logging.basicConfig`, PHP Monolog StreamHandler on
  `php://stdout`.
- **Framework telemetry**: keep logging facades (Rust `tracing` used as the
  log facade, Go `slog`, Python `logging`, .NET `ILogger`, Phoenix
  `:telemetry` for request logs). Remove metric and tracing modules: the
  flagd-ui Telemetry metrics module and the LiveDashboard metrics page, .NET
  `Meter` and `ActivitySource` usage, and stopwatch-based latency recording
  that exists only for metrics.
- **Frontend access logs**: keep a slim API-route wrapper that only writes the
  pino "API request completed/failed" logs.
- **Flags**: remove `emitRawPii` everywhere. Keep all failure-scenario flags.
- **synthetic_request**: remove the marker everywhere. This covers
  load-generator baggage, Playwright header injection, and span tagging in
  checkout, payment and frontend.
- **Load-generator browser waits**: keep the `wait_for_timeout(2000)` calls.
  They are not only there for trace export: they keep each page alive long
  enough for the add-to-cart and currency requests to fire. This keeps the
  traffic shape identical to upstream, so comparisons stay fair.
- **Leftover dependencies that existed only for OTel**: remove them even if
  they are not OTel packages themselves. Examples: quote `guzzlehttp/guzzle`,
  mcp `langchain`, agent `aiohttp` and `greenlet`. Unused dependencies that
  are unrelated to OTel stay.
- **Implicit couplings**: when an OTel package silently provided something
  the app needs, add an explicit replacement and record it in BREAKING.md.
  Examples: accounting gets `Microsoft.Extensions.Hosting`, and
  react-native-app gets `@types/node`.
- **Test fixtures**: remove recorded telemetry calls from the agent VCR
  cassettes (`POST otel-collector:4318/...`) on every sync.
- **Out of scope**: problems upstream already has that are unrelated to
  observability stay untouched, and are listed in BREAKING.md under
  "Upstream issues noticed". One example is frontend `npm run lint`.
- **Unused non-OTel code**: leave it, for example
  `ValkeyCartStore.GetConnection()`.
- **Naming**: branding and project identifiers stay and are allowlisted. This
  covers Go module paths, the Gradle project and group names, the RN bundle id
  `io.opentelemetry.reactnativeapp`, README product names, the `otel*` theme
  colors and page titles.
- **Ad session targeting via baggage**: strip it now. Ad flags are evaluated
  with an empty context. Tracked as open item #1 in BREAKING.md.
- **Branding**: change only `IMAGE_NAME`, so upstream's instrumented images
  can never be pulled. Keep the `oteldemo` proto package, the network name,
  the UI footer and the theme.
- **CI**: strip workflows and jobs that exist only for observability (the
  telemetry tests, Weaver, matrix entries for deleted images). Keep the rest.
  Image pushes go only to `ghcr.io/bronto-community/notel-demo`, with no
  Docker Hub target.
- **Envoy access log**: replace the OTel access logger with
  `envoy.access_loggers.stdout`, using the same format.
- **Makefile**: `start` and `start-minimal` replace the old `*-no-o11y`
  targets. No aliases are kept.
- **Changelog**: upstream `CHANGELOG.md` and `.chloggen/` are left untouched
  and allowlisted in the residual scan.

## Transitive dependencies

- **Rule**: transitive, vendored or third-party OTel is accepted only if it
  stays silent. Silent means no SDK is registered, nothing is exported, and
  no connections are made. Such cases are documented as "dormant library
  instrumentation" in BREAKING.md. Do not replace or fork providers to get
  rid of it.
- **Known dormant cases**, re-checked on every sync:
  - Go `open-feature/go-sdk-contrib/providers/flagd`, which pulls in
    otelconnect, otel and `go.opentelemetry.io/auto/sdk` through
    `flagd/core`.
  - Java `dev.openfeature.contrib.providers:flagd`, which pulls in
    `opentelemetry-api`. Never call `withGlobalTelemetry(true)` or
    `.openTelemetry(...)`.
  - Python `fastmcp`, which pulls in `opentelemetry-api` (agent and mcp).
    `mcp` 2.x would also pull it in.
  - Next.js, which vendors `next/dist/compiled/@opentelemetry/api`.
  - kafka-clients, librdkafka and the Kafka broker image, which ship
    OTLP protobuf classes for KIP-714 client metrics. These are inactive
    unless broker subscriptions are configured. The broker jar is kept.
  - The `ghcr.io/open-feature/flagd` image, which embeds the full OTel
    stack. **It is not silent.** It always builds an OTLP trace exporter,
    which defaults to `https://localhost:4318`. The maintainer accepted it
    as a known non-silent exception. Do not add `OTEL_TRACES_EXPORTER=none`,
    and do not patch the image. It is allowlisted in
    `notel/verify/silence-allowlist.txt`; see BREAKING.md #23.
  - agent `langsmith` (through langchain-core), which has its own tracing
    and an OTel integration. It is off unless `LANGSMITH_TRACING` or
    `LANGSMITH_OTEL_ENABLED` is set.
  - load-generator Locust, which has a built-in `--otel` option. It is inert
    because no OTel SDK is installed.
  - The frontend-tests Cypress image, which bundles the OTel SDK and an
    OTLP exporter. It is test-only tooling.
  - Envoy (frontend-proxy), which has the OTel tracer and access logger
    built in. It is silent because neither is configured.
  - Alpine `libgrpc` (currency), which embeds xDS proto descriptors that
    mention OpenTelemetry. No OTel plugin is linked or registered.
    `grpcpp_otel_plugin.pc` is removed in the Dockerfile.
- **Proof of silence**: verification runs a canary listener that stands in
  for `otel-collector` on 4317 and 4318, plus common metrics ports, using
  `notel/verify/` (a compose overlay used only during verification, never
  shipped). The canary must record zero connections while the full stack
  and load run. Verification also scans container logs for exporter and
  OTLP errors.
