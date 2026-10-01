# product-catalog (Go)

## Observability removed

- main.go: `otelslog` logger set in `init()`; `otelconf.NewSDK` (from
  `OTEL_CONFIG_FILE`) with global provider and propagator registration and its
  shutdown; `otelsql.Open` with SQLCommenter and span options;
  `otelsql.RegisterDBStatsMetrics` and its `Unregister`; the
  `otelhooks.NewTracesHook()` hook; `runtime.Start`; the otelgrpc server stats
  handler; span attributes, events and statuses in `ListProducts`,
  `GetProduct` and `SearchProducts`.
- opamp.go, opamp_test.go: deleted, with the `prepareOpAMPIdentity` and
  `startOpAMPClient` call sites in main.go and the Dockerfile `COPY` of opamp.go.
- README.md: the "Database Calls Instrumentation" (otelsql) section.
- go.mod/go.sum: `XSAM/otelsql`, `opamp-go`, `hooks/open-telemetry` and all
  direct `go.opentelemetry.io/*` requirements (`go mod tidy`).

## Behavior-preserving replacements

- `logger = slog.New(slog.NewTextHandler(os.Stdout, nil))` in the package `var`
  block (BREAKING.md #2).
- `sql.Open("postgres", connStr)` with the `lib/pq` driver import kept. Queries
  no longer carry sqlcommenter comments (BREAKING.md, "SQL text").

## Traps

- `main` declares `ctx := context.Background()` and later re-declares it with
  `ctx, cancel := signal.NotifyContext(...)`. The first `ctx` is still used by
  `triggerLockContentionLoop`, so keep it after removing the SDK code.
- The `err` variable was first declared by the OpAMP call. After removing it,
  `provider, err := flagd.NewProvider()` declares it.
- Upstream exited on a bad or missing OTel config file. That exit is gone
  (BREAKING.md, "Startup"). The DB-init exit is kept.
- The module path is `github.com/opentelemetry/opentelemetry-demo/...` (no
  hyphen, unlike checkout) and hits the residual scanner. It is upstream
  naming, not observability.

## Dormant transitive OTel

- Same chain as checkout: flagd provider -> `flagd/core` -> `otel`,
  `otel/metric`, `otel/trace`, `auto/sdk`; flagd `service/rpc` -> `otelconnect`
  (interceptor off by default, never enable it). `otel/sdk` is in go.mod only
  through otelconnect's tests and is not linked.

## Verify

- `docker run --rm -v "$PWD/src/product-catalog":/w -w /w golang:<ver>-bookworm sh -c 'go mod tidy && go vet ./... && go test ./...'` (no test files remain)
- `docker build --load -t notel-test/product-catalog -f src/product-catalog/Dockerfile .`
- `go version -m <extracted binary> | grep -i otel`, as for checkout.
- Running the image without a database prints
  `level=ERROR msg="Error initializing database: ..."` to stdout and exits 1.
