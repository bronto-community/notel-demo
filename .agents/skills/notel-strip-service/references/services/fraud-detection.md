# fraud-detection (Kotlin)

## Observability removed
- `src/main/kotlin/frauddetection/main.kt`:
  - `FlagdOptions.withGlobalTelemetry(true)`.
  - The "via baggage?" TODO in `getFeatureFlagValue`.
  - "may emit no telemetry" in the `AUTO_OFFSET_RESET_CONFIG` comment. The
    comment now ends at "silently drops those orders."
- `build.gradle.kts`: `opentelemetry-api`, `opentelemetry-sdk` and
  `opentelemetry-extension-annotations`.
- `Dockerfile`: the `OTEL_JAVA_AGENT_VERSION` ARG, the javaagent `ADD`, and
  `-javaagent` in `JAVA_TOOL_OPTIONS`.
- `src/main/resources/log4j2.xml`: `trace_id`, `span_id` and `trace_flags`
  removed from the pattern.

## Behavior-preserving replacements
- `JAVA_TOOL_OPTIONS="-Xmx180m"` is kept without the agent.
- The flag evaluation context still uses a random UUID `session`. It never
  came from baggage, so nothing changes.
- The log pattern change is BREAKING.md #17.

## Traps
- The code never called the OTel API directly, so the direct deps were only
  there for the agent and annotations. Removing them needs no code changes.
- `group = "io.opentelemetry"` in `build.gradle.kts` is the Maven group
  coordinate, not observability. It is kept (branding) and needs an allowlist
  entry.
- `io.grpc.netty...TcpMetrics` in the startup log is grpc-netty internal,
  not observability.

## Dormant transitive OTel
- `dev.openfeature.contrib.providers:flagd:0.14.2` ->
  `io.opentelemetry:opentelemetry-api:1.63.0` -> `opentelemetry-context`,
  `opentelemetry-common`. These are shaded into the fat jar. Nothing calls
  `withGlobalTelemetry(true)` or `.openTelemetry(...)`.
- `org.apache.kafka:kafka-clients:4.3.1` embeds shaded OTLP protobuf classes
  for KIP-714 client metrics. They are inactive unless broker subscriptions
  are configured (DECISIONS.md known case).

## Verify
- `docker build -f src/fraud-detection/Dockerfile .` (repo root as the
  context).
- `gradle dependencies --configuration runtimeClasspath` in
  `gradle:9.7.1-jdk17`, with `pb/` copied to `src/main/proto`, then grep
  `opentelemetry|prometheus`. Expect only the three flagd-transitive
  artifacts.
- Smoke test: `docker run -e KAFKA_ADDR=... <image>` shows only
  `Picked up JAVA_TOOL_OPTIONS: -Xmx180m`.
- There are no unit tests (there is a `kotlin("test")` dependency but no
  `src/test`).
