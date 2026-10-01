# accounting (.NET / C#)

## Observability removed

- `Consumer.cs`: the `ActivitySource("Accounting.Consumer")`, the
  `StartActivity("order-consumed")` around each consume, and
  `using System.Diagnostics;`.
- `Helpers.cs`: the `CORECLR_` and `OTEL_` prefixes in the startup env dump
  (`DOTNET_` and `KAFKA_` kept).
- `Accounting.csproj`, `Directory.Packages.props`:
  `OpenTelemetry.AutoInstrumentation`.
- `Dockerfile`: the `/var/log/opentelemetry/dotnet` setup, the `chown` of
  `instrument.sh`, the `USER root` / `USER app` switch that existed only for
  those steps, and `OTEL_DOTNET_AUTO_TRACES_ADDITIONAL_SOURCES`. The
  ENTRYPOINT is now `["dotnet", "Accounting.dll"]`. The base images are
  unchanged.

## Behavior-preserving replacements

- `Microsoft.Extensions.Hosting` 10.0.10 added as a direct
  `PackageReference`, pinned to the same release train as the existing
  `Microsoft.Extensions.Logging` 10.0.10. Before, `Host` and
  `BackgroundService` came from the `Microsoft.AspNetCore.App` shared
  framework, which `OpenTelemetry.Instrumentation.AspNetCore` (via
  AutoInstrumentation) pulled in as a transitive `FrameworkReference`.
  Logging still goes to the console through `Host.CreateDefaultBuilder`.

## Traps

- Removing `OpenTelemetry.AutoInstrumentation` breaks the build with CS0234
  and CS0246 (`Microsoft.Extensions.Hosting`, `BackgroundService`), because
  the hosting assemblies were never referenced directly.
- A direct `<FrameworkReference Include="Microsoft.AspNetCore.App" />` also
  fixes it, but it triggers NU1510 (warnings are errors) on the now-redundant
  `Microsoft.Extensions.Logging` reference. That is why the Hosting package is
  used instead.
- `instrument.sh` was not in the repo. The AutoInstrumentation package put it
  into the publish output. Once the package is removed, the old ENTRYPOINT and
  `chown` would fail.

## Dormant transitive OTel

- `Confluent.Kafka` -> `librdkafka.redist` 2.15.0, which embeds nanopb OTLP
  protos for KIP-714 client metrics. Known dormant case in DECISIONS.md.
  `dotnet list package --include-transitive` shows no `OpenTelemetry.*`
  packages.

## Verify

- `docker build -f src/accounting/Dockerfile .` (repo-root context, per
  compose.full.yaml).
- `dotnet list package --include-transitive` in the
  `mcr.microsoft.com/dotnet/sdk:10.0` image; grep for `OpenTelemetry`.
- `docker run -e KAFKA_ADDR=127.0.0.1:1 <image>` must print
  "Accounting service started", the env dump without `OTEL_` entries, and
  "Application started".
- `ls /app` in the image shows no `instrument.sh` or OTel files.
