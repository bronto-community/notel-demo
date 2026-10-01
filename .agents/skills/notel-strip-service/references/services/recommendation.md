# recommendation (Python)

## Observability removed
- `recommendation_server.py`:
  - All `opentelemetry.*` imports, the `TracingHook` import and
    `api.add_hooks([TracingHook()])`.
  - The tracer and meter setup, `init_metrics` and the
    `demo.recommendation.requests` counter `.add()` call.
  - `LoggerProvider`, `OTLPLogExporter`, `BatchLogRecordProcessor`,
    `LoggingHandler` and the `logger.addHandler(handler)` call.
  - `trace.get_current_span()` and every `span.set_attribute` call
    (`demo.product.*`, `demo.feature_flag.recommendation_cache`,
    `demo.recommendation.cache_hit`).
  - The `start_as_current_span("get_product_list")` wrapper. The body is
    unwrapped and dedented.
  - `must_map_env('OTEL_SERVICE_NAME')` (`service_name` was only used for the
    tracer and meter).
- `metrics.py` (counter definition) and `logger.py` (dead JSON logger that
  injected trace and span IDs): deleted.
- `Dockerfile`: `opentelemetry-bootstrap -a install`, the
  `opentelemetry-instrument` ENTRYPOINT wrapper, and the COPY of `logger.py`
  and `metrics.py`.
- `requirements.in`: `opentelemetry-distro`,
  `opentelemetry-exporter-otlp-proto-grpc`, `openfeature-hooks-opentelemetry`,
  `psutil` (its only purpose was to make `opentelemetry-bootstrap` install the
  system-metrics instrumentation, per its inline comment) and
  `python-json-logger` (only imported by the deleted `logger.py`).

## Behavior-preserving replacements
- `logging.basicConfig(level=logging.INFO)` at the start of `__main__`, so the
  `main` logger reaches stdout (BREAKING.md #5). Output format is the stdlib
  default, e.g. `INFO:main:Recommendation service started, listening on port 9001`.
- The service no longer needs `OTEL_SERVICE_NAME` to start (BREAKING.md #8).

## Traps
- `logger` and `product_catalog_stub` are module globals created in
  `__main__`. Keep `logger = logging.getLogger('main')` there.
- `python-dotenv` is in `requirements.in` but not imported. It is not
  observability, so it is kept.
- pip-tools >= 7.5 writes `--no-index` into the lockfile header when called
  with `--no-emit-index-url`. The header was restored to the original
  command, since the written one would not resolve if re-run.

## Dormant transitive OTel
- none

## Verify
- Lockfile, from the repo root (header paths are repo-relative):
  `docker run --rm -v "$PWD":/repo -w /repo python:3.14.7-alpine3.24@sha256:c6ead215bfd31f1e433d968853b7a769989117115b728874824e6c0a27cb96fc sh -c 'pip install -q pip==25.2 pip-tools==7.5.2 && pip-compile --allow-unsafe --generate-hashes --no-emit-index-url --strip-extras --output-file=src/recommendation/requirements.txt src/recommendation/requirements.in'`
  (keeps the existing pins; only removals expected).
- `docker build --load -t notel-recommendation:test -f src/recommendation/Dockerfile .`
- `docker run --rm --entrypoint /venv/bin/pip notel-recommendation:test list | grep -Ei 'opentelemetry|traceloop|prometheus'` prints nothing.
- `docker run --rm -e PRODUCT_CATALOG_ADDR=localhost:1 -e RECOMMENDATION_PORT=9001 notel-recommendation:test`
  logs `INFO:main:Recommendation service started, listening on port 9001`
  with no `OTEL_*` set.
