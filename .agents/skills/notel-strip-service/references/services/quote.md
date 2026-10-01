# quote (PHP)

## Observability removed
- `public/index.php`: the `OpenTelemetry\...` uses and the three periodic
  `forceFlush` timers ("workaround for non-async batch processors").
- `app/routes.php`: the `calculate-quote` manual span, its events and
  attributes, the `quotes` counter, `recordException`, and the events on
  `Span::getCurrent()` in the `/getquote` handler.
- `app/dependencies.php`: the OTel Monolog `Handler` on `Globals::loggerProvider()`.
- `composer.json`: `open-telemetry/api`, `sdk`, `exporter-otlp`,
  `opentelemetry-auto-slim`, `detector-container` and
  `opentelemetry-logger-monolog`, plus `guzzlehttp/guzzle` (maintainer
  decision: it was only the PSR-18 HTTP client for the OTLP exporter). There
  is no lockfile, so none is added.
- `Dockerfile`: the `opentelemetry` and `protobuf` PHP extensions. Only the
  OTLP exporter used protobuf: no package in `vendor/` references
  `Google\Protobuf` after the strip.
- `README.md`: the "automatic and manual instrumentation" sentence.

## Behavior-preserving replacements
- Monolog `StreamHandler` on `$loggerSettings['path']` (`php://stdout`,
  defined in `settings.php`) at `LogLevel::INFO`, the old handler's level
  (BREAKING.md #7). "Calculated quote" now appears on stdout as
  `slim-app.INFO: Calculated quote {"total":26.97} []`.
- `calculateQuote` keeps its `try/catch/finally` (BREAKING.md #14). The catch
  sets `$quote = 0.0` and `finally` still does `return $quote;`.

## Traps
- `return` inside `finally` also swallows `TypeError`. A request without a
  JSON content type gives `getParsedBody() === null`, and
  `array_key_exists(..., null)` throws `TypeError`, which is not an
  `\Exception`. Upstream returns 200 `0` in that case only because of the
  `finally` return. Do not collapse the block into a plain catch.
- Nothing else needs `guzzlehttp/guzzle`. The app code doesn't use it, and
  Monolog lists it only under `require-dev`. Slim's `GuzzlePsr17Factory` is
  optional auto-detection: `slim/psr7` is installed and detected first.
  ReactPHP doesn't depend on it. Removing it also drops `guzzlehttp/psr7`,
  `guzzlehttp/promises`, `psr/http-client` and `symfony/deprecation-contracts`
  from `vendor/`.

## Dormant transitive OTel
- none. `vendor/composer/installed.json` has no `open-telemetry/*` package.
  The only remaining mention is a doc comment in Monolog's `FrankenPhpHandler`.
  The image has no `opentelemetry` or `protobuf` extension (`php -m`).

## Verify
- `docker build --load -t notel-test/quote -f src/quote/Dockerfile .`
- `docker run -e QUOTE_PORT=8090 -p 18090:8090 notel-test/quote`, then
  `curl -X POST localhost:18090/getquote -H 'Content-Type: application/json' -d '{"numberOfItems":3}'`
  returns `26.97`. `{}` and an empty body without a content type both
  return `0`.
- `check_residuals.py --paths src/quote`: the remaining hits are project-name
  branding in `README.md` (`opentelemetry-demo`) and the `composer.json`
  description. They need an allowlist entry.
