#!/usr/bin/env bash
# Attach a packet-capture sidecar to every running demo container and record
# outbound connection attempts to well-known telemetry ports, including those
# to localhost (the SDK default endpoint). Usage:
#   silence_check.sh start            # start sidecars
#   silence_check.sh report           # print hits, exit 1 if any
#   silence_check.sh stop             # remove sidecars
set -euo pipefail

NETSHOOT_IMAGE="${NETSHOOT_IMAGE:-nicolaka/netshoot:v0.13}"
PREFIX="notel-silence-"
HERE="$(cd "$(dirname "$0")" && pwd)"
# BPF filter: TCP SYNs (connection attempts) or any UDP to telemetry ports.
FILTER='((tcp[tcpflags] & tcp-syn != 0 and tcp[tcpflags] & tcp-ack == 0) and (dst port 4317 or dst port 4318 or dst port 55680 or dst port 55681 or dst port 9411 or dst port 14250 or dst port 14268)) or (udp and (dst port 6831 or dst port 6832))'

containers() {
  docker ps --filter "network=opentelemetry-demo" --format '{{.Names}}' \
    | grep -v -e "^${PREFIX}" -e '^notel-canary$'
}

case "${1:-}" in
  start)
    if [ -z "$(containers)" ]; then
      echo "no running demo containers on network opentelemetry-demo" >&2
      exit 3
    fi
    for c in $(containers); do
      docker run -d --rm --name "${PREFIX}${c}" --net "container:${c}" \
        "${NETSHOOT_IMAGE}" tcpdump -i any -nn -l "${FILTER}" >/dev/null
    done
    echo "silence sidecars started for: $(containers | tr '\n' ' ')"
    ;;
  report)
    hits=0
    sidecars="$(docker ps --filter "name=^${PREFIX}" --format '{{.Names}}')"
    if [ -z "${sidecars}" ] || ! docker ps --format '{{.Names}}' | grep -qx notel-canary; then
      echo "NOT VERIFIED: no silence sidecars or no canary running; run 'start' against a running stack first" >&2
      exit 3
    fi
    for s in ${sidecars}; do
      name="${s#"${PREFIX}"}"
      out="$(docker logs "${s}" 2>/dev/null | grep -v -e 'listening on' -e 'verbose output suppressed' || true)"
      [ -z "${out}" ] && continue
      split="$(printf '%s\n' "${out}" | python3 "${HERE}/silence_filter.py" "${name}" "${HERE}/silence-allowlist.txt")"
      allowed="$(printf '%s\n' "${split}" | sed -n 's/^ALLOWED //p')"
      denied="$(printf '%s\n' "${split}" | sed -n 's/^DENIED //p')"
      if [ -n "${allowed}" ]; then
        echo "== ${name} (allowlisted: $(printf '%s\n' "${allowed}" | wc -l | tr -d ' ') attempts) =="
        printf '%s\n' "${allowed}" | head -3
      fi
      if [ -n "${denied}" ]; then
        hits=1
        echo "== ${name} =="
        echo "${denied}"
      fi
    done
    canary="$(docker logs notel-canary 2>/dev/null | grep CANARY_HIT || true)"
    if [ -n "${canary}" ]; then
      hits=1
      echo "== notel-canary =="
      echo "${canary}"
    fi
    if [ "${hits}" -eq 0 ]; then echo "SILENT: no unallowlisted telemetry connection attempts recorded"; fi
    exit "${hits}"
    ;;
  stop)
    docker ps --filter "name=^${PREFIX}" -q | xargs -r docker rm -f >/dev/null
    ;;
  *)
    echo "usage: $0 start|report|stop" >&2
    exit 2
    ;;
esac
