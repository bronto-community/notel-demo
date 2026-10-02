#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Render the pinned upstream opentelemetry-demo chart with notel's values and
# post-renderer, and fail if anything observability-related is left.
# Runs helm in Docker. Usage, from anywhere:
#   notel/k8s/check_render.sh [output.yaml]
# The rendered manifests are written to the given file (default: a temp file).
set -euo pipefail

HELM_IMAGE="${HELM_IMAGE:-alpine/helm:4.3.0}"
CHART_REPO="https://open-telemetry.github.io/opentelemetry-helm-charts"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${HERE}/chart-version")"
OUT="${1:-$(mktemp)}"
PATTERN='OTEL_|otel-collector|jaeger|prometheus|grafana|opensearch|opamp|traceloop'

docker run --rm -v "${ROOT}:/w:ro" -w /w --entrypoint sh "${HELM_IMAGE}" -c "
  set -e
  export HELM_CONFIG_HOME=/tmp/helm HELM_CACHE_HOME=/tmp/helm/cache HELM_DATA_HOME=/tmp/helm/data
  helm plugin install notel/k8s/post-render >/dev/null
  helm template notel opentelemetry-demo --repo '${CHART_REPO}' --version '${VERSION}' \
    -f notel/k8s/values.yaml --post-renderer notel-strip
" > "${OUT}"

fail=0
deployments="$(grep -c '^kind: Deployment$' "${OUT}" || true)"
echo "rendered chart ${VERSION}: $(wc -l < "${OUT}" | tr -d ' ') lines, ${deployments} Deployments -> ${OUT}"
if [ "${deployments}" -eq 0 ]; then
  echo "FAIL: no Deployments rendered" >&2
  fail=1
fi
if grep -inE "${PATTERN}" "${OUT}"; then
  echo "FAIL: observability references left in the rendered manifests (above)" >&2
  fail=1
fi
for cm in flagd-config postgresql-init agent-fixtures; do
  if grep -qx "  name: ${cm}" "${OUT}"; then
    echo "FAIL: ConfigMap ${cm} was not removed by the post-renderer" >&2
    fail=1
  fi
done
if [ "${fail}" -eq 0 ]; then echo "CLEAN: no matches for ${PATTERN}"; fi
exit "${fail}"
