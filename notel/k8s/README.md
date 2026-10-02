# notel on Kubernetes

notel runs on Kubernetes with the upstream
[opentelemetry-demo Helm chart](https://github.com/open-telemetry/opentelemetry-helm-charts/tree/main/charts/opentelemetry-demo).
It needs two things on top of the chart: a values file and a small
post-renderer.

- `chart-version` pins the chart version. Its `appVersion` must match
  `IMAGE_VERSION` in `.env`.
- `values.yaml` is generated. Don't edit it by hand. It turns off the
  collector, Jaeger, Prometheus, Grafana, OpenSearch, the OpAMP server,
  telemetry docs and profiling. It removes every OTel env var, pod
  annotation and metrics port, and points the images at `IMAGE_NAME`. It
  also mounts notel's flagd flags, PostgreSQL init script and agent
  cassettes in place of the chart's copies.
- `post-render/` deletes the chart's own copies of those three ConfigMaps
  (`flagd-config`, `postgresql-init`, `agent-fixtures`). Nothing references
  them once the values are applied.

## Install

With Helm 4:

```sh
helm plugin install notel/k8s/post-render
helm install notel opentelemetry-demo \
  --repo https://open-telemetry.github.io/opentelemetry-helm-charts \
  --version "$(cat notel/k8s/chart-version)" \
  -f notel/k8s/values.yaml --post-renderer notel-strip
kubectl port-forward svc/frontend-proxy 8080:8080
```

Helm 3 runs the script directly:
`--post-renderer notel/k8s/post-render/post-render.sh`.

The images are `<IMAGE_NAME>:<tag>-<service>`. The values default to tag
`latest`, the same tag that `make build` produces. To use a release, pass
`--set default.image.tag=notel-<upstream-short-sha>`.

Without the post-renderer, the release still works and sends no telemetry.
The three ConfigMaps stay behind, unused, with the upstream flags (including
`emitRawPii`) and the upstream PostgreSQL init script, which creates a
monitoring user.

## Regenerate the values

```sh
docker run --rm -v "$PWD":/w -w /w python:3.13-alpine \
  sh -c 'pip install -q pyyaml && python3 notel/scripts/gen_helm_values.py'
```

The script needs PyYAML, so it runs in Docker. Use `--check` to only
compare, `--tag` to change the default image tag, and `--chart` to use a
local chart. The output is deterministic. The script fails when the chart
has something it doesn't know: a new component, dependency, template or
top-level key, a chart shape it edits that has changed, or anything that
still looks like observability after stripping.

## Checks

- `notel/k8s/check_render.sh [out.yaml]` renders the pinned chart in
  Docker, with the values and the post-renderer. It exits 1 if the output
  matches `OTEL_|otel-collector|jaeger|prometheus|grafana|opensearch|opamp|traceloop`,
  or if one of the three ConfigMaps is still there.
- `notel/k8s/kind_verify.sh` is the cluster run used by the `notel-verify`
  skill. It needs kind, kubectl and Helm 4. It creates a kind cluster and
  loads the local images. It deploys the canary from `notel/verify/` behind
  Services named like the backends, installs the chart, and attaches a
  tcpdump ephemeral container to every pod.
  It refuses to start while any container on the compose network
  `opentelemetry-demo` is running, since both don't fit in memory
  together. Stop compose first.
