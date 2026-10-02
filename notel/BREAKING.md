# Breaking and behavior changes from removing observability

Each item records the coupling found upstream, what notel does about it, and
whether it could be raised upstream. Status is one of: `open` (not fixed),
`fixed` (handled in notel), or `n/a` (pure removal, recorded for reference).

## Open items

### 1. Ad flag targeting depends on OTel baggage (`open`, upstream candidate)

- **Where**: `src/ad/.../AdService.java` (`Baggage.fromContextOrNull`), set by
  `src/frontend/gateways/Api.gateway.ts`.
- **What**: `session.id` (and `enduser.id`) travel from the frontend to ad
  only as W3C baggage, carried by OTel propagation and the Java agent. Ad
  uses them as the OpenFeature targeting key and the `session` context for
  `adHighCpu`, `adFailure` and `adManualGc`.
- **History**: introduced on purpose in upstream #1502 (2024-04, "Pass
  Session ID through baggage ... to consume it in feature flag context") and
  extended in #3366 (2026-05, `enduser.id`).
- **Impact in notel**: ad flags are evaluated with an empty context. The
  shipped `demo.flagd.json` has no targeting rules for these flags, so there
  is no visible effect unless someone adds per-session or fractional rules.
- **Fix options**: add an explicit `session_id` field to `AdRequest` in
  `pb/demo.proto`, or send a plain gRPC metadata header.
- **Upstream angle**: business logic (flag evaluation) silently depends on
  the telemetry SDK being present. Upstream may consider this an intended
  showcase of baggage.

### 23. flagd dials localhost:4318 without any OTel configuration (`accepted`, upstream candidate for open-feature/flagd)

- **Where**: the `ghcr.io/open-feature/flagd:v0.16.0` image (the flagd
  service).
- **What**: once `OTEL_EXPORTER_OTLP_ENDPOINT` is removed, flagd falls back
  to `https://localhost:4318`. The silence check counted 163 SYNs in 12
  minutes: one every ~5 s under OFREP load, about one per 32 s when idle.
  `OTEL_SDK_DISABLED=true` and `OTEL_{TRACES,METRICS,LOGS}_EXPORTER=none` do
  not stop it. This contradicts `flagd --help`, which says nothing is
  exported without `--otel-collector-uri`.
- **Impact**: connection attempts to a port nobody listens on. Nothing is
  exported, but the stack is not silent.
- **Cause** (flagd v0.16.0; v0.17.0 behaves the same):
  `core/pkg/telemetry/builder.go:79` always calls
  `autoexport.NewSpanExporter`. With `OTEL_TRACES_EXPORTER` unset, autoexport
  defaults to `otlp` over http/protobuf, which means
  `https://localhost:4318`. Spans come from the OFREP `otelhttp` handler and
  the always-on `otelconnect` interceptor. The batch processor flushes every
  5 s. `OTEL_SDK_DISABLED` is ignored, because Go autoexport doesn't
  implement it. The behavior was introduced in #1812 (v0.13.0). No existing
  upstream issue was found.
- **Options considered**:
  - Set `OTEL_TRACES_EXPORTER=none`. Verified to give 0 attempts.
  - Use a patched flagd image.
  - Accept it.
- **Decision**: accepted as a known non-silent exception. The silence check
  allowlists exactly `flagd` -> `127.0.0.1:4318`. Revisit if flagd fixes the
  default upstream.
- **Memory** (investigated 2026-10-02): the always-on exporter adds about
  3-5 MiB, the same as a working exporter. It is not why flagd sits at its
  75Mi limit; see "Upstream issues noticed".
- **Upstream**: the `--otel-collector-uri` help text and docs ("If unset ...
  traces will not be exported") contradict the behavior. This is worth an
  issue on open-feature/flagd, and the issue text must be written by a
  human.

## Fixed in notel (behavior preserved by explicit replacement)

| # | Service | Coupling | notel fix |
| --- | --- | --- | --- |
| 2 | checkout, product-catalog | `slog` default and sarama logger are otelslog-only; no stdout logs | slog TextHandler on stdout |
| 3 | currency | all logs go through the OTel C++ logger only | `std::cout` / `std::cerr` |
| 4 | shipping | `tracing_subscriber` (incl. stdout fmt layer) is initialized inside the OTel init | init the fmt subscriber in `main` |
| 5 | recommendation | `main` logger has only the OTLP handler; stdout depended on `opentelemetry-instrument` | `logging.basicConfig(level=INFO)` |
| 6 | load-generator | with `--skip-log-setup` the only root handler is the OTel LoggingHandler | `logging.basicConfig` |
| 7 | quote | Monolog's only handler is the OTel handler | Monolog StreamHandler on stdout |
| 8 | recommendation | startup crashes without `OTEL_SERVICE_NAME` (`must_map_env`) | drop the lookup |
| 9 | flagd-ui | prod startup raises without `OTEL_EXPORTER_OTLP_ENDPOINT` | drop the requirement |
| 10 | cart | the Valkey connection is made eagerly only as a side effect of `AddRedisInstrumentation` | explicit `GetRequiredService<ICartStore>()` at startup |
| 11 | react-native-app | splash screen waits for `tracerLoaded` | gate on fonts only |
| 12 | frontend | per-request access logs live inside the tracing middleware | slim logging-only wrapper |
| 13 | kafka | `KAFKA_OPTS` references the Java agent jar; the broker fails if only the jar is removed | remove both together |
| 14 | quote | the `catch` in `calculateQuote` records on the span and returns 0.0 | keep the catch and the 0.0 return |
| 15 | email | `error do ... end` return value becomes the response body | explicit body |
| 16 | payment | logger mixin reads `service.name` from `OTEL_SERVICE_NAME` | hardcode it or drop the field |
| 17 | ad, fraud-detection | log4j pattern prints agent-filled `trace_id`/`span_id` MDC | remove those fields from the pattern |

| 18 | accounting | `Host`/`BackgroundService` came from the ASP.NET Core framework, which was only pulled in by `OpenTelemetry.AutoInstrumentation`; without it the build fails (CS0234/CS0246) | explicit `Microsoft.Extensions.Hosting` (upstream candidate: hidden build dependency) |
| 19 | react-native-app | OTel typings added Node types globally (`/// <reference types="node"/>`); without them, `tsc` reports ~80 `Buffer` errors in `protos/demo.ts` | explicit `@types/node` devDependency plus `"types": ["node"]` in tsconfig.json (TS 6 defaults `types` to `[]`) (upstream candidate) |
| 20 | email | removing the `error do ... end` block changes the 500 body to `<h1>Internal Server Error</h1>` | `error do "" end` keeps the body empty |
| 21 | quote | the `return` inside `finally` also swallows `TypeError`, which is what makes a request with no body return 0 | keep the `finally` |
| 22 | load-generator | the 2 s browser waits look like trace-export waits, but they keep the page alive for the add-to-cart and currency requests | waits kept |

## Pure removals with an observable difference (`n/a`)

- **Log format**: recommendation and load-generator use the stdlib default
  format (`INFO:<logger>:<msg>`). Before, they used the OTel-instrumented
  format with trace IDs. Messages and levels are unchanged.
- **Log lines**: OTel- and metrics-specific startup lines are gone (e.g.
  "Prometheus metrics endpoint started", "no baggage found in context",
  "Shutdown OpenTelemetry SDK", "Successfully configured OTel").
- **react-native-app**: the session is no longer saved before every API
  call; it's saved only by calls that use it.

- **Kafka wire format**: checkout no longer adds `traceparent`/`baggage`
  headers to Kafka records. No consumer reads them.
- **SQL text**: product-catalog no longer appends sqlcommenter
  `/*traceparent=...*/` comments to queries.
- **Ports and routes**:
  - ad `/metrics` (`AD_PROMETHEUS_PORT`) is gone.
  - frontend-proxy `/otlp-http`, `/jaeger`, `/grafana`, `/opamp`, `/telemetry`
    and `/profiles` are gone.
- **Postgres**: the `monitoring_user` role and `pg_stat_statements` are
  removed. They existed only for the collector's postgresql receiver.
- **Flags**: `emitRawPii` is removed. The `synthetic_request` marker is
  removed. The failure-scenario flags are kept but are no longer observable
  out of the box.
- **Tests**: `test/telemetry` is removed. Only the frontend Cypress tests
  remain.
- **Startup**: product-catalog no longer exits on a bad or missing OTel config
  file.
- **Dashboards and metrics**: custom metrics such as `demo.payment.transactions`
  and `demo.ad.requests` no longer exist.

## Dormant library instrumentation

These remain on purpose under the transitive rule in DECISIONS.md. They make
no API calls of their own, and they become **active as soon as an SDK or
agent is added**. Keep that in mind when you compare instrumented runs: spans
from these libraries are library instrumentation, not demo code.

| Where | Source | Becomes visible with |
| --- | --- | --- |
| checkout, product-catalog | flagd Go provider -> `flagd/core` evaluator -> otel API, `go.opentelemetry.io/auto/sdk`, otelconnect (inactive unless `WithOtelInterceptor`) | Go eBPF auto-instrumentation (picks up API spans through auto/sdk) |
| ad, fraud-detection | flagd Java provider -> `opentelemetry-api` (used only if handed an OpenTelemetry instance) | the Java agent, if the provider is wired up |
| agent, mcp | `fastmcp` -> `opentelemetry-api` | any Python SDK or auto-instrumentation |
| frontend | Next.js vendored `@opentelemetry/api` (built-in Next spans) | Node SDK / `--require` auto-instrumentation |
| fraud-detection, accounting, kafka | KIP-714 OTLP protobuf classes in kafka-clients, librdkafka and the broker | only with broker client-metrics subscriptions |
| flagd | official image embeds the full OTel stack | only when configured with an OTLP endpoint |
| frontend-proxy | Envoy OTel tracer and access logger built in | only when configured |
| currency | Alpine libgrpc xDS descriptors mention OpenTelemetry | never (no plugin linked) |
| recommendation | grpcio xDS descriptors include `opentelemetry.proto` | never (no plugin linked) |
| agent, chatbot, mcp | Starlette's opt-in `OpenTelemetryMiddleware` | only if app code adds the middleware |

## Upstream issues noticed (unrelated to observability, left untouched)

- frontend `npm run lint` is broken: Next 16 dropped `next lint`, and ESLint 9
  rejects `.eslintrc`.
- The agent replays VCR cassettes with `record_mode="new_episodes"` (upstream
  `patch_vcr.py`), so a prompt with no recorded match goes out to the real
  LLM endpoint (`https://local-llm.com` in the default config). This is
  not telemetry, but it is real outbound traffic.
- react-native-app `tsc --noEmit` already reports 3 errors in the generated
  `protos/demo.ts`.
- ad and fraud-detection print `SLF4J(W): No SLF4J providers were found`.
  Upstream `3.1.0-ad` prints the same, so it predates notel.
- 5 of the 9 frontend Cypress tests fail, and neither the specs nor the code
  under test differ from upstream:
  - `compose.tests.yaml` sets `baseUrl` to `frontend:8080` instead of the
    proxy, so `/feature`, `/images` and `/flagservice` return 404.
  - `Checkout.cy.ts` expects `data-cy=checkout-item`, which the confirmation
    page never renders.
  - The productCatalogFailure test fires before the flag reloads (~2 s).
  - The Home corrupted-session spec reads `getSession()` before the visit.
  - The ProductDetail "picture missing" test still renders the picture.
- Memory limits and `GOMEMLIMIT` collide in upstream and notel alike. A
  side-by-side run on 2026-10-02 used stock upstream 3.1.0 and notel, each
  fresh for 30 minutes on the same machine (one run each):
  - flagd: `GOMEMLIMIT=60MiB` inside a 75Mi limit leaves too little room for
    the ~48 MiB of the flagd binary that stays resident. Both runs sat at
    the limit, with 486 (notel) and 500 (upstream) limit-hit events, and
    no OOM kills.
  - Go services at 20Mi with `GOMEMLIMIT=16MiB`: upstream product-catalog
    thrashed hard (5.2M limit hits and 6.4M major faults in 31 minutes, at
    208% CPU), which caused 504s. notel checkout logged 1.09M limit hits in
    5 minutes.
  - `docker stats` and `kubectl top` leave out file cache, so they hide all
    of this: flagd looks like 34-70 MiB while it is pinned at its limit.
    The symptom is CPU and latency, not crashes. Under VM memory pressure
    it becomes a stall, as in the kind run.
  - Related upstream history: #2126 (flagd OOMKilled, closed 2025-10-22
    after `GOMEMLIMIT`), #2148 (compose `GOMEMLIMIT`, merged), and #2564 (k8s
    `GOMEMLIMIT`, closed unmerged). No open issue as of 2026-10-02.
  - Decision: notel keeps the upstream limits, so that resource comparisons
    with upstream stay fair. Only `notel/k8s/kind_verify.sh` raises flagd to
    150Mi for the verification cluster. Upstream candidate (the issue text
    must be written by a human).
