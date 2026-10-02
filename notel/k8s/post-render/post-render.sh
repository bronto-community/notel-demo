#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Helm post-renderer for notel: reads the rendered manifests on stdin and
# drops the chart's built-in ConfigMaps (upstream flags, PostgreSQL init and
# agent cassettes). notel/k8s/values.yaml mounts notel's own copies instead,
# so nothing references these. Everything else passes through unchanged.
exec awk '
function flush() {
  if (doc != "" && !(configmap && replaced)) printf "%s", doc
  doc = ""; configmap = 0; replaced = 0
}
# A line starting with --- begins a new YAML document.
/^---/ { flush() }
{ doc = doc $0 "\n" }
/^kind: ConfigMap$/ { configmap = 1 }
# metadata.name of one of the replaced ConfigMaps (two-space indent).
/^  name: (flagd-config|postgresql-init|agent-fixtures)$/ { replaced = 1 }
END { flush() }
'
