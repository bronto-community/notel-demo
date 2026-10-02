# checkout (Go)

## Observability removed

- main.go: resource detectors, OTLP HTTP trace, metric and log providers and
  their shutdowns, the TraceContext+Baggage propagator, `otelslog` logger,
  `runtime.Start`, the `otelhooks.NewTracesHook()` OpenFeature hook,
  `otelhttp.NewTransport` (now `&http.Client{}`, which uses
  `http.DefaultTransport` as before), otelgrpc server and client stats handlers.
- main.go `PlaceOrder`: span attributes, events and `RecordError` defer; the
  `emitRawPii` attributes; the `synthetic_request` baggage check.
- main.go `prepareOrderItemsAndShippingQuoteFromCart`: the manual span, plus the
  `totalCart`/`shippingCostFloat` computation that only fed span attributes.
- main.go `sendToPostProcessor`: the Kafka producer span, its attributes and
  status; `createProducerSpan`, which injected `traceparent`/`baggage` headers
  into Kafka records (see BREAKING.md, "Kafka wire format").
- flags.json, flags/flags_gen.go: the `emitRawPii` flag.
- go.mod/go.sum: all direct `go.opentelemetry.io/*` and
  `go-sdk-contrib/hooks/open-telemetry` requirements (`go mod tidy`).

## Behavior-preserving replacements

- `var logger = slog.New(slog.NewTextHandler(os.Stdout, nil))` at package level
  plus `slog.SetDefault(logger)` in `main` (BREAKING.md #2). Package-level init
  removes the old nil-logger window before provider setup. The sarama logger
  in kafka/producer.go receives this logger, so it now prints to stdout too.

## Traps

- `flags_gen.go` is generated. Regenerate it, do not hand-edit:
  `docker run --rm -v "$PWD":/w -w /w golang:<Dockerfile version> sh -c 'go install github.com/open-feature/cli/cmd/openfeature@v0.4.0 && openfeature generate -o flags --package-name flags go'`
  from `src/checkout`. v0.4.0 reproduces the upstream file byte for byte
  (header `CLI version: dev`).
- `flags.json` ends with a blank line upstream. Keep it to avoid diff noise.
- `PlaceOrder` declared `var err error` only for the `RecordError` defer. The
  later `:=` assignments still compile once it is removed.
- `src/flagd/demo.flagd.json` also defines `emitRawPii`. That file belongs to
  the flagd owner, not this service.
- The Go module path `github.com/open-telemetry/opentelemetry-demo/...` hits
  the residual scanner. It is upstream naming, not observability.

## Dormant transitive OTel

- `open-feature/go-sdk-contrib/providers/flagd` -> `flagd/core` ->
  `go.opentelemetry.io/otel` (+ `otel/metric`, `otel/trace`,
  `go.opentelemetry.io/auto/sdk`), and flagd `service/rpc` ->
  `connectrpc.com/otelconnect`. The otelconnect interceptor is only added with
  `flagd.WithOtelInterceptor(true)` and there is no env var for it. Never set it.
- `otel/sdk` and `otel/sdk/metric` remain in go.mod as indirect only because
  of `otelconnect`'s tests (`go mod why -m`). They are not linked.

## Verify

- `docker run --rm -v "$PWD/src/checkout":/w -w /w golang:<ver>-bookworm sh -c 'go mod tidy && go vet ./... && go test ./...'`
- `docker build --load -t notel-test/checkout -f src/checkout/Dockerfile .`
- `go version -m <extracted binary> | grep -i otel` lists only otelconnect,
  auto/sdk, otel, otel/metric and otel/trace.
- Running the image prints `time=... level=INFO msg="starting to listen on tcp: ..."` to stdout.
