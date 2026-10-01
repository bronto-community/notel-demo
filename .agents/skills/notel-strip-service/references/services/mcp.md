# mcp (Python, FastMCP)

## Observability removed
- `run.py`: `Traceloop.init` (and its `OTEL_SERVICE_NAME` read),
  `HTTPXClientInstrumentor().instrument()`, their imports, and the now unused
  `import os`.
- `requirements.in`: `traceloop-sdk`, all `opentelemetry-*` packages, and
  `langchain` (not imported by the MCP server or `src/shared/tools.py`; it was
  only there for `opentelemetry-instrumentation-langchain`; maintainer
  decision). This also drops langchain-core, langgraph*, langsmith and their
  dependencies from the lockfile.
- `README.md`: the Observability overview bullet and section, the
  Traceloop/httpx startup sentence, the `OTEL_*` config rows, the
  `OTEL_EXPORTER_OTLP_ENDPOINT` line in the local run example, and the
  "Traceloop init" file-layout note.

## Behavior-preserving replacements
- none needed. `logging.basicConfig(level=logging.INFO)` was already there.

## Traps
- If upstream adds a real `langchain` import to the MCP server, put the
  dependency back.

## Dormant transitive OTel
- `fastmcp` -> `fastmcp-slim` -> `opentelemetry-api` (API only, no SDK, so
  no-op). Known case in DECISIONS.md.

## Verify
- Lockfile, from the repo root (header paths are repo-relative) with
  `python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d`,
  `pip==25.2 pip-tools==7.5.2`, same flags as the header.
- `docker build --load -t notel-mcp:test -f src/mcp/Dockerfile .`
- `docker run --rm --entrypoint pip notel-mcp:test list | grep -Ei 'opentelemetry|traceloop|prometheus'`
  prints only `opentelemetry-api`.
- `docker run --rm notel-mcp:test` reaches `Uvicorn running on http://0.0.0.0:8011`.
