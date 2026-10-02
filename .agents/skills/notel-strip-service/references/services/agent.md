# agent (Python, FastAPI + LangChain)

## Observability removed

- `run.py`: `Traceloop.init` (and its `OTEL_SERVICE_NAME` read), the
  `HTTPXClientInstrumentor`, `OpenAIInstrumentor` and
  `FastAPIInstrumentor.instrument_app` calls with their imports, and the now
  unused `import os`.
- `src/agents/agents.py`: `@workflow(name="astronomy_shop_agent_workflow")`
  and the `traceloop.sdk.decorators` import.
- `src/agents/feature_flags.py`: `TracingHook` and `api.add_hooks`.
- `requirements.in`: `traceloop-sdk`, all `opentelemetry-*` packages,
  `openfeature-hooks-opentelemetry`, and `aiohttp` and `greenlet` (not
  imported by the service; maintainer decision). `langchain` is kept, the
  agent imports it.
- `fixtures/vcr_cassettes/*.yaml`: the recorded
  `POST http://otel-collector:4318/v1/traces` interaction (one per cassette,
  captured while recording with Traceloop on). Every remaining interaction has
  `uri: https://vcr.local/`. **Redo on every sync**: upstream re-records the
  cassettes with telemetry on, so drop every interaction whose `uri` is not
  `https://vcr.local/` (collector, `/v1/traces|metrics|logs`), editing the
  YAML textually so the other entries stay byte-identical, then check it
  loads with `yaml.safe_load`.
- `README.md`: the Observability overview bullet and section, the `OTEL_*`
  config rows, the "No telemetry appears" troubleshooting entry. The
  compose "Depends on" list now matches `compose.agent.yaml`
  (`product-catalog`, `mcp`, `flagd`).

## Behavior-preserving replacements

- none needed. `logging.basicConfig(level=logging.INFO)` was already there.

## Traps

- Keep `mcp<2` (currently `mcp==1.30.0`).
- VCR is used at runtime: `.env` sets `USE_VCR=True` and
  `LLM_MODEL=azure/gpt-5.5`, and compose mounts `./src/agent/fixtures` into
  `/app/fixtures`. `record_mode="new_episodes"` writes to that mount, so test
  replay against a copy of the fixtures.

## Dormant transitive OTel

- `fastmcp` -> `fastmcp-slim` -> `opentelemetry-api` (API only, no SDK, so
  no-op). Known case in DECISIONS.md.

## Verify

- Lockfile, run from `src/agent` (header paths are relative) with
  `python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d`,
  `pip==25.2 pip-tools==7.5.2`, same flags as the header.
- `docker build --load -t notel-agent:test -f src/agent/Dockerfile .`
- `docker run --rm --entrypoint pip notel-agent:test list | grep -Ei 'opentelemetry|traceloop|prometheus'`
  prints only `opentelemetry-api`.
- `docker run --rm notel-agent:test` reaches `Uvicorn running on http://0.0.0.0:8010`.
- Replay: copy `fixtures/` to a temp dir, run the image with it mounted at
  `/app/fixtures`, `USE_VCR=True LLM_MODEL=azure/gpt-5.5
  LLM_BASE_URL=http://127.0.0.1:1/v1 API_KEY=x MCP_ENABLED=False`, and POST
  the canned prompts to `/prompt`. Expect HTTP 200 and
  `VCR best-match playback ... score=1.0000` logs, with the copy unchanged.
