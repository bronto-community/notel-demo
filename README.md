# notel-demo

![notel-demo logo](notel/assets/notel-demo-logo.png)

**The [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo),
with all of the OpenTelemetry taken out.**

notel-demo is the same microservice shop as the OpenTelemetry Demo, the
Astronomy Shop: the same services, languages, feature flags and load
generator. Every piece of observability has been removed. There are no SDKs,
no agents, no exporters, no instrumentation libraries, no collector and no
backends. It is a realistic, polyglot application that starts out completely
uninstrumented.

> [!NOTE]
> **This project is built with AI.** The scripts, skills and docs in this
> repository were written with an AI coding agent. Observability is
> stripped from the upstream code by AI coding agents following the skills
> in [.agents/skills/](.agents/skills/). A deterministic script handles the
> mechanical infrastructure edits. Every result is checked by an automated
> verification run, and each AI-generated commit has an `Assisted-by:`
> trailer. Review the diff against upstream before relying on it.

This project builds on top of the OpenTelemetry Demo. It is not a fork that
evolves on its own: it is regenerated from upstream from time to time, so it
stays as close to the original as possible. The upstream README is kept as
[README.original.md](README.original.md).

## Why

- **Compare uninstrumented and instrumented.** Run notel-demo and the
  upstream demo side by side, or run notel-demo before and after you
  instrument it, and see what instrumentation adds in signals, overhead and
  complexity.
- **Try instrumentation approaches from zero.** Use it as a clean starting
  point for:
  - zero-code and agent-based approaches: the OpenTelemetry Operator,
    injectors, language agents and eBPF-based instrumentation;
  - vendor agents;
  - AI- or skill-driven instrumentation, where a coding agent adds the
    instrumentation for you.

  The upstream demo combines zero-code instrumentation (the Java agent,
  .NET auto-instrumentation, `opentelemetry-instrument`, the Node.js
  auto-instrumentations) with manual spans, attributes and metrics. You can
  compare what your approach produces with what upstream produces.
- **Measure.** Get a baseline for resource usage, latency and startup time
  without any telemetry pipeline in the way.

## What is removed and what is kept

Removed:

- OpenTelemetry API and SDK calls, exporters and instrumentation libraries in
  every service.
- The Java agent, .NET auto-instrumentation, Node `--require` hooks, the
  Python `opentelemetry-instrument` wrapper, the PHP extension and the C++ SDK
  build.
- Prometheus clients and endpoints, Traceloop/OpenLLMetry, and OpAMP clients.
- The OpenTelemetry Collector, Jaeger, Prometheus, Grafana, OpenSearch, the
  OpAMP server, profiling, the telemetry schema and docs, and the telemetry
  tests.
- Tracing in Envoy and nginx, the OTLP endpoint on the frontend proxy, and
  trace context in Kafka headers and SQL comments.

Kept:

- All services and their behavior, including the failure-scenario feature
  flags, the load generator and the AI agent and chatbot.
- Plain stdout logging. Where logs used to reach stdout only through
  OpenTelemetry, they now use the language's standard logger.

Some third-party libraries still ship the OpenTelemetry API internally. One
example is the flagd OpenFeature providers; another is Next.js. Without an
SDK they do nothing, and once you add one they produce spans. These cases
are listed as "dormant library instrumentation" in
[notel/BREAKING.md](notel/BREAKING.md), so that their spans are not mistaken
for demo code when you compare results. flagd itself is a known exception:
it tries to reach `localhost:4318` even when nothing is configured.

## Quick start

You need Docker with Compose. The full stack peaks at about 2 GB of memory.

```sh
make build           # build all images locally
make start           # full demo
make start-agentic   # full demo plus the AI agent, MCP server and chatbot
make stop
```

Then open:

- the storefront at <http://localhost:8080/>;
- the load generator at <http://localhost:8080/loadgen/>;
- the feature flags at <http://localhost:8080/feature/>;
- the chatbot at <http://localhost:8080/chatbot/> (with `start-agentic`).

If port 8080 is taken, export `ENVOY_PORT` with another port first.

## How it works

Each notel release is the upstream demo at a specific commit, followed by a
small, readable stack of commits:

1. `notel: tooling`, with the scripts, skills and decision log.
2. `notel: delete observability components`.
3. `notel: strip infra`, the output of a deterministic script.
4. `notel(<service>): strip observability`, one commit per service.
5. `notel: verification record`.

Releases are tagged `notel/<upstream-sha>`. To see exactly what notel changed
in a release, run `git diff <upstream-sha> notel/<upstream-sha>`.

notel does not merge upstream changes. On every sync it rebuilds from a fresh
upstream commit:

- [notel/scripts/strip_infra.py](notel/scripts/strip_infra.py) handles the
  mechanical parts deterministically: compose files, env, Makefile, proxies,
  CI and docs. It fails loudly when upstream drifts.
- Service code is stripped by coding agents that follow the skills in
  [.agents/skills/](.agents/skills/). They use the
  [Agent Skills](https://agentskills.io) format, so any compatible agent can
  run them:
  - `notel-sync` regenerates the whole project.
  - `notel-strip-service` strips one service.
  - `notel-verify` checks the result.
- `notel-verify` builds and runs the full stack under load. It checks that
  the shop still works, scans for leftover instrumentation, and runs a
  silence check: a canary plus packet capture inside every container, which
  confirms that nothing tries to send telemetry.
- [notel/DECISIONS.md](notel/DECISIONS.md) records every decision about what
  to remove, keep or replace.
- [notel/BREAKING.md](notel/BREAKING.md) lists every place where removing
  observability changed behavior, and how notel handles it.

## Contributing

Contributions to the demo itself go to the
[OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo).
That covers new features, bug fixes, new services and documentation. They
reach notel-demo with the next sync.

This repository only accepts contributions that help strip OpenTelemetry
from the demo, for example:

- a removal that was missed, or leftover instrumentation;
- improvements to the strip scripts, skills or verification;
- fixes for behavior that breaks when observability is removed.

Some of those couplings are better fixed upstream. BREAKING.md marks them as
upstream candidates.

## License

[Apache License 2.0](LICENSE), the same as the OpenTelemetry Demo. The demo
is copyright The OpenTelemetry Authors.
