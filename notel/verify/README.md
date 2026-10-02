# notel verification tooling

Used only by the `notel-verify` skill. It is never part of the shipped demo.

- `compose.canary.yaml` and `canary.py`: a listener that takes over every
  hostname an exporter could target (`otel-collector`, `jaeger`,
  `prometheus`, ...). It logs `CANARY_HIT` for every TCP connection or UDP
  datagram it receives on telemetry ports.
- `silence_check.sh start|report|stop`: attaches a `tcpdump` sidecar to the
  network namespace of every running demo container. This catches
  connection attempts to telemetry ports even when they target `localhost`,
  which is the SDK default when no endpoint is configured and which the
  canary alone cannot see.
- `LAST_RUN.md`: the result of the latest verification run.

Positive control: see the notel-verify skill. A connection from
load-generator to `otel-collector:4318` and to `localhost:4318` must be
recorded by both the canary and the load-generator sidecar. `report` exits
with 3 when nothing is attached, so an empty setup can never pass as
silent.

Known gaps:

- Sidecars attach after `up -d`, so roughly the first minute of startup is
  not captured. One-off containers such as `frontend-tests` are not covered.
- The sidecar filter covers outbound OTLP, Zipkin and Jaeger ports. Ports
  9464 and 8889 are Prometheus exporter *listening* ports. The canary covers
  them for scrape-style targets.
- If host port 8080 is taken, export `ENVOY_PORT=<free port>` before `up`.
