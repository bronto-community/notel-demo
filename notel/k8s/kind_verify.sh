#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Verification-only: run notel on a local kind cluster with a canary that
# stands in for every observability backend, plus a tcpdump ephemeral
# container in every pod. Never part of the shipped demo. Needs docker, kind,
# kubectl and helm (4.x) on PATH. Usage:
#   kind_verify.sh up        # cluster, images, canary, chart; waits for Ready
#   kind_verify.sh smoke     # port-forward frontend-proxy and curl the routes
#   kind_verify.sh capture   # attach tcpdump to every demo pod
#   kind_verify.sh report    # canary hits and tcpdump hits; exit 1 on any
#   kind_verify.sh control   # positive control from load-generator
#   kind_verify.sh down      # delete the cluster
set -euo pipefail

CLUSTER="${CLUSTER:-notel}"
NS="${NS:-notel}"
TAG="${TAG:-latest}"
NODE_MEMORY="${NODE_MEMORY:-4000m}"
# The chart's 75Mi flagd limit made flagd thrash on page cache in kind and
# stalled the whole demo. Set FLAGD_MEMORY=75Mi to run with the chart value.
FLAGD_MEMORY="${FLAGD_MEMORY:-150Mi}"
# AGENTIC=false skips agent, mcp and chatbot.
AGENTIC="${AGENTIC:-true}"
LOCAL_PORT="${LOCAL_PORT:-18080}"
NETSHOOT_IMAGE="${NETSHOOT_IMAGE:-nicolaka/netshoot:v0.13}"
CANARY_IMAGE="python:3.12-alpine"
CHART_REPO="https://open-telemetry.github.io/opentelemetry-helm-charts"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
VERIFY="${ROOT}/notel/verify"
IMAGE_NAME="$(sed -n 's/^IMAGE_NAME=//p' "${ROOT}/.env")"
CANARY_HOSTS="otel-collector otelcol jaeger prometheus grafana opensearch opamp-server tempo zipkin"
TCP_PORTS="4317 4318 55680 55681 9411 14250 14268 9464 8889"
UDP_PORTS="6831 6832"
# Same BPF filter as notel/verify/silence_check.sh: TCP SYNs or UDP to telemetry ports.
FILTER='((tcp[tcpflags] & tcp-syn != 0 and tcp[tcpflags] & tcp-ack == 0) and (dst port 4317 or dst port 4318 or dst port 55680 or dst port 55681 or dst port 9411 or dst port 14250 or dst port 14268)) or (udp and (dst port 6831 or dst port 6832))'
K=(kubectl --context "kind-${CLUSTER}" -n "${NS}")

images() {
  local values="${ROOT}/notel/k8s/values.yaml"
  docker images --format '{{.Repository}}:{{.Tag}}' \
    | grep -E "^${IMAGE_NAME}:${TAG}-" | grep -v -e '-frontend-tests$' -e '-react-native-app$'
  # Third-party images pinned in values.yaml, and the chart's init containers.
  awk '/imageOverride:/{getline r; getline t; sub(/.*: /,"",r); sub(/.*: /,"",t); gsub(/'\''/,"",t); print r ":" t}' "${values}"
  echo busybox:latest
  echo "${CANARY_IMAGE}"
  echo "${NETSHOOT_IMAGE}"
}

canary_manifest() {
  cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: notel-canary
  labels: {app: notel-canary}
spec:
  containers:
    - name: canary
      image: ${CANARY_IMAGE}
      imagePullPolicy: IfNotPresent
      command: ["python", "-u", "/canary/canary.py"]
      volumeMounts: [{name: canary, mountPath: /canary}]
      resources: {limits: {memory: 64Mi}}
  volumes:
    - name: canary
      configMap: {name: notel-canary}
EOF
  for host in ${CANARY_HOSTS}; do
    printf -- '---\napiVersion: v1\nkind: Service\nmetadata:\n  name: %s\nspec:\n  selector: {app: notel-canary}\n  ports:\n' "${host}"
    for p in ${TCP_PORTS}; do printf '    - {name: tcp-%s, port: %s, protocol: TCP}\n' "$p" "$p"; done
    for p in ${UDP_PORTS}; do printf '    - {name: udp-%s, port: %s, protocol: UDP}\n' "$p" "$p"; done
  done
}

demo_pods() {
  "${K[@]}" get pods -l opentelemetry.io/name \
    -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.metadata.labels.app\.kubernetes\.io/component}{"\n"}{end}'
}

case "${1:-}" in
  up)
    # The compose project is named after the checkout directory, so match the
    # network that compose.yaml names explicitly.
    running="$(docker ps --filter network=opentelemetry-demo --format '{{.Names}}')"
    if [ -n "${running}" ]; then
      echo "refusing to start: the notel compose stack is running ($(echo "${running}" | wc -l | tr -d ' ') containers on network opentelemetry-demo)." >&2
      echo "The cluster needs that memory. Stop it first, for example with 'make stop'." >&2
      exit 4
    fi
    kind create cluster --name "${CLUSTER}" --wait 120s
    # Cap the node so that an out-of-memory condition stays inside kind.
    docker update --memory "${NODE_MEMORY}" --memory-swap "${NODE_MEMORY}" "${CLUSTER}-control-plane" >/dev/null
    arch="$(docker version --format '{{.Server.Arch}}')"
    images | sort -u | while read -r img; do
      docker image inspect "${img}" >/dev/null 2>&1 || docker pull -q "${img}" >/dev/null
      echo "loading ${img}"
      docker save --platform "linux/${arch}" "${img}" | docker exec -i "${CLUSTER}-control-plane" \
        ctr --namespace=k8s.io images import - >/dev/null
    done
    kubectl --context "kind-${CLUSTER}" create namespace "${NS}"
    "${K[@]}" create configmap notel-canary --from-file="${VERIFY}/canary.py"
    canary_manifest | "${K[@]}" apply -f - >/dev/null
    "${K[@]}" wait --for=condition=Ready pod/notel-canary --timeout=120s
    helm plugin list 2>/dev/null | grep -q '^notel-strip' || helm plugin install "${HERE}/post-render"
    helm --kube-context "kind-${CLUSTER}" -n "${NS}" install notel opentelemetry-demo \
      --repo "${CHART_REPO}" --version "$(tr -d '[:space:]' < "${HERE}/chart-version")" \
      -f "${HERE}/values.yaml" --set default.image.tag="${TAG}" --post-renderer notel-strip \
      --set components.flagd.resources.limits.memory="${FLAGD_MEMORY}" \
      --set components.agent.enabled="${AGENTIC}" --set components.mcp.enabled="${AGENTIC}" \
      --set components.chatbot.enabled="${AGENTIC}"
    "${K[@]}" wait --for=condition=Ready pods --all --timeout=900s
    "${K[@]}" get pods
    ;;
  smoke)
    "${K[@]}" port-forward svc/frontend-proxy "${LOCAL_PORT}:8080" >/dev/null 2>&1 &
    pf=$!
    trap 'kill ${pf} 2>/dev/null || true' EXIT
    for _ in $(seq 30); do
      curl -s -o /dev/null "http://localhost:${LOCAL_PORT}/" && break
      sleep 1
    done
    fail=0
    for path in / /api/products /feature/ /loadgen/; do
      code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${LOCAL_PORT}${path}" || true)"
      echo "${path} -> ${code}"
      [ "${code}" = "200" ] || fail=1
    done
    curl -s "http://localhost:${LOCAL_PORT}/loadgen/stats/requests" \
      | python3 -c "import json,sys; d=json.load(sys.stdin); t=[s for s in d['stats'] if s['name']=='Aggregated'][0]; print(f\"locust: {t['num_requests']} requests, {t['num_failures']} failures, state {d['state']}\")"
    exit "${fail}"
    ;;
  capture)
    demo_pods | while read -r pod _component; do
      "${K[@]}" get pod "${pod}" -o jsonpath='{.spec.ephemeralContainers[*].name}' | grep -qw notel-silence && continue
      "${K[@]}" debug "pod/${pod}" --image="${NETSHOOT_IMAGE}" --image-pull-policy=IfNotPresent \
        --profile=netadmin --container=notel-silence -- tcpdump -i any -nn -l "${FILTER}" >/dev/null
    done
    echo "tcpdump attached to all $(demo_pods | wc -l | tr -d ' ') demo pods"
    ;;
  report)
    hits=0
    attached=0
    while read -r pod component; do
      out="$("${K[@]}" logs "${pod}" -c notel-silence 2>/dev/null || echo NOT_ATTACHED)"
      if [ "${out}" = "NOT_ATTACHED" ]; then echo "== ${component}: no tcpdump container"; continue; fi
      attached=$((attached + 1))
      out="$(printf '%s\n' "${out}" | grep -v -e 'listening on' -e 'verbose output suppressed' -e 'data link type' -e '^$' || true)"
      [ -z "${out}" ] && continue
      split="$(printf '%s\n' "${out}" | python3 "${VERIFY}/silence_filter.py" "${component}" "${VERIFY}/silence-allowlist.txt")"
      allowed="$(printf '%s\n' "${split}" | sed -n 's/^ALLOWED //p')"
      denied="$(printf '%s\n' "${split}" | sed -n 's/^DENIED //p')"
      if [ -n "${allowed}" ]; then
        echo "== ${component} (allowlisted: $(printf '%s\n' "${allowed}" | wc -l | tr -d ' ') attempts) =="
        printf '%s\n' "${allowed}" | head -3
      fi
      if [ -n "${denied}" ]; then hits=1; echo "== ${component} =="; echo "${denied}"; fi
    done < <(demo_pods)
    canary="$("${K[@]}" logs notel-canary | grep CANARY_HIT || true)"
    if [ -n "${canary}" ]; then hits=1; echo "== notel-canary =="; echo "${canary}"; fi
    if [ "${attached}" -eq 0 ]; then echo "NOT VERIFIED: no tcpdump containers attached" >&2; exit 3; fi
    if [ "${hits}" -eq 0 ]; then echo "SILENT: no unallowlisted telemetry connection attempts (${attached} pods captured)"; fi
    exit "${hits}"
    ;;
  control)
    pod="$(demo_pods | awk '$2 == "load-generator" {print $1}')"
    "${K[@]}" exec "${pod}" -- python -c "import socket
for h in ('otel-collector', 'localhost'):
    try: socket.create_connection((h, 4318), 2).close()
    except OSError: pass"
    echo "positive control sent from ${pod}; 'report' must now exit 1"
    ;;
  down)
    kind delete cluster --name "${CLUSTER}"
    ;;
  *)
    echo "usage: $0 up|smoke|capture|report|control|down" >&2
    exit 2
    ;;
esac
