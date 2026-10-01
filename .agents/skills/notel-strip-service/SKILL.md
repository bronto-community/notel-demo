---
name: notel-strip-service
description: Remove all observability (OpenTelemetry, Prometheus, Traceloop, OpAMP, agents, exporters, instrumentation) from one service of the notel-demo fork of the OpenTelemetry Demo, keeping behavior intact. Use when stripping or re-stripping a service under src/ after an upstream sync.
---

# Strip observability from one service

You are working on one service directory under `src/<service>` in the
notel-demo fork.

Before you start, read these files. They are binding.

- `notel/DECISIONS.md`: what to keep, what to remove, and the transitive rule.
- `notel/BREAKING.md`: the known couplings and how notel fixes them.
- `.agents/skills/notel-strip-service/references/services/<service>.md`, if it
  exists. It records what was done on earlier syncs and the service-specific
  traps.
- The previous strip diff for the service, if one exists. Compare the last
  notel tag against its upstream base:
  `git diff <prev-upstream-sha> <prev-notel-tag> -- src/<service>`.

If a situation is not covered by DECISIONS.md, stop and report the question.
Do not decide on your own.

## Scope

- Edit only `src/<service>/**`, plus any files explicitly assigned to you.
- `compose*.yaml`, `.env`, the Makefile, `.github`, and infra under
  `src/frontend-proxy`, `src/image-provider`, `src/kafka` and `src/postgresql`
  are handled by `notel/scripts/strip_infra.py`. Do not touch them.
- Never commit or push. The orchestrator commits.

## Procedure

1. **Inventory.** Search the service for:
   `opentelemetry|otel|OTEL_|tracer|meter|span|baggage|propagat|prometheus|metrics|traceloop|opamp|instrument|ActivitySource|Activity\.|System\.Diagnostics\.Metrics`
   (case-insensitive). Also check the manifests and lockfiles, the Dockerfile,
   and the entrypoint and start scripts.
2. **Remove code.** Delete SDK init, providers, exporters, resource
   detectors, tracers, meters, spans, span attributes and events,
   `recordException`/`setStatus`, baggage reads and writes, propagators,
   instrumentation wrappers (interceptors, middleware, handlers, transports),
   OpenFeature OTel hooks, OpAMP clients, and metric instruments with their
   recording code.
   - Keep the business logic that was wrapped. Unwrap `with span:` and
     `in_span do` blocks, and dedent them.
   - Keep `try/catch` blocks whose return values or rethrow behavior matter.
     A catch that only recorded on the span and then rethrew can go.
   - Do not leave no-op calls, shims or stubs.
3. **Keep logging working.** If logs reached stdout only through OTel, add the
   language-standard stdout logger listed in DECISIONS.md. Keep the messages
   and levels. Remove trace_id and span_id fields from log patterns.
4. **Remove dependencies.** Remove the direct OTel, Prometheus and
   instrumentation dependencies, then regenerate the lockfiles with the
   service's own toolchain inside Docker. Do not bump unrelated packages:
   - Go: `go mod tidy`.
   - Python: `pip-compile` with the existing hashes mode.
   - npm: `npm uninstall`.
   - Ruby: `bundle lock`.
   - Rust: `cargo update -p` only where needed.
   - Elixir: `mix deps.unlock --unused`.
   - .NET: Central Package Management (`Directory.Packages.props`).
5. **Dockerfile and startup.** Remove agent downloads, `-javaagent`,
   `--require` hooks, `opentelemetry-instrument`, `opentelemetry-bootstrap`,
   `instrument.sh`, PHP extensions, and OTel C++ builds. Preserve unrelated
   flags such as `-Xmx`.
6. **Env reads.** Remove reads of `OTEL_*` and similar env vars. A read that
   is required at startup must not crash the service once the variable is
   gone.
7. **Flags.** Per DECISIONS.md, remove `emitRawPii` and the
   `synthetic_request` handling. Keep the failure-scenario flags.
8. **Transitive check.** Resolve the dependency graph and list any OTel that
   is still pulled in. If it is a known dormant case in DECISIONS.md, that's
   fine. A new case must be reported, not removed.
9. **Build.** Build the image directly:
   `docker build -f src/<service>/Dockerfile .`, using the Dockerfile's
   context as compose defines it. Run the service's unit tests if they exist.
10. **Residual scan.** Run
    `python3 notel/scripts/check_residuals.py --paths src/<service>` if it exists;
    otherwise grep. Every remaining hit must be allowlisted with a reason.
11. **Record.** Write or update
    `.agents/skills/notel-strip-service/references/services/<service>.md`
    using the template below. If you hit a breaking or behavior change that
    is not yet in BREAKING.md, report it to the orchestrator.

## references/services/<service>.md template

```markdown
# <service> (<language>)

## Observability removed
- <file>: <what>

## Behavior-preserving replacements
- <what was added and why (link BREAKING.md item)>

## Traps
- <non-obvious things that broke or nearly broke>

## Dormant transitive OTel
- <dependency chain>, or "none"

## Verify
- <build or test commands that prove it works>
```
