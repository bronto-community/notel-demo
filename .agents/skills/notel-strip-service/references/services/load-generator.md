# load-generator (Python, Locust)

## Observability removed

- `locustfile.py`:
  - The `grpc.experimental.gevent` workaround. Its comment ties it to the
    gRPC exporter imports, and nothing else imports grpc (grpcio is gone from
    the lockfile).
  - All `opentelemetry.*` imports, the `MeterProvider`, `TracerProvider`,
    `LoggerProvider`, the OTLP gRPC metric/span/log exporters, the root
    `LoggingHandler`, and the `LoggingInstrumentor`, `Jinja2Instrumentor`,
    `RequestsInstrumentor`, `SystemMetricsInstrumentor` and
    `URLLib3Instrumentor` calls, plus the "Instrumentation complete" log.
  - `TracingHook` and `api.add_hooks`.
  - `WebsiteUser.__init__` (only set `self.tracer`) and every
    `start_as_current_span` (unwrapped and dedented), including the span
    attributes and the `gen_ai.input.messages` JSON (`input_messages` was
    only built for that attribute).
  - `on_start`: the `session.id` and `synthetic_request` baggage and the
    `context.attach`. `session_id` is not sent in any request; it is kept only
    for the existing "Starting user session" log line.
  - Browser users: the `context=Context()` spans, `add_baggage_header` and its
    `page.route('**/*', ...)` calls and the `playwright.async_api` import.
- `requirements.in`: `openfeature-hooks-opentelemetry` and all
  `opentelemetry-*` packages. `openfeature-provider-ofrep` is kept.

## Behavior-preserving replacements

- `logging.basicConfig(level=logging.INFO)` at module import. The image runs
  `locust --skip-log-setup`, so this is the only root handler (BREAKING.md
  #6). Format changes from the LoggingInstrumentor format (timestamp, trace
  and span IDs) to the stdlib default `INFO:root:<message>`.

## Traps

- KEEP both browser `wait_for_timeout(2000)` calls (maintainer decision,
  overrides the "browser export sleeps" wording in DECISIONS.md). Upstream
  commented them as "time to export the traces", but they also keep the page
  alive: `locust_plugins`' `@pw` closes the previous browser context at the
  start of the next task and `PlaywrightUser.wait_time` is 0, so without the
  wait the page is torn down right after `select_option`/`click` and the
  currency re-fetch and add-to-cart requests can be cut off. Keeping them
  keeps the traffic shape identical to upstream. Only the comment was
  changed, to "keep the page open so the requests triggered above complete".
- `python-json-logger` is in `requirements.in` but not imported anywhere. Not
  observability, kept.
- Locust exits 1 when requests fail; that is expected in a smoke run without
  a frontend.

## Dormant transitive OTel

- none

## Verify

- Lockfile, from the repo root with
  `python:3.14.7-slim-bookworm@sha256:82bc3c539b8813ada9d68c63b40158fa002f7f33de9bf3312a3dfdc0620dff56`,
  `pip==25.2 pip-tools==7.5.2`, same flags as the header. Restore the header
  if pip-tools adds `--no-index`.
- `docker build --load -t notel-load-generator:test -f src/load-generator/Dockerfile .`
- `docker run --rm --entrypoint pip notel-load-generator:test list | grep -Ei 'opentelemetry|traceloop|prometheus'` prints nothing.
- `docker run --rm -e LOCUST_BROWSER_TRAFFIC_ENABLED=true -e LOCUST_BROWSER_USER_WEIGHT=0 notel-load-generator:test --headless -u 1 -r 1 -t 5s -H http://127.0.0.1:1`
  prints `INFO:root:User ...` lines and shuts down without a traceback.
