# cart (.NET / C#)

## Observability removed

- `src/Program.cs`: the `OpenTelemetry.*` and `OpenFeature.Hooks` usings;
  `AddOpenTelemetry(... AddOtlpExporter())` on logging (`AddConsole` kept);
  the OpenFeature `MetricsHook` and `TraceEnricherHook`; the
  `serviceInstanceId` and resource builder; `AddOpenTelemetry()` with
  tracing (Redis, AspNetCore, GrpcClient, Http, OTLP) and metrics (Process,
  Runtime, AspNetCore, exemplars, OTLP); the OpAMP client (start, stop and
  the `OPAMP_SERVER_*` reads); the
  `StackExchangeRedisInstrumentation.AddConnection` line.
- `src/OpAmpClientSetup.cs`: deleted.
- `src/services/CartService.cs`: the `Activity.Current` tags, events,
  `AddException` and `SetStatus` calls. The `catch (RpcException) { ...;
  throw; }` blocks only recorded on the span, so they were removed along with
  the item-count loop that only fed `demo.cart.items.count`.
- `src/cartstore/ValkeyCartStore.cs`: the `Meter`, the
  `demo.cart.add_item.latency` and `demo.cart.get_cart.latency` histograms,
  the unused `ActivitySource`, and the `Stopwatch` plus `finally { Record }`
  code. The `catch` blocks that wrap errors in `RpcException(FailedPrecondition)`
  are kept.
- `src/services/HealthCheckService.cs`: the unused `using OpenFeature.Hooks;`.
- `src/cart.csproj`, `Directory.Packages.props`: all 11 `OpenTelemetry.*`
  packages, including `OpenTelemetry.OpAmp.Client`.

## Behavior-preserving replacements

- `Program.cs`: `app.Services.GetRequiredService<ICartStore>();` right after
  `builder.Build()` (BREAKING.md #10). The removed instrumentation line
  resolved the singleton eagerly, which connects to Valkey at startup. Without
  this line, the first gRPC call would make the connection. Verified: with an
  unreachable `VALKEY_ADDR` the container still fails at startup with
  "Wasn't able to connect to redis".
- The readiness check `oteldemo.CartService` and the `failedReadinessProbe`
  flag are unchanged.

## Traps

- `MetricsHook` and `TraceEnricherHook` live in the `OpenFeature` package
  itself (`OpenFeature.Hooks` namespace), not in an OTel package. Removing the
  OTel packages does not break the build if they stay, so they have to be
  removed explicitly.
- `ValkeyCartStore.GetConnection()` is now unused. It dates from the initial
  code donation and is not observability code, so it was kept.
- The Dockerfile `test` stage runs `tests/cart.tests.csproj` and gates the
  release build on it, so `docker build` also runs the unit tests.
- The default buildx builder in this setup does not load images. Use
  `--load` to run the image locally.

## Dormant transitive OTel

- none. `dotnet list package --include-transitive` for `src/cart.csproj` and
  `tests/cart.tests.csproj` shows no `OpenTelemetry.*` or OpAMP packages.
  `OpenFeature` ships `MetricsHook` and `TraceEnricherHook`
  (`System.Diagnostics.Metrics` and `Activity`) but they are not registered.

## Verify

- `docker build -f src/cart/src/Dockerfile .` (repo-root context, per
  compose.yaml); the test stage reports `Passed: 3`.
- `dotnet list src/cart.csproj package --include-transitive` in the
  `mcr.microsoft.com/dotnet/sdk:10.0` image; grep for `OpenTelemetry|OpAmp`.
- `docker run -e VALKEY_ADDR=127.0.0.1:1 <image>` must fail at startup on
  the Valkey connect.
