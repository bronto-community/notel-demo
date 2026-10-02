---
name: notel-verify
description: Verify that the notel-demo fork (the OpenTelemetry Demo with observability removed) builds, runs end to end in Docker, has no observability residue, and stays silent on the network (no telemetry connection attempts). Use after stripping services or syncing upstream, before tagging a notel release.
---

# Verify notel-demo

Run every step from the repo root. A failure in any step means the run is
not done. Report the failure; do not paper over it.

## 1. Static checks

1. Run `python3 notel/scripts/check_residuals.py`. It must exit with 0. Each
   allowlist entry in `notel/scripts/residuals-allowlist.txt` must have a
   reason. Review any new entry with the maintainer.
2. Run `docker compose -f compose.yaml -f compose.full.yaml -f compose.agent.yaml config -q`,
   and repeat with the other file combinations the Makefile uses.
3. Check the direct dependency manifests. No manifest under `src/` may
   declare an OTel, Prometheus, Traceloop or OpAMP dependency. The residual
   scan covers this, but read the manifests again for package names that
   don't contain "otel".

## 2. Build

`make build`, or `docker compose -f compose.yaml -f compose.full.yaml build`.
Add `-f compose.agent.yaml` when the agent services are in scope. Every image
must build.

## 3. Run with the silence check

```sh
docker compose -f compose.yaml -f compose.full.yaml -f notel/verify/compose.canary.yaml up -d
notel/verify/silence_check.sh start
```

Let the load generator run for at least 10 minutes. It starts by default and
covers browser traffic when `LOCUST_BROWSER_TRAFFIC_ENABLED=true`.

## 4. Functional smoke test

- `curl -fsS localhost:8080/` returns the storefront.
- `curl -fsS localhost:8080/api/products` returns JSON.
- Do one checkout through the UI or the API: add to cart, then check out.
  The order confirmation must render.
- `/feature` (flagd-ui) loads.
- No container is restarting: `docker compose ps` shows everything up and
  healthy.
- Locust stats at `localhost:8080/loadgen/` show traffic, with a failure rate
  in line with the flags (all flags are off by default).
- Logs: every service writes its usual stdout logs. Spot-check checkout,
  product-catalog, currency, shipping, recommendation, quote and
  load-generator. These are the ones where notel added stdout logging.
- Toggle one failure flag (e.g. `paymentFailure`) in `/feature` and confirm
  that the failure shows up in logs or the UI. Then switch it back off.
- Run the frontend Cypress tests: `make run-frontend-tests` (or the
  compose.tests.yaml equivalent).

## 5. Silence report

```sh
notel/verify/silence_check.sh report   # must print SILENT and exit 0
docker compose logs 2>&1 | grep -iE 'otlp|exporter|opentelemetry|4317|4318' # review every hit
notel/verify/silence_check.sh stop
```

Accepted exceptions are listed in `notel/verify/silence-allowlist.txt`
(currently only flagd → localhost:4318, BREAKING.md #23). The report prints
them, but they don't fail the check. Any other hit is a regression: dormant
library instrumentation became active, or a removal was missed. Investigate
and report it. Add an allowlist entry only with the maintainer's approval.

Positive control: after the first report, run the following and then run
`report` again:

```sh
docker exec load-generator python -c "import socket
for h in ('otel-collector', 'localhost'):
    try: socket.create_connection((h, 4318), 2).close()
    except OSError: pass"
```

The second report must show a hit from `notel-canary` and from the
`load-generator` sidecar, and it must exit 1. If either hit is missing, the
check itself is broken. The frontend image is distroless (it has no shell),
so use load-generator. `report` exits with 3 ("NOT VERIFIED") if no
sidecars or canary are running. Never treat that as silent.

## 6. Image scan (dormant transitive check)

For each built image, list the files and packages that match `opentelemetry`.
Compare them with the "Known dormant cases" in `notel/DECISIONS.md`. A new
case is not a failure, but it must be reported to the maintainer and added to
DECISIONS.md and BREAKING.md once approved.

## 7. Tear down

`docker compose -f compose.yaml -f compose.full.yaml -f notel/verify/compose.canary.yaml down -v`

## 8. Kubernetes

Run this after the compose teardown (step 7). The stack and the cluster
don't fit in memory together. It needs kind, kubectl and Helm 4. The images from step 2 must
be present locally with the tag `latest`.

1. `docker run --rm -v "$PWD":/w -w /w python:3.13-alpine sh -c 'pip install -q pyyaml && python3 notel/scripts/gen_helm_values.py --check'`
   must exit with 0. If it doesn't, the values are stale. Regenerate them
   and review the diff.
2. `notel/k8s/check_render.sh` must print CLEAN and exit with 0.
3. Run the cluster:

   ```sh
   notel/k8s/kind_verify.sh up        # every pod must become Ready
   notel/k8s/kind_verify.sh capture
   notel/k8s/kind_verify.sh smoke     # /, /api/products, /feature/, /loadgen/ return 200
   ```

   Let the load generator run for at least 5 minutes. Then run
   `notel/k8s/kind_verify.sh smoke` again, and check that Locust shows
   requests and few failures.
4. `notel/k8s/kind_verify.sh report` must print SILENT and exit with 0.
   As with compose, only flagd → localhost:4318 is allowlisted.
5. Positive control: run `notel/k8s/kind_verify.sh control`, then
   `report` again. The report must show a canary hit and a load-generator
   hit, and exit with 1.
6. `notel/k8s/kind_verify.sh down`.

`kind_verify.sh up` refuses to start while any notel compose container is
running (anything on the `opentelemetry-demo` network), because the cluster needs that
memory. Stop the stack first. Don't work around the check. The full chart
runs, including the agent, MCP server and chatbot. The kind node is capped
at 4 GB (`NODE_MEMORY`). flagd runs with a 150Mi limit (`FLAGD_MEMORY`),
because with the chart's 75Mi it thrashed on page cache and stalled the
whole demo. This is under investigation. If pods are OOM-killed or stay
pending, report it. tcpdump attaches only after the pods are Ready, so
startup is not captured. This is the same gap as in the compose run.

## Output

Write a short verification summary to `notel/verify/LAST_RUN.md`. Include:

- The upstream sha.
- The pass or fail result of each step.
- The silence report, for compose and for Kubernetes.
- Any new dormant cases.
- The open issues.
