# chatbot (Python, Gradio)

## Observability removed

- `run.py`: `_configure_telemetry()` (MeterProvider, TracerProvider, OTLP HTTP
  metric and span exporters, Requests and HTTPX instrumentors) and its call,
  all `opentelemetry.*` imports, and the OpAMP `start_opamp_agent()` /
  `stop_opamp_agent()` calls. The `try/finally` existed only for the OpAMP
  stop, so `await asyncio.gather(*tasks)` is called directly.
- `src/opamp.py`: deleted (OpAMP client).
- `requirements.in`: all `opentelemetry-*` packages (including
  `opentelemetry-opamp-client`) and `websocket-client` (only imported by
  `opamp.py`; no other package depends on it).
- `README.md`: the Observability overview bullet and section, the `OTEL_*`
  config rows, the "configures OpenTelemetry tracing" startup sentence and the
  "No telemetry appears" troubleshooting entry.

## Behavior-preserving replacements

- none needed. `logging.basicConfig(level=logging.INFO)` was already there.

## Traps

- none

## Dormant transitive OTel

- none

## Verify

- Lockfile, run from `src/chatbot` (header paths are relative) with
  `python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d`,
  `pip==25.2 pip-tools==7.5.2`, same flags as the header.
- `docker build --load -t notel-chatbot:test -f src/chatbot/Dockerfile .`
- `docker run --rm --entrypoint pip notel-chatbot:test list | grep -Ei 'opentelemetry|traceloop|prometheus'` prints nothing.
- `docker run --rm notel-chatbot:test` reaches `Running on local URL:  http://0.0.0.0:7860`.
