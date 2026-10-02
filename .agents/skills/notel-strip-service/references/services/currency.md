# currency (C++)

## Observability removed

- `src/logger_common.h`, `src/meter_common.h`, `src/tracer_common.h`: deleted
  (OTLP gRPC exporters, tracer/meter/logger provider init, `GrpcServerCarrier`
  for W3C context extraction from gRPC metadata).
- `src/server.cpp`: OTel includes, `using namespace opentelemetry::*`, namespace
  aliases, `eventName()`/`EventId`, `<grpcpp/impl/codegen/string_ref.h>` (only
  used by the carrier), context extraction and server spans with semconv RPC
  attributes, span events and status in `GetSupportedCurrencies` and `Convert`,
  `demo.exchange.from/to` span attributes, the `demo.exchange.conversions`
  counter (`CurrencyCounter`), provider init and shutdown/flush in `main`, and
  the `VERSION` env read (used only for the meter version).
- `src/server.cpp`: `ServerShutdownResult`, `makeServerShutdownResult`,
  `remainingShutdownTimeout` and `shutdown_timeout` (9s) removed. The deadline
  only budgeted provider flushes; `RunServer` now returns `bool`. The gRPC
  server shutdown deadline (`server_shutdown_timeout`, 4s) is kept.
- `CMakeLists.txt`: `find_package(opentelemetry-cpp)`,
  `OPENTELEMETRY_CPP_INCLUDE_DIRS`, `OPENTELEMETRY_CPP_LIBRARIES`.
- `Dockerfile`: `ARG OPENTELEMETRY_CPP_VERSION`, the opentelemetry-cpp clone
  and build, and `git` from the builder packages (only needed for the clone).
  Release stage copies only `/usr/local/bin/currency` instead of all of
  `/usr/local` (which held the static OTel libs and headers). Runtime libs
  (grpc, protobuf, abseil, libstdc++) come from the `base` stage's apk
  packages. The dangling `/usr/lib/pkgconfig/grpcpp_otel_plugin.pc` shipped by
  Alpine `grpc-dev` is removed with `rm -f` (the plugin library itself is not
  in the package).

## Behavior-preserving replacements

- BREAKING.md #3: every `logger->Info/Error` went only to OTLP. Replaced with
  `logInfo` (stdout, `INFO:` prefix) and `logError` (stderr, `ERROR:`
  prefix). Each line is built as one string and flushed, so lines appear
  promptly in `docker logs` (stdout is a pipe, hence block-buffered) and do
  not interleave between gRPC threads. Log record attributes are appended as
  `key=value` (`currency.from`, `currency.to`, `server.address`).
- The shutdown message was printed twice upstream (plain `std::cout` plus the
  OTel logger); it is now one `INFO:` line.
- The `try/catch(...)` in `Convert` returning `Status::CANCELLED` is kept.
  gRPC health service is kept.

## Traps

- `docker build` with the docker-container buildx driver does not load the
  image; use `--load` to run it.
- A SIGTERM sent within milliseconds of container start (before
  `pthread_sigmask`) is dropped because the binary runs as PID 1, and
  `docker stop` falls back to SIGKILL (exit 137). Same as upstream.
- `check_residuals.py` scans the git index, so deleted-but-uncommitted headers
  still show up until the orchestrator commits.
- `pb/demo.proto` is copied into the build; the committed
  `build/generated/proto/*` files contain `oteldemo` split across string
  literals (`.otelde`, `.oteld`), which the `\boteldemo\b` allowlist entry
  does not cover.

## Dormant transitive OTel

- Alpine `grpc-dev`/`grpc` 1.78: `libgrpc.so` embeds upb descriptors for
  `envoy/config/trace/v3/opentelemetry.proto` (xDS config types) and a
  "Export telemetry domains in OpenTelemetry metrics" flag string. No OTel
  plugin is linked (`grpcpp_otel_plugin` is not shipped), nothing is
  registered or exported. Pending listing in DECISIONS.md.
- The `currency` binary itself contains no `opentelemetry`/`otlp` strings.

## Verify

- `docker build --load -f src/currency/Dockerfile -t notel-currency:test .`
  (context is the repo root, per `compose.yaml`).
- `docker run --rm --entrypoint sh notel-currency:test -c 'ldd /usr/local/bin/currency | grep "not found"; find / -xdev -iname "*otel*" -o -xdev -iname "*opentelemetry*"'`
  prints nothing.
- On a shared network, run the image with `CURRENCY_PORT=7001` and call it with
  `fullstorydev/grpcurl -plaintext` (mount `pb/` and `src/currency/proto/`):
  `grpc.health.v1.Health/Check` returns SERVING; `Convert` USD 100 to EUR
  returns 88.456435205; `GetSupportedCurrencies` lists codes. `docker logs`
  shows `INFO: Currency Server started ...`, `INFO: conversion successful ...`,
  `INFO: GetSupportedCurrencies successful`, and on `docker stop`
  `INFO: Received SIGTERM, shutting down Currency Server` with exit 0.
- `python3 notel/scripts/check_residuals.py --paths src/currency`.
