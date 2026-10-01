# flagd-ui (Elixir, Phoenix)

## Observability removed

- mix.exs: `opentelemetry`, `opentelemetry_api`, `opentelemetry_exporter`,
  `opentelemetry_phoenix`, `opentelemetry_bandit`, `telemetry_poller`,
  `telemetry_metrics` deps and the release `applications:` block (it only
  listed the OTel apps).
- lib/flagd_ui/application.ex: `OpentelemetryBandit.setup/0`,
  `OpentelemetryPhoenix.setup/1`, the `FlagdUiWeb.Telemetry` child, and
  `Application.ensure_started(:inets)` (its comment and only purpose was the
  exporter's httpc; nothing else in lib/config uses `:httpc`).
- lib/flagd_ui_web/telemetry.ex: deleted (Telemetry.Metrics definitions and
  the telemetry_poller VM measurements).
- lib/flagd_ui_web/router.ex: `metrics: FlagdUiWeb.Telemetry` on the dev-only
  `live_dashboard` route. LiveDashboard stays; its other pages do not need
  metrics and the Metrics tab shows its "not configured" hint.
- config/runtime.exs: the required `OTEL_EXPORTER_OTLP_ENDPOINT` read and the
  `:opentelemetry, :processors` exporter config.
- config/dev.exs: `otel_exporter_stdout` traces exporter.
- mix.lock: `mix deps.get` then `mix deps.unlock --unused` (deletions only).
- test/flagd_ui/scheduler_test.exs: the `emitRawPii` exclusion test is now an
  inline-config test of `metadata.schedulable: false`, since no shipped flag
  uses that metadata any more.

## Behavior-preserving replacements

- Prod startup no longer needs `OTEL_EXPORTER_OTLP_ENDPOINT` (BREAKING.md #9).
- `:telemetry` and `Plug.Telemetry` in endpoint.ex stay: Phoenix request logs
  (`GET /...`, `Sent 200 in ...`) depend on them (DECISIONS, framework
  telemetry).

## Traps

- `mix deps.unlock --unused` without fetched deps unlocks every transitive
  dep (it removed plug, mime, telemetry, ...). Run `mix deps.get` first, in a
  scratch copy so `deps/` does not land in the repo.
  The scratch copy needs only `mix.exs`, `mix.lock` and `config/`. The slim
  Elixir image has no `git`, which `mix deps.get` needs for `heroicons`;
  `apt-get install git` first. On a sync, take upstream's `mix.lock` when
  the cherry-pick conflicts and rerun both steps.
- `phoenix_live_dashboard` depends on `telemetry_metrics` (non-optional), so
  `telemetry_metrics` stays in mix.lock as a transitive dep after the direct
  dep is removed. It is a BEAM `:telemetry` helper, not OTel.
- The Dockerfile test stage copies `src/flagd/demo.flagd.json`; tests read the
  shipped flags.
- A bare container returns 500 until `/app/data/demo.flagd.json` exists
  (compose mounts it). Unrelated to the strip.
- Residual scanner hits: `Plug.Telemetry` (kept per DECISIONS) and the
  opentelemetry.io docs link in README.md.

## Dormant transitive OTel

- none.

## Verify

- `docker build -f src/flagd-ui/Dockerfile .` (repo root context; the test
  stage runs `mix test`: 47 passed). Compile warnings are in deps only.
- `docker run -v <dir with demo.flagd.json>:/app/data -e SECRET_KEY_BASE=... -e PHX_SERVER=true -p 14000:4000 <image>`
  with no OTEL env: `/`, `/scheduler`, `/advanced`, `/api/read` return 200 and
  request logs print to stdout.
