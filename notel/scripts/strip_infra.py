#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Remove observability from the non-service parts of the OpenTelemetry Demo.

Deterministic and idempotent. On a fresh upstream tree every edit must find
its anchor, otherwise nothing is written and the script exits non-zero. On an
already stripped tree every edit is a no-op. See notel/scripts/README.md.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT_DIR))
import check_residuals  # noqa: E402

NEW_IMAGE_NAME = "ghcr.io/bronto-community/notel-demo"

DELETE_PATHS = [
    "compose.observability.yaml",
    "compose.profiling.yaml",
    "otel-config.yml",
    "src/otel-collector",
    "src/jaeger",
    "src/prometheus",
    "src/grafana",
    "src/opensearch",
    "src/opamp-server",
    "src/telemetry-docs",
    "telemetry-schema",
    "test/telemetry",
    ".github/workflows/run-telemetry-tests.yml",
    ".github/workflows/run-agentic-telemetry-tests.yml",
]

DELETED_COMPONENTS = [
    "otel-collector",
    "jaeger",
    "prometheus",
    "grafana",
    "opensearch",
    "opamp-server",
    "telemetry-docs",
]

COMPOSE_FILES = [
    "compose.yaml",
    "compose.full.yaml",
    "compose.agent.yaml",
    "compose.extras.yaml",
    "compose.tests.yaml",
]

SCOPE_PATHS = [
    ".chloggen",
    ".env",
    ".env.override",
    ".github",
    ".gitignore",
    ".licenserc.json",
    ".lychee.toml",
    ".markdownlint.yaml",
    ".yamlignore",
    ".yamllint",
    "AGENTS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "Makefile",
    "README.md",
    "buildkitd.toml",
    "docker-gen-proto.sh",
    "ide-gen-proto.sh",
    "internal",
    "package.json",
    "pb",
    "src/frontend-proxy",
    "src/image-provider",
    "src/kafka",
    "src/postgresql",
    "test",
    *COMPOSE_FILES,
    *DELETE_PATHS,
]

# Compose environment variable names that only configure observability.
COMPOSE_ENV_RE = re.compile(
    r"^(OTEL_|PUBLIC_OTEL|WEB_OTEL|TRACELOOP|OPAMP|GRAFANA|JAEGER|PROMETHEUS"
    r"|TELEMETRY_DOCS|FIREPIT|OPENSEARCH)|^AD_PROMETHEUS_PORT$"
)
# .env keys that only configure observability (collector, backends, build args).
DOTENV_KEY_RE = re.compile(
    r"^(OTEL_|OPENTELEMETRY_|PUBLIC_OTEL|WEB_OTEL|OPAMP_|COLLECTOR_|FIREPIT_"
    r"|GRAFANA_|JAEGER|OPENSEARCH_|PROMETHEUS_|TRACELOOP_|TELEMETRY_DOCS_)"
    r"|^(AD_PROMETHEUS_PORT|POSTGRES_MONITORING_PASSWORD|HOST_FILESYSTEM|DOCKER_SOCK)$"
)
DOTENV_MUST_REMOVE = [
    "OTEL_JAVA_AGENT_VERSION",
    "OPENTELEMETRY_CPP_VERSION",
    "OPAMP_GO_REF",
    "COLLECTOR_CONTRIB_IMAGE",
    "OTEL_COLLECTOR_HOST",
    "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE",
    "AD_PROMETHEUS_PORT",
    "GRAFANA_HOST",
    "TRACELOOP_BASE_URL",
    "FIREPIT_HOST",
    "TELEMETRY_DOCS_HOST",
    "POSTGRES_MONITORING_PASSWORD",
]
BUILD_ARGS_REMOVE = {"OTEL_JAVA_AGENT_VERSION", "OPENTELEMETRY_CPP_VERSION"}
# Compose port mappings that only exist for observability endpoints.
COMPOSE_PORT_RE = re.compile(r"\$\{(AD_PROMETHEUS_PORT|OTEL_COLLECTOR_\w+)\}")
# Compose volume mounts of the deleted OTel declarative config file.
COMPOSE_VOLUME_RE = re.compile(r"otel-config\.yml")
# The astronomy-db command that only preloads pg_stat_statements.
PG_COMMAND_RE = re.compile(r"^\s*command:\s*postgres -c shared_preload_libraries=pg_stat_statements\s*$")

ENVOY_ROUTES_REMOVE = ["otlp-http", "jaeger", "grafana", "opamp", "telemetry", "profiles"]
ENVOY_CLUSTERS_REMOVE = [
    "opentelemetry_collector_grpc",
    "opentelemetry_collector_http",
    "grafana",
    "jaeger",
    "opamp",
    "telemetry-docs",
    "profiles",
]

# The previous OTel access log body format (YAML double-quoted string content).
ENVOY_ACCESS_LOG_FORMAT = '[%START_TIME%] \\"%REQ(:METHOD)% %REQ(X-ENVOY-ORIGINAL-PATH?:PATH)% %PROTOCOL%\\" %RESPONSE_CODE% %RESPONSE_FLAGS% %RESPONSE_CODE_DETAILS% %CONNECTION_TERMINATION_DETAILS% \\"%UPSTREAM_TRANSPORT_FAILURE_REASON%\\" %BYTES_RECEIVED% %BYTES_SENT% %DURATION% %RESP(X-ENVOY-UPSTREAM-SERVICE-TIME)% \\"%REQ(X-FORWARDED-FOR)%\\" \\"%REQ(USER-AGENT)%\\" \\"%REQ(X-REQUEST-ID)%\\" \\"%REQ(:AUTHORITY)%\\" \\"%UPSTREAM_HOST%\\" %UPSTREAM_CLUSTER% %UPSTREAM_LOCAL_ADDRESS% %DOWNSTREAM_LOCAL_ADDRESS% %DOWNSTREAM_REMOTE_ADDRESS% %REQUESTED_SERVER_NAME% %ROUTE_NAME%\\n'
STDOUT_LOGGER_TEMPLATE = [
    "access_log:",
    "  - name: envoy.access_loggers.stdout",
    "    typed_config:",
    "      \"@type\": type.googleapis.com/envoy.extensions.access_loggers.stream.v3.StdoutAccessLog",
    "      log_format:",
    "        text_format_source:",
    "          # yamllint disable-line rule:line-length",
    "          inline_string: \"{fmt}\"",
]

MAKE_TARGETS_REMOVE = [
    "build-agentic",
    "run-telemetry-tests",
    "run-telemetry-tests-minimal",
    "run-telemetry-tests-agentic",
    "start-no-o11y",
    "start-minimal-no-o11y",
    "start-profiling",
]


class StripError(Exception):
    pass


# --------------------------------------------------------------------------
# Generic line helpers (YAML-indentation aware, no YAML library)
# --------------------------------------------------------------------------

def ind(s):
    return len(s) - len(s.lstrip(" "))


def blank(s):
    return not s.strip()


def comment(s):
    return s.lstrip().startswith("#")


def content(s):
    return not blank(s) and not comment(s)


# A YAML mapping key, optionally after a list dash; group 1 is the key name.
KEY_RE = re.compile(r"^\s*(?:-\s+)?[\"']?([^\"'\s:#][^\"':#]*?)[\"']?\s*:(?:\s|$)")
# A YAML block sequence item line.
ITEM_RE = re.compile(r"^\s*-(?:\s|$)")
# The variable name of a compose environment list item such as `- "FOO=bar"`.
ENV_ITEM_RE = re.compile(r"^\s*-\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)")


def key_of(s):
    m = KEY_RE.match(s)
    return m.group(1) if m else None


def is_item(s):
    return bool(ITEM_RE.match(s))


def node_end(lines, i):
    """Index just past the last line that belongs to the node starting at i."""
    base = ind(lines[i])
    last = i
    for j in range(i + 1, len(lines)):
        s = lines[j]
        if blank(s):
            continue
        if comment(s):
            if ind(s) > base:
                last = j
            continue
        if ind(s) <= base:
            break
        last = j
    return last + 1


def children(lines, i):
    """Line indices of the direct children of node i (None is the document)."""
    start, end = (0, len(lines)) if i is None else (i + 1, node_end(lines, i))
    child_indent = None
    out = []
    for j in range(start, end):
        if content(lines[j]):
            if child_indent is None:
                child_indent = ind(lines[j])
            if ind(lines[j]) == child_indent:
                out.append(j)
    return out


def find_path(lines, path):
    """Locate a mapping key by its key path from the document root."""
    i = None
    for k in path:
        nxt = None
        for c in children(lines, i):
            if not is_item(lines[c]) and key_of(lines[c]) == k:
                nxt = c
                break
        if nxt is None:
            return None
        i = nxt
    return i


def fix_junction(lines, s):
    """Avoid double blank lines (and trailing blanks) where lines were removed."""
    if s < len(lines):
        if blank(lines[s]) and (s == 0 or blank(lines[s - 1])):
            del lines[s]
    else:
        while lines and blank(lines[-1]):
            lines.pop()


def delete_range(lines, s, e, leading_comments=True):
    if leading_comments:
        while s > 0 and comment(lines[s - 1]) and ind(lines[s - 1]) == ind(lines[s]):
            s -= 1
    del lines[s:e]
    fix_junction(lines, s)


def remove_node(lines, i, leading_comments=True):
    delete_range(lines, i, node_end(lines, i), leading_comments)


def remove_if_empty(lines, i):
    """Remove a `key:` line whose block no longer has any content."""
    if i is None:
        return 0
    # A bare `key:` line with no inline value.
    if not re.match(r"^\s*[^#]*:\s*$", lines[i]):
        return 0
    if any(content(lines[j]) for j in range(i + 1, node_end(lines, i))):
        return 0
    remove_node(lines, i, leading_comments=False)
    return 1


def node_text(lines, i):
    return "\n".join(lines[i:node_end(lines, i)])


def filter_children(lines, path_or_idx, pred):
    """Remove children (items or keys) of a node for which pred is true.

    path_or_idx is a key path (re-resolved after each removal) or a callable
    returning the parent index. Returns the first line of each removed child.
    """
    removed = []

    def parent():
        if callable(path_or_idx):
            return path_or_idx()
        return find_path(lines, path_or_idx)

    while True:
        p = parent()
        if p is None:
            return removed
        for c in children(lines, p):
            if pred(lines, c):
                removed.append(lines[c].strip())
                remove_node(lines, c)
                break
        else:
            return removed


def remove_lines(lines, regex, leading_comments=False):
    n = 0
    i = 0
    while i < len(lines):
        if regex.search(lines[i]):
            delete_range(lines, i, i + 1, leading_comments)
            n += 1
            i = max(i - 2, 0)
            continue
        i += 1
    return n


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------

class Ctx:
    def __init__(self, root, strict):
        self.root = root
        self.strict = strict
        self.files = {}
        self.original = {}
        self.trailing_nl = {}
        self.errors = []
        self.log = []

    def lines(self, rel):
        if rel not in self.files:
            p = self.root / rel
            if not p.is_file():
                raise StripError(f"{rel}: file not found")
            text = p.read_text(encoding="utf-8")
            self.original[rel] = text
            self.trailing_nl[rel] = text.endswith("\n")
            body = text[:-1] if text.endswith("\n") else text
            self.files[rel] = body.split("\n")
        return self.files[rel]

    def text(self, rel):
        return "\n".join(self.lines(rel))

    def set_text(self, rel, text):
        self.files[rel][:] = text.split("\n")

    def expect(self, rel, count, what, required=True):
        if count:
            detail = count if not isinstance(count, list) else ", ".join(count)
            self.log.append(f"{rel}: {what}: {detail}")
        elif required and self.strict:
            self.errors.append(f"{rel}: expected anchor not found: {what}")

    def changed(self):
        out = {}
        for rel, lines in self.files.items():
            orig_last = self.original[rel].rstrip("\n").split("\n")[-1]
            nl = self.trailing_nl[rel] or (bool(lines) and lines[-1] != orig_last)
            text = "\n".join(lines) + ("\n" if nl else "")
            if text != self.original[rel]:
                out[rel] = text
        return out


def replace_text(ctx, rel, old, new, what, count=1):
    text = ctx.text(rel)
    n = text.count(old)
    if n == 0:
        if new and new in text:
            return
        ctx.expect(rel, 0, what)
        return
    if n != count:
        ctx.errors.append(f"{rel}: '{what}' matched {n} times, expected {count}")
        return
    ctx.set_text(rel, text.replace(old, new))
    ctx.expect(rel, n, what)


def sub_lines(ctx, rel, regex, repl, what, required=True):
    lines = ctx.lines(rel)
    n = 0
    for i, s in enumerate(lines):
        new = regex.sub(repl, s)
        if new != s:
            lines[i] = new
            n += 1
    ctx.expect(rel, n, what, required)


# --------------------------------------------------------------------------
# Compose
# --------------------------------------------------------------------------

def service_names(lines):
    svc = find_path(lines, ["services"])
    if svc is None:
        return []
    return [key_of(lines[c]) for c in children(lines, svc)]


def strip_compose(ctx, rel):
    lines = ctx.lines(rel)
    removed_services = []
    for name in service_names(lines):
        if name in DELETED_COMPONENTS:
            remove_node(lines, find_path(lines, ["services", name]))
            removed_services.append(name)

    env_removed, deps_removed, args_removed, ports_removed, vols_removed = [], [], [], [], []
    for name in service_names(lines):
        base = ["services", name]

        def env_pred(ls, c):
            if is_item(ls[c]):
                m = ENV_ITEM_RE.match(ls[c])
                return bool(m and COMPOSE_ENV_RE.search(m.group(1)))
            k = key_of(ls[c])
            return bool(k and COMPOSE_ENV_RE.search(k))

        env_removed += filter_children(lines, base + ["environment"], env_pred)
        remove_if_empty(lines, find_path(lines, base + ["environment"]))

        def dep_pred(ls, c):
            k = ls[c].strip()[1:].strip().strip("\"'") if is_item(ls[c]) else key_of(ls[c])
            return k in DELETED_COMPONENTS

        deps_removed += [f"{name}->{d.rstrip(':').lstrip('- ')}"
                         for d in filter_children(lines, base + ["depends_on"], dep_pred)]
        remove_if_empty(lines, find_path(lines, base + ["depends_on"]))

        args_removed += filter_children(
            lines, base + ["build", "args"],
            lambda ls, c: key_of(ls[c]) in BUILD_ARGS_REMOVE)
        remove_if_empty(lines, find_path(lines, base + ["build", "args"]))

        ports_removed += filter_children(
            lines, base + ["ports"], lambda ls, c: bool(COMPOSE_PORT_RE.search(ls[c])))
        remove_if_empty(lines, find_path(lines, base + ["ports"]))

        vols_removed += filter_children(
            lines, base + ["volumes"], lambda ls, c: bool(COMPOSE_VOLUME_RE.search(ls[c])))
        remove_if_empty(lines, find_path(lines, base + ["volumes"]))

    is_core = rel == "compose.yaml"
    is_full = rel == "compose.full.yaml"
    is_agent = rel == "compose.agent.yaml"
    ctx.expect(rel, removed_services, "removed services", is_core or is_full)
    if is_core:
        for svc in ("otel-collector", "telemetry-docs"):
            if svc not in removed_services:
                ctx.expect(rel, 0, f"service {svc}")
    # Strips the `=value` part to log only variable names.
    ctx.expect(rel, sorted({re.sub(r"[=\s].*", "", e.lstrip("- \"'")) for e in env_removed}),
               "removed env vars", is_core or is_full or is_agent)
    ctx.expect(rel, deps_removed, "removed depends_on", is_core or is_full or is_agent)
    ctx.expect(rel, args_removed, "removed build args", is_core or is_full)
    ctx.expect(rel, ports_removed, "removed ports", is_core)
    ctx.expect(rel, vols_removed, "removed volumes", is_core)

    cmd = find_path(lines, ["services", "astronomy-db", "command"])
    n = 0
    if cmd is not None:
        if PG_COMMAND_RE.match(lines[cmd]):
            remove_node(lines, cmd, leading_comments=False)
            n = 1
        elif "pg_stat_statements" in node_text(lines, cmd):
            ctx.errors.append(f"{rel}: astronomy-db command changed upstream, edit manually")
    ctx.expect(rel, n, "removed astronomy-db pg_stat_statements command", is_core)

    n = remove_empty_banners(lines)
    ctx.expect(rel, n, "removed empty section banners", is_core)
    strip_compose_header(ctx, rel)


# A section banner line made of asterisks, e.g. `# ******`.
BANNER_RE = re.compile(r"^\s*#\s*\*{4,}\s*$")


def remove_empty_banners(lines):
    """Remove 3-line `# ***` / `# Title` / `# ***` banners with nothing below."""
    n = 0
    i = 0
    while i + 2 < len(lines):
        if BANNER_RE.match(lines[i]) and BANNER_RE.match(lines[i + 2]) and comment(lines[i + 1]):
            j = i + 3
            empty = True
            while j < len(lines):
                s = lines[j]
                if blank(s) or (comment(s) and not BANNER_RE.match(s)):
                    j += 1
                    continue
                empty = BANNER_RE.match(s) is not None or ind(s) < ind(lines[i])
                break
            if empty:
                delete_range(lines, i, i + 3, leading_comments=False)
                n += 1
                continue
        i += 1
    return n


# Header usage labels whose example command only made sense with observability.
HEADER_LABEL_RE = re.compile(r"^#\s+(With observability stack\b.*|Default \(full \+ observability\)):\s*$")
# A commented `docker compose ...` example command line.
HEADER_CMD_RE = re.compile(r"^#\s+docker compose\b")
# A commented continuation line that only adds the observability compose file.
HEADER_OBS_CONT_RE = re.compile(r"^#\s+-f compose\.observability\.yaml\s*\\\s*$")
# An inline ` -f compose.observability.yaml` within a commented command.
HEADER_OBS_FLAG_RE = re.compile(r" -f compose\.observability\.yaml")


def strip_compose_header(ctx, rel):
    lines = ctx.lines(rel)
    n = 0
    i = 0
    while i < len(lines) and (comment(lines[i]) or blank(lines[i])):
        s = lines[i]
        if HEADER_LABEL_RE.match(s):
            end = i + 2 if i + 1 < len(lines) and HEADER_CMD_RE.match(lines[i + 1]) else i + 1
            del lines[i:end]
            n += 1
            continue
        if HEADER_OBS_CONT_RE.match(s):
            del lines[i]
            n += 1
            continue
        if HEADER_OBS_FLAG_RE.search(s):
            lines[i] = HEADER_OBS_FLAG_RE.sub("", s)
            n += 1
        i += 1
    ctx.expect(rel, n, "edited header comments", rel in ("compose.yaml", "compose.agent.yaml",
                                                         "compose.extras.yaml"))


def strip_compose_extras_example(ctx):
    old = (
        "# Example: add a service and patch the otel-collector to export to it:\n"
        "#\n"
        "# services:\n"
        "#   my-backend:\n"
        "#     image: myvendor/backend:latest\n"
        "#     ports:\n"
        "#       - \"4317\"\n"
        "#\n"
        "#   otel-collector:\n"
        "#     depends_on:\n"
        "#       my-backend:\n"
        "#         condition: service_started\n"
        "#\n"
        "# Then add your exporter config to src/otel-collector/otelcol-config-extras.yml."
    )
    new = (
        "# Example: add a service:\n"
        "#\n"
        "# services:\n"
        "#   my-backend:\n"
        "#     image: myvendor/backend:latest\n"
        "#     ports:\n"
        "#       - \"4317\""
    )
    replace_text(ctx, "compose.extras.yaml", old, new, "otel-collector example in header")


# --------------------------------------------------------------------------
# .env files
# --------------------------------------------------------------------------

# A dotenv assignment, optionally commented out; group 1 is the key.
DOTENV_ASSIGN_RE = re.compile(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)=")


def dotenv_key(s):
    if comment(s):
        m = DOTENV_ASSIGN_RE.match(s)
        # A commented-out assignment such as `# FOO=bar` (not prose).
        return m.group(1) if m and re.match(r"^\s*#\s?[A-Z_][A-Z0-9_]*=", s) else None
    m = DOTENV_ASSIGN_RE.match(s)
    return m.group(1) if m else None


def strip_dotenv(ctx, rel, required_keys):
    lines = ctx.lines(rel)
    out = []
    removed = []
    i = 0
    while i < len(lines):
        if blank(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and not blank(lines[j]):
            j += 1
        block = lines[i:j]
        keys = [k for k in (dotenv_key(s) for s in block) if k]
        kept = []
        for s in block:
            k = dotenv_key(s)
            if k and DOTENV_KEY_RE.search(k):
                removed.append(k)
                if any(dotenv_key(x) for x in kept):
                    while kept and comment(kept[-1]) and not dotenv_key(kept[-1]):
                        kept.pop()
                continue
            kept.append(s)
        if keys and not any(dotenv_key(s) for s in kept):
            if out and blank(out[-1]):
                out.pop()
            if not out:
                while j < len(lines) and blank(lines[j]):
                    j += 1
        else:
            out.extend(kept)
        i = j
    while out and blank(out[-1]):
        out.pop()
    lines[:] = out
    ctx.expect(rel, removed, "removed keys")
    if ctx.strict:
        for k in required_keys:
            if k not in removed:
                ctx.errors.append(f"{rel}: expected key not found: {k}")


def set_image_name(ctx):
    lines = ctx.lines(".env")
    idx = [i for i, s in enumerate(lines) if s.startswith("IMAGE_NAME=")]
    if len(idx) != 1:
        ctx.errors.append(".env: expected exactly one IMAGE_NAME line")
        return
    new = f"IMAGE_NAME={NEW_IMAGE_NAME}"
    if lines[idx[0]] != new:
        lines[idx[0]] = new
        ctx.expect(".env", 1, "set IMAGE_NAME")


# --------------------------------------------------------------------------
# Makefile
# --------------------------------------------------------------------------

def remove_make_target(lines, name):
    # The rule line `name:` of a make target (not a `name := value` assignment).
    rule = re.compile(rf"^{re.escape(name)}\s*:(?!=)")
    for i, s in enumerate(lines):
        if rule.match(s):
            break
    else:
        return 0
    e = i + 1
    while e < len(lines) and (lines[e].startswith("\t") or lines[e - 1].endswith("\\")):
        e += 1
    s = i
    # The `.PHONY: name` line directly above the rule.
    if s > 0 and re.match(rf"^\.PHONY:\s*{re.escape(name)}\s*$", lines[s - 1]):
        s -= 1
    while s > 0 and lines[s - 1].startswith("#"):
        s -= 1
    del lines[s:e]
    fix_junction(lines, s)
    return 1


def strip_makefile(ctx):
    rel = "Makefile"
    lines = ctx.lines(rel)
    removed = [t for t in MAKE_TARGETS_REMOVE if remove_make_target(lines, t)]
    ctx.expect(rel, removed, "removed targets")
    if ctx.strict:
        for t in MAKE_TARGETS_REMOVE:
            if t not in removed:
                ctx.errors.append(f"{rel}: expected target not found: {t}")

    # Variables for the deleted compose layers.
    n = remove_lines(lines, re.compile(r"^DOCKER_COMPOSE_FILES_(OBSERVABILITY|PROFILING)\s*[:?]?="))
    ctx.expect(rel, n, "removed observability/profiling compose file vars")
    # The layer description comment for the observability compose file.
    n = remove_lines(lines, re.compile(r"^#\s+With observability stack:.*compose\.observability\.yaml\s*$"))
    ctx.expect(rel, n, "removed observability layer comment")
    replace_text(ctx, rel, "# Default: full demo + observability stack + extras stub",
                 "# Default: full demo + extras stub", "default compose files comment")
    # References to the observability compose file variable in recipes.
    sub_lines(ctx, rel, re.compile(r" \$\(DOCKER_COMPOSE_FILES_OBSERVABILITY\)"), "",
              "removed $(DOCKER_COMPOSE_FILES_OBSERVABILITY) uses")
    # Recipe lines that use the profiling compose file (stop target).
    n = remove_lines(lines, re.compile(r"\$\(DOCKER_COMPOSE_FILES_PROFILING\)"))
    ctx.expect(rel, n, "removed profiling recipe lines")
    # Echo hints for UIs served by deleted components.
    n = remove_lines(lines, re.compile(
        r"^\t@echo \"Go to http://localhost:8080/(jaeger|grafana|telemetry|profiles)/"))
    ctx.expect(rel, n, "removed echo lines for deleted UIs")
    # The unused semconvgen pin and its comment.
    n = remove_lines(lines, re.compile(
        r"^(SEMCONVGEN_VERSION=|# see https://github\.com/open-telemetry/build-tools/releases"
        r"|# Keep links in semantic_conventions/README\.md)"))
    ctx.expect(rel, n, "removed unused SEMCONVGEN_VERSION")


# --------------------------------------------------------------------------
# frontend-proxy (Envoy)
# --------------------------------------------------------------------------

# An Envoy route match on one of the deleted observability paths.
ENVOY_ROUTE_RE = re.compile(
    r"-\s*match:\s*\{\s*(?:path|prefix):\s*\"/(" + "|".join(map(re.escape, ENVOY_ROUTES_REMOVE))
    + r")/?\"\s*\}")
# An Envoy cluster list item for one of the deleted observability backends.
ENVOY_CLUSTER_RE = re.compile(
    r"^\s*-\s*name:\s*(" + "|".join(map(re.escape, ENVOY_CLUSTERS_REMOVE)) + r")\s*$")
# A YAML anchor definition such as `&dns_resolver`; group 1 is the anchor name.
ANCHOR_RE = re.compile(r"&([A-Za-z0-9_-]+)")


def strip_envoy(ctx):
    rel = "src/frontend-proxy/envoy.tmpl.yaml"
    lines = ctx.lines(rel)

    # The HttpConnectionManager tracing block.
    idx = [i for i, s in enumerate(lines) if re.match(r"^\s+tracing:\s*$", s)]
    for i in reversed(idx):
        remove_node(lines, i)
    ctx.expect(rel, len(idx), "removed tracing block")

    def access_log_parent():
        for i, s in enumerate(lines):
            # An `access_log:` key of the connection manager.
            if re.match(r"^\s+access_log:\s*$", s) and "open_telemetry" in node_text(lines, i):
                return i
        return None

    fmt = ENVOY_ACCESS_LOG_FORMAT
    p = access_log_parent()
    if p is not None:
        for j in range(p, node_end(lines, p)):
            # The quoted `string_value` of the OTel access log body.
            m = re.match(r'^\s+string_value:\s*"(\[%START_TIME%\].*)"\s*$', lines[j])
            if m:
                fmt = m.group(1)
                break
    removed = filter_children(lines, access_log_parent,
                              lambda ls, c: "envoy.access_loggers.open_telemetry" in node_text(ls, c))
    ctx.expect(rel, removed, "removed OTel access loggers")
    for i, s in enumerate(lines):
        # An `access_log:` key of the connection manager.
        if re.match(r"^\s+access_log:\s*$", s):
            remove_if_empty(lines, i)
            break
    ctx.expect(rel, add_stdout_access_log(ctx, lines, fmt), "added stdout access log",
               required=False)

    def routes_parent():
        for i, s in enumerate(lines):
            # The `routes:` key of the virtual host.
            if re.match(r"^\s+routes:\s*$", s):
                return i
        return None

    removed = filter_children(lines, routes_parent, lambda ls, c: bool(ENVOY_ROUTE_RE.search(ls[c])))
    ctx.expect(rel, removed, "removed routes")
    if ctx.strict:
        for r in ENVOY_ROUTES_REMOVE:
            if not any(f'"/{r}' in x for x in removed):
                ctx.errors.append(f"{rel}: expected route not found: /{r}")

    removed = []
    while True:
        clusters = find_path(lines, ["static_resources", "clusters"])
        if clusters is None:
            break
        hit = next((c for c in children(lines, clusters) if ENVOY_CLUSTER_RE.match(lines[c])), None)
        if hit is None:
            break
        removed.append(ENVOY_CLUSTER_RE.match(lines[hit]).group(1))
        transplant_anchors(lines, hit)
        remove_node(lines, hit)
    ctx.expect(rel, removed, "removed clusters")
    if ctx.strict:
        for c in ENVOY_CLUSTERS_REMOVE:
            if c not in removed:
                ctx.errors.append(f"{rel}: expected cluster not found: {c}")


def add_stdout_access_log(ctx, lines, fmt):
    """Add an Envoy stdout access logger next to the HTTP filters."""
    if any("envoy.access_loggers.stdout" in s for s in lines):
        return 0
    # The `http_filters:` key of the HttpConnectionManager.
    idx = [i for i, s in enumerate(lines) if re.match(r"^\s+http_filters:\s*$", s)]
    if len(idx) != 1:
        ctx.errors.append("envoy.tmpl.yaml: expected exactly one http_filters key")
        return 0
    pad = " " * ind(lines[idx[0]])
    block = [pad + t.replace("{fmt}", fmt) for t in STDOUT_LOGGER_TEMPLATE]
    end = node_end(lines, idx[0])
    lines[end:end] = block
    return 1


def transplant_anchors(lines, item):
    """Move anchor definitions out of a node about to be removed.

    The definition replaces the first alias that is outside the node, so the
    remaining aliases keep resolving.
    """
    end = node_end(lines, item)
    for i in range(item, end):
        m = ANCHOR_RE.search(lines[i])
        if not m:
            continue
        name = m.group(1)
        def_end = node_end(lines, i)
        definition = lines[i:def_end]
        # An alias usage `key: *name` of the anchor being moved.
        alias_re = re.compile(rf"^(\s*)([^#\s][^:]*):\s*\*{re.escape(name)}\s*$")
        for j in range(end, len(lines)):
            a = alias_re.match(lines[j])
            if a:
                delta = ind(lines[j]) - ind(definition[0])
                moved = [(" " * delta + s) if delta >= 0 else s[-delta:] for s in definition]
                lines[j:j + 1] = moved
                return


def strip_frontend_proxy_dockerfile(ctx):
    rel = "src/frontend-proxy/Dockerfile"
    # An OTel variable inside an envsubst variable list.
    sub_lines(ctx, rel, re.compile(r" ?\$\{?OTEL_\w+\}?"), "", "removed OTEL vars from envsubst",
              required=False)


# --------------------------------------------------------------------------
# image-provider (nginx)
# --------------------------------------------------------------------------

# A FROM line using the nginx `-otel` image variant, with an optional digest.
NGINX_FROM_RE = re.compile(r"^(FROM\s+)(\S+?):(\S+?)-otel(?:@sha256:[0-9a-f]{64})?(\s.*)?$")


def resolve_digest(ref):
    try:
        out = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", "--format", "{{json .Manifest.Digest}}", ref],
            check=True, capture_output=True, text=True, timeout=120).stdout.strip().strip('"')
    except (OSError, subprocess.SubprocessError) as e:
        raise StripError(f"could not resolve digest for {ref}: {e}") from e
    # A sha256 image digest.
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", out):
        raise StripError(f"unexpected digest for {ref}: {out!r}")
    return out


def strip_image_provider(ctx, digest_mode):
    rel = "src/image-provider/Dockerfile"
    lines = ctx.lines(rel)
    n = 0
    for i, s in enumerate(lines):
        m = NGINX_FROM_RE.match(s)
        if m:
            ref = f"{m.group(2)}:{m.group(3)}"
            if digest_mode == "none":
                pinned = ref
            elif digest_mode == "resolve":
                pinned = f"{ref}@{resolve_digest(ref)}"
            else:
                pinned = f"{ref}@{digest_mode}"
            lines[i] = f"{m.group(1)}{pinned}{m.group(4) or ''}"
            n += 1
    ctx.expect(rel, n, "switched nginx base image from -otel variant")
    # An OTel variable inside the envsubst variable list.
    sub_lines(ctx, rel, re.compile(r" ?\$\{?OTEL_\w+\}?"), "", "removed OTEL vars from envsubst")
    # A leading space left in the envsubst list after removing the first variable.
    sub_lines(ctx, rel, re.compile(r"envsubst ' "), "envsubst '", "normalized envsubst list",
              required=False)

    rel = "src/image-provider/nginx.conf.template"
    lines = ctx.lines(rel)
    # The dynamic module load of the nginx OTel module.
    n = remove_lines(lines, re.compile(r"^\s*load_module\s+\S*ngx_otel_module\.so;\s*$"))
    ctx.expect(rel, n, "removed load_module ngx_otel_module")
    n = 0
    i = 0
    while i < len(lines):
        # The opening of the `otel_exporter { ... }` block.
        if re.match(r"^\s*otel_exporter\s*\{", lines[i]):
            depth = 0
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if depth == 0:
                    break
            else:
                ctx.errors.append(f"{rel}: unbalanced otel_exporter block")
                return
            delete_range(lines, i, j + 1, leading_comments=False)
            n += 1
            continue
        i += 1
    ctx.expect(rel, n, "removed otel_exporter block")
    # Any other `otel_*` nginx directive.
    n = remove_lines(lines, re.compile(r"^\s*otel_\w+\s+[^;]*;\s*$"))
    ctx.expect(rel, n, "removed otel_* directives")
    i = 0
    while i + 1 < len(lines):
        if lines[i].rstrip().endswith("{") and blank(lines[i + 1]):
            del lines[i + 1]
            continue
        i += 1
    # The `location /status` block used by the compose healthcheck.
    if not any(re.search(r"location\s+/status\b", s) for s in lines):
        ctx.errors.append(f"{rel}: /status location missing, the healthcheck depends on it")


# --------------------------------------------------------------------------
# kafka
# --------------------------------------------------------------------------

def strip_kafka(ctx):
    rel = "src/kafka/Dockerfile"
    lines = ctx.lines(rel)
    # The build arg for the OTel Java agent version.
    n_arg = remove_lines(lines, re.compile(r"^ARG\s+OTEL_JAVA_AGENT_VERSION\b"))
    ctx.expect(rel, n_arg, "removed ARG OTEL_JAVA_AGENT_VERSION")
    for s in lines:
        if "opentelemetry-javaagent" in s and s.rstrip().endswith("\\"):
            ctx.errors.append(f"{rel}: multi-line javaagent ADD, edit manually")
            return
    # The ADD that downloads the OTel Java agent jar.
    n_add = remove_lines(lines, re.compile(r"^ADD\s.*opentelemetry-javaagent\.jar"))
    ctx.expect(rel, n_add, "removed javaagent ADD")
    n_opts = 0
    for i, s in enumerate(lines):
        # The KAFKA_OPTS ENV line; group 1 is the quoted value.
        m = re.match(r'^ENV KAFKA_OPTS="(.*)"\s*$', s)
        if not m:
            continue
        tokens = m.group(1).split()
        kept = [t for t in tokens if not (t.startswith("-javaagent:") or t.startswith("-Dotel."))]
        if kept != tokens:
            n_opts += 1
            if kept:
                lines[i] = f'ENV KAFKA_OPTS="{" ".join(kept)}"'
            else:
                delete_range(lines, i, i + 1, leading_comments=False)
            break
    ctx.expect(rel, n_opts, "removed -javaagent/otel.jmx from KAFKA_OPTS")
    if bool(n_add) != bool(n_opts):
        ctx.errors.append(f"{rel}: javaagent ADD and KAFKA_OPTS must be removed together")
    if any("javaagent" in s for s in lines):
        ctx.errors.append(f"{rel}: javaagent reference remains")


# --------------------------------------------------------------------------
# postgresql
# --------------------------------------------------------------------------

def strip_postgres(ctx):
    rel = "src/postgresql/init.sql"
    lines = ctx.lines(rel)
    # SQL lines that touch the monitoring role or pg_stat_statements.
    target = re.compile(r"monitoring_user|pg_stat_statements", re.I)
    n = 0
    i = 0
    while i < len(lines):
        if target.search(lines[i]) and not lines[i].lstrip().startswith("--"):
            prev = next((lines[k] for k in range(i - 1, -1, -1)
                         if lines[k].strip() and not lines[k].lstrip().startswith("--")), ";")
            prev_done = prev.rstrip().endswith(";") or prev.lstrip().startswith("\\")
            if not lines[i].rstrip().endswith(";") or not prev_done:
                ctx.errors.append(f"{rel}:{i + 1}: multi-line statement, edit manually")
                return
            s = i
            while s > 0 and lines[s - 1].lstrip().startswith("--"):
                s -= 1
            del lines[s:i + 1]
            fix_junction(lines, s)
            n += 1
            i = max(s - 1, 0)
            continue
        i += 1
    ctx.expect(rel, n, "removed monitoring_user/pg_stat_statements statements")
    for k, s in enumerate(lines):
        if target.search(s):
            ctx.errors.append(f"{rel}:{k + 1}: residual reference: {s.strip()}")


# --------------------------------------------------------------------------
# .github
# --------------------------------------------------------------------------

def deleted_dir_re(prefix=""):
    # A path into one of the deleted component dirs, e.g. `./src/opensearch/`.
    return re.compile(prefix + r"src/(" + "|".join(map(re.escape, DELETED_COMPONENTS)) + r")/")


def strip_github(ctx):
    rel = ".github/workflows/checks.yml"
    lines = ctx.lines(rel)
    n = 0
    job = find_path(lines, ["jobs", "weaver-check"])
    if job is not None:
        remove_node(lines, job)
        n = 1
    ctx.expect(rel, n, "removed weaver-check job")
    # weaver-check as an entry of a `needs:` flow sequence.
    n = remove_lines(lines, re.compile(r"^\s+weaver-check,?\s*$"))
    ctx.expect(rel, n, "removed weaver-check from needs")
    if any("weaver" in s.lower() for s in lines):
        ctx.errors.append(f"{rel}: weaver reference remains")

    rel = ".github/workflows/component-build-images.yml"
    lines = ctx.lines(rel)
    path = ["jobs", "build_and_push_images", "strategy", "matrix", "file_tag"]
    rx = deleted_dir_re(r"\./")
    removed = filter_children(lines, path, lambda ls, c: bool(rx.search(node_text(ls, c))))
    ctx.expect(rel, removed, "removed matrix entries")
    n = 0
    i = 0
    while i < len(lines):
        # A `build-args: |` block scalar of a build step.
        if re.match(r"^\s+build-args:\s*\|\s*$", lines[i]):
            end = node_end(lines, i)
            # A build arg that only feeds OTel agents, SDKs or OpAMP.
            arg_re = re.compile(r"^\s+(OTEL_JAVA_AGENT_VERSION|OPENTELEMETRY_CPP_VERSION|OPAMP_GO_REF)=")
            keep = [s for s in lines[i + 1:end] if not arg_re.match(s)]
            if len(keep) != end - i - 1:
                n += end - i - 1 - len(keep)
                lines[i:end] = ([lines[i]] + keep) if any(content(s) for s in keep) else []
        i += 1
    ctx.expect(rel, n, "removed OTel build args")

    rel = ".github/workflows/label-pr.yml"
    # A paths-filter glob for one of the deleted component dirs.
    n = remove_lines(ctx.lines(rel), re.compile(
        r"^\s*-\s*'src/(" + "|".join(map(re.escape, DELETED_COMPONENTS)) + r")/\*\*'\s*$"))
    ctx.expect(rel, n, "removed paths for deleted dirs")

    rel = ".github/dependabot.yml"
    lines = ctx.lines(rel)
    rx = deleted_dir_re(r"\"/")
    removed = filter_children(lines, ["updates"], lambda ls, c: bool(rx.search(node_text(ls, c))))
    groups = {f"src-{c}" for c in DELETED_COMPONENTS}
    removed += filter_children(lines, ["multi-ecosystem-groups"],
                               lambda ls, c: key_of(ls[c]) in groups)
    ctx.expect(rel, removed, "removed entries for deleted dirs")

    rel = ".github/component_owners.yml"
    owners = {f"src/{c}" for c in DELETED_COMPONENTS}
    removed = filter_children(ctx.lines(rel), ["components"], lambda ls, c: key_of(ls[c]) in owners)
    ctx.expect(rel, removed, "removed owners for deleted dirs", required=False)

    replace_text(
        ctx, ".github/PULL_REQUEST_TEMPLATE.md",
        "A Pull Request that modifies compose*.yaml, otelcol-config*.yml, or\n"
        "Grafana dashboards will likely require an update to the Demo Helm chart.",
        "A Pull Request that modifies compose*.yaml will likely require an update to\n"
        "the Demo Helm chart.",
        "Helm note about collector config and Grafana dashboards")


def strip_registry(ctx):
    """Push images only to the notel GHCR repository, never to Docker Hub."""
    rel = ".github/workflows/component-build-images.yml"
    lines = ctx.lines(rel)
    n = 0
    node = find_path(lines, ["on", "workflow_call", "inputs", "dockerhub_repo"])
    if node is not None:
        remove_node(lines, node)
        n = 1
    ctx.expect(rel, n, "removed dockerhub_repo input")
    default = find_path(lines, ["on", "workflow_call", "inputs", "ghcr_repo", "default"])
    if default is None:
        ctx.expect(rel, 0, "ghcr_repo default")
    else:
        new = f"{' ' * ind(lines[default])}default: '{NEW_IMAGE_NAME}'"
        if lines[default] != new:
            lines[default] = new
            ctx.expect(rel, 1, "set ghcr_repo default")
    removed = filter_children(
        lines, ["jobs", "build_and_push_images", "steps"],
        # The Docker Hub login step.
        lambda ls, c: bool(re.match(r"^\s*-\s*name:\s*Log in to Docker Hub\s*$", ls[c])))
    ctx.expect(rel, removed, "removed Docker Hub login step")
    # An image tag that targets the Docker Hub repository input.
    n = remove_lines(lines, re.compile(r"\$\{\{\s*inputs\.dockerhub_repo\s*\}\}"))
    ctx.expect(rel, n, "removed Docker Hub tags")

    docker_secrets = {"DOCKER_USERNAME", "DOCKER_PASSWORD"}
    for wf, paths in ((rel, [["on", "workflow_call", "secrets"]]),
                      (".github/workflows/checks.yml", None),
                      (".github/workflows/release.yml", None),
                      (".github/workflows/nightly-release.yml", None)):
        lines = ctx.lines(wf)
        if paths is None:
            jobs = find_path(lines, ["jobs"])
            names = [key_of(lines[c]) for c in children(lines, jobs)] if jobs is not None else []
            paths = [["jobs", j, "secrets"] for j in names]
        removed = []
        for path in paths:
            removed += filter_children(lines, path, lambda ls, c: key_of(ls[c]) in docker_secrets)
            remove_if_empty(lines, find_path(lines, path))
        ctx.expect(wf, removed, "removed Docker Hub secrets")
        if any(re.search(r"DOCKER_(USERNAME|PASSWORD)|dockerhub", x) for x in lines):
            ctx.errors.append(f"{wf}: Docker Hub reference remains")

    # The upstream image name in the Makefile clean-images filter.
    sub_lines(ctx, "Makefile", re.compile(r'reference="ghcr\.io/open-telemetry/demo:'),
              f'reference="{NEW_IMAGE_NAME}:', "clean-images filter uses notel image name")


# --------------------------------------------------------------------------
# Docs and misc
# --------------------------------------------------------------------------

def remove_md_section(ctx, rel, heading):
    lines = ctx.lines(rel)
    level = len(heading) - len(heading.lstrip("#"))
    try:
        i = lines.index(heading)
    except ValueError:
        ctx.expect(rel, 0, f"section '{heading}'")
        return
    fence = False
    e = len(lines)
    for j in range(i + 1, len(lines)):
        if lines[j].lstrip().startswith("```"):
            fence = not fence
        # A markdown heading of the same or a higher level.
        if not fence and re.match(rf"^#{{1,{level}}}\s", lines[j]):
            e = j
            break
    delete_range(lines, i, e, leading_comments=False)
    ctx.expect(rel, 1, f"removed section '{heading}'")


def strip_docs(ctx):
    remove_md_section(ctx, "AGENTS.md", "## Telemetry conventions")

    # The README badge for the deleted telemetry tests workflow.
    n = remove_lines(ctx.lines("README.md"), re.compile(r"^\[!\[Telemetry Tests\]\(.*run-telemetry-tests\.yml"))
    ctx.expect("README.md", n, "removed Telemetry Tests badge")

    rel = "CONTRIBUTING.md"
    replace_text(
        ctx, rel,
        "runtime. To use Podman instead, first set the `DOCKER_SOCK` to use podman,\n"
        "in `.env.override` uncomment `# DOCKER_SOCK=/run/user/1000/podman/podman.sock`\n"
        "This is needed for the otel-collector to work correctly. For example, you should\n"
        "have:\n"
        "\n"
        "```sh\n"
        "# Rootless podman: use the podman Docker-compatible API socket so the collector's\n"
        "# docker resource detector and docker_stats receiver can connect.\n"
        "DOCKER_SOCK=/run/user/1000/podman/podman.sock\n"
        "```\n"
        "\n"
        "Next you can run podman with:",
        "runtime. To use Podman instead, run:",
        "podman DOCKER_SOCK note")
    replace_text(ctx, rel, "### Verify the Webstore & Telemetry\n", "### Verify the Webstore\n",
                 "verify heading")
    # Verify-list bullets for UIs of deleted components.
    n = remove_lines(ctx.lines(rel), re.compile(r"^- \*\*(Jaeger|Grafana|OpAMP)\*\*: \[http://localhost:8080/"))
    ctx.expect(rel, n, "removed Jaeger/Grafana/OpAMP bullets")
    replace_text(
        ctx, rel,
        "\n\nThe OpAMP UI shows the OpenTelemetry Collector as a managed agent. Click the\n"
        "collector instance ID to view its health status, version, attributes, and\n"
        "effective configuration.\n",
        "\n", "OpAMP UI paragraph")
    replace_text(ctx, rel, "contracts, or collector/frontend-proxy configuration,",
                 "contracts, or frontend-proxy configuration,", "collector config mention")
    replace_text(
        ctx, rel,
        "direct service endpoints, container logs, Jaeger traces, Grafana dashboards, or\n"
        "other telemetry views as appropriate.",
        "direct service endpoints, or container logs as appropriate.",
        "verify via Jaeger/Grafana passage")
    replace_text(ctx, rel, "behavior, telemetry, configuration, or workflow changes.",
                 "behavior, configuration, or workflow changes.", "docs update telemetry mention")
    replace_text(ctx, rel, "For any user-visible behavior, telemetry, configuration, or workflow change:",
                 "For any user-visible behavior, configuration, or workflow change:",
                 "changelog telemetry mention")

    # The C++ OTel version build arg passed to the genproto image build.
    sub_lines(ctx, "docker-gen-proto.sh",
              re.compile(r"--build-arg OPENTELEMETRY_CPP_VERSION=\$\{OPENTELEMETRY_CPP_VERSION\} "), "",
              "removed OPENTELEMETRY_CPP_VERSION build arg")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def run(root, digest_mode, check_only):
    strict = any((root / p).exists() for p in DELETE_PATHS)
    ctx = Ctx(root, strict)
    try:
        for rel in COMPOSE_FILES:
            strip_compose(ctx, rel)
        strip_compose_extras_example(ctx)
        strip_dotenv(ctx, ".env", DOTENV_MUST_REMOVE)
        strip_dotenv(ctx, ".env.override", ["DOCKER_SOCK"])
        set_image_name(ctx)
        strip_makefile(ctx)
        strip_envoy(ctx)
        strip_frontend_proxy_dockerfile(ctx)
        strip_image_provider(ctx, digest_mode)
        strip_kafka(ctx)
        strip_postgres(ctx)
        strip_github(ctx)
        strip_registry(ctx)
        strip_docs(ctx)
    except StripError as e:
        ctx.errors.append(str(e))

    deletions = [p for p in DELETE_PATHS if (root / p).exists() or (root / p).is_symlink()]
    print(f"mode: {'fresh upstream tree (strict)' if strict else 'already stripped (idempotent)'}")
    for p in deletions:
        print(f"delete: {p}")
    for line in ctx.log:
        print(f"edit: {line}")
    if ctx.errors:
        print("\nERRORS (nothing was written):", file=sys.stderr)
        for e in ctx.errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    changed = ctx.changed()
    if check_only:
        print(f"\ncheck only: {len(deletions)} deletions and {len(changed)} file edits pending")
        return 1 if (deletions or changed) else 0

    for p in deletions:
        target = root / p
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
        parent = target.parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    for rel, text in changed.items():
        (root / rel).write_text(text, encoding="utf-8")
    print(f"\nwrote {len(changed)} files, deleted {len(deletions)} paths")

    hits = check_residuals.scan(root, [p for p in SCOPE_PATHS if (root / p).exists()])
    if hits:
        check_residuals.print_hits(hits)
        print(f"\nERROR: {len(hits)} unallowed observability residuals in scope", file=sys.stderr)
        return 1
    print("residual check: scope clean")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=SCRIPT_DIR.parent.parent,
                    help="repository root (default: the repo containing this script)")
    ap.add_argument("--nginx-digest", default="resolve",
                    help="digest for the plain nginx image: 'resolve' (docker buildx imagetools), "
                         "'none' (no pin), or an explicit sha256:... value")
    ap.add_argument("--check", action="store_true",
                    help="only report pending changes, exit 1 if any")
    args = ap.parse_args()
    sys.exit(run(args.root.resolve(), args.nginx_digest, args.check))


if __name__ == "__main__":
    main()
