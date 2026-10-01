# shipping (Rust)

## Observability removed

- `src/telemetry_conf.rs`: deleted (OTLP tracer, meter and logger providers,
  resource detectors, the propagator, the tracing bridge and `OtelGuard`).
- `src/main.rs`: `init_otel`, the "Successfully configured OTel" log, the
  `RequestTracing` and `RequestMetrics` middleware and `otel_guard.shutdown()`.
  `main` now ends with `.run().await`.
- `src/shipping_service/quote.rs`: the `demo.shipping.items_shipped` counter,
  `get_active_span` with its event and attribute (it now calls
  `create_quote_from_float` directly) and `.trace_request()` on the awc client.
- `Cargo.toml`: `opentelemetry`, `opentelemetry_sdk`, `opentelemetry-otlp`,
  `opentelemetry-instrumentation-actix-web`, `opentelemetry-appender-tracing`
  and `opentelemetry-resource-detectors`.
- `Cargo.lock`: `cargo update --workspace` in `rust:1.98.0`. It only removes
  packages, including 19 crates (reqwest, tower-http and others) that are
  now unused, and the versioned `base64 0.x` references become `base64`
  (0.22.1 on the first strip, 0.23.1 at 7ea09b86). Nothing is bumped.
  On a sync where upstream changed `Cargo.lock`, the cherry-pick conflicts:
  take upstream's lock and rerun `cargo update --workspace`, then compare
  the `[[package]]` name/version sets with upstream's lock (only removals).

## Behavior-preserving replacements

- `tracing_subscriber::fmt().with_writer(std::io::stdout).with_env_filter(EnvFilter::new("info")).init()`
  at the top of `main` (BREAKING.md #4). It matches the old stdout fmt layer,
  which had a hardcoded `info` filter and ANSI on by default. `tracing` stays
  as the log facade, per DECISIONS.md.

## Traps

- Initialize the subscriber before anything logs. The flagd provider logs
  connection retries at WARN during `FlagdProvider::new`.
- The service blocks at startup until flagd is reachable. This is upstream
  behavior. For a local run, start `ghcr.io/open-feature/flagd` with
  `src/flagd/demo.flagd.json`.

## Dormant transitive OTel

- none (`cargo tree -i opentelemetry` reports no match. `cargo tree -e all`
  has no opentelemetry, otel or prometheus crates)

## Verify

- `cargo test --locked` in `rust:1.98.0` with `protobuf-compiler`: 7 passed.
- `docker build --load -t notel-test/shipping -f src/shipping/Dockerfile .`
- On one network with quote and flagd: `POST /get-quote` with 3 items returns
  `{"cost_usd":{"currency_code":"USD","units":26,"nanos":970000000}}`,
  `POST /ship-order` returns a tracking id, and `/health` returns 200. The
  logs reach stdout through the fmt subscriber.
