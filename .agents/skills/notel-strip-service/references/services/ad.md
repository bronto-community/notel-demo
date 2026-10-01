# ad (Java)

## Observability removed

- `src/main/java/oteldemo/AdService.java`:
  - All `io.opentelemetry.*` and `io.prometheus.*` imports.
  - The Prometheus `HTTPServer` field, the `AD_PROMETHEUS_PORT` env read, the
    server start, the "Prometheus metrics endpoint started" log, and the stop
    in `stop()`.
  - The `demo_ad_served_total` Prometheus counter and its `inc()` calls.
  - The `GlobalOpenTelemetry` tracer and meter, the `demo.ad.requests`
    counter, and the `demo.ad.request_type`/`demo.ad.response_type` attribute
    keys.
  - The `AdRequestType`/`AdResponseType` enums and their assignments. They
    only fed span attributes and the counter.
  - Every `Span.current()` `setAttribute`, `addEvent` and `setStatus` call.
  - `@WithSpan`/`@SpanAttribute` on `getAdsByCategory`.
  - The manual `getRandomAds` span and its `makeCurrent` try/finally. The
    loop body is kept.
  - `FlagdOptions.withGlobalTelemetry(true)` and the "flagd instance with
    OpenTelemetry" comment.
  - The baggage read of `session.id`/`enduser.id` and the "no baggage found in
    context" log. Flags are now evaluated with an empty `MutableContext`
    (BREAKING.md #1).
- `build.gradle`: the OTel and instrumentation BOMs, `opentelemetry-api`,
  `opentelemetry-sdk`, `opentelemetry-instrumentation-annotations`, both
  `io.prometheus` deps, and the `opentelemetryVersion`,
  `opentelemetryInstrumentationVersion` and `prometheusMetricsVersion`
  variables.
- `Dockerfile`: the `OTEL_JAVA_AGENT_VERSION` ARG, the javaagent `ADD`,
  `-javaagent` in `JAVA_TOOL_OPTIONS`, and the `AD_PROMETHEUS_PORT` ARG and
  EXPOSE.
- `src/main/resources/log4j2.xml`: `trace_id`, `span_id` and `trace_flags`
  removed from the pattern.
- `README.md`: the "Custom metrics: bridging Prometheus to OpenTelemetry"
  section.

## Behavior-preserving replacements

- `JAVA_TOOL_OPTIONS="-Xmx200m"` is kept without the agent.
- log4j2 still logs to stdout with the same messages. Only the MDC fields
  that the agent filled are gone (BREAKING.md #17).
- The `catch (StatusRuntimeException)` in `getAds` is kept. It still logs at
  WARN and calls `responseObserver.onError`.

## Traps

- The `TARGETED`/`RANDOM` enums look like business logic but existed only for
  telemetry. Removing them does not change the response.
- The shared working tree was reset by another process during the first
  run, which reverted the edits. Keep a patch backup, and re-check
  `git diff -- src/ad` before reporting.
- `SLF4J(W): No SLF4J providers were found` at startup comes from grpc and
  flagd. No SLF4J binding is declared, so it is not caused by the strip.
- Remaining residual hits are product names: `opentelemetry-demo-ad`
  (`settings.gradle` rootProject name, the Dockerfile ENTRYPOINT path and the
  README), plus "`opentelemetry-demo`" in the README and in a `build.gradle`
  comment. These need allowlist entries as branding.

## Dormant transitive OTel

- `dev.openfeature.contrib.providers:flagd:0.14.2` ->
  `io.opentelemetry:opentelemetry-api:1.63.0` -> `opentelemetry-context`,
  `opentelemetry-common`. These ship in `build/install/.../lib`. Nothing
  calls `withGlobalTelemetry(true)` or `.openTelemetry(...)`, and no SDK is
  on the classpath, so `GlobalOpenTelemetry` is a no-op.

## Verify

- `docker build -f src/ad/Dockerfile .` (repo root as the context).
- `./gradlew dependencies --configuration runtimeClasspath -PprotoSourceDir=<pb>`
  in `eclipse-temurin:24.0.2_12-jdk`, then grep `opentelemetry|prometheus`.
  Expect only the three flagd-transitive jars.
- Smoke test: `docker run -e AD_PORT=9555 <image>` logs
  "Ad service started, listening on 9555", and the JVM shows only
  `Picked up JAVA_TOOL_OPTIONS: -Xmx200m`.
- There are no unit tests.
