#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate notel/k8s/values.yaml for the upstream opentelemetry-demo Helm chart.

The chart version is pinned in notel/k8s/chart-version. The script reads that
chart's values.yaml and writes an override that disables every observability
sub-chart and component, strips OTel env, annotations, ports and config from
the remaining components, points them at the notel images, and inlines
notel's flagd flags, PostgreSQL init script and agent cassettes.

It fails loudly when the chart has something it does not know: a new
component, dependency, template or top-level key, or anything that still
looks like observability after stripping. See notel/k8s/README.md.

Needs PyYAML. Without it, run it in Docker:

    docker run --rm -v "$PWD":/w -w /w python:3.13-alpine \\
        sh -c 'pip install -q pyyaml && python3 notel/scripts/gen_helm_values.py'
"""
from __future__ import annotations

import argparse
import copy
import io
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(__doc__.split("Needs PyYAML.", 1)[1].strip())

ROOT = Path(__file__).resolve().parents[2]
K8S = ROOT / "notel" / "k8s"
PIN_FILE = K8S / "chart-version"
OUTPUT = K8S / "values.yaml"
CHART = "opentelemetry-demo"
CHART_URL = ("https://github.com/open-telemetry/opentelemetry-helm-charts/releases/"
            "download/{chart}-{version}/{chart}-{version}.tgz")

# Chart components notel deploys, and the ones it removed.
KEEP = {
    "accounting", "ad", "agent", "cart", "chatbot", "checkout", "currency",
    "email", "fraud-detection", "frontend", "frontend-proxy", "image-provider",
    "load-generator", "mcp", "payment", "product-catalog", "quote",
    "recommendation", "shipping", "flagd", "kafka", "astronomy-db", "valkey-cart",
}
DISABLE = {"telemetry-docs", "opamp-server", "firepit"}
# Third-party components whose image comes from .env, as in compose.
THIRD_PARTY_IMAGES = {"flagd": "FLAGD_IMAGE", "astronomy-db": "POSTGRES_IMAGE",
                        "valkey-cart": "VALKEY_IMAGE"}
# Compose services that the chart runs as a sidecar instead of a component.
SIDECARS = {"flagd-ui": "flagd"}
COMPOSE_FILES = ["compose.yaml", "compose.full.yaml", "compose.agent.yaml"]

# Templates the chart ships. A new one may render a ConfigMap from chart
# files that notel has not reviewed.
KNOWN_TEMPLATES = {
    "NOTES.txt", "_helpers.tpl", "_objects.tpl", "_pod.tpl",
    "agent-fixtures-config.yaml", "component.yaml", "flagd-config.yaml",
    "grafana-config.yaml", "posgresql-init-config.yaml", "serviceaccount.yaml",
}
# ConfigMaps rendered from chart files that notel replaces. The post-renderer
# (notel/k8s/post-render/post-render.sh) deletes exactly these.
REPLACED_CONFIGMAPS = {"flagd-config", "postgresql-init", "agent-fixtures"}

# Env vars stripped by name: anything OTel, or pointing at a removed component.
STRIP_ENV = re.compile(r"OTEL|TRACELOOP|OPAMP|GRAFANA|JAEGER|PROMETHEUS|TELEMETRY_DOCS|FIREPIT")
# Pod annotations for the collector's resource detection and receiver discovery
# (resource.opentelemetry.io/*, io.opentelemetry.discovery.*).
STRIP_ANNOTATION = re.compile(r"opentelemetry")
# Container ports that only exist for metrics scraping.
STRIP_PORT = re.compile(r"prometheus|metrics")
# Anything left after stripping that still looks like observability. "otel"
# not preceded by "n", so that the notel image name does not match.
SUSPICIOUS = re.compile(
    r"(?<!n)otel|opentelemetry|traceloop|opamp|jaeger|prometheus|grafana|opensearch|"
    r"zipkin|tempo|pyroscope|collector|telemetry|langsmith|4317|4318|9464|"
    r"pg_stat_statements|monitoring_user", re.IGNORECASE)


class GenError(Exception):
    pass


def read_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.split(" #", 1)[0].strip()
    return env


def load_chart(source: str | None, version: str) -> tuple[dict, dict, set[str]]:
    if source and Path(source).is_dir():
        base = Path(source)
        files = {p.relative_to(base).as_posix(): p.read_bytes()
                for p in base.rglob("*") if p.is_file() and "charts/" not in p.as_posix()}
    else:
        if source:
            data = Path(source).read_bytes()
        else:
            url = CHART_URL.format(chart=CHART, version=version)
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
        files = {}
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                parts = member.name.split("/", 1)
                if member.isfile() and len(parts) == 2 and not parts[1].startswith("charts/"):
                    files[parts[1]] = tar.extractfile(member).read()
    chart = yaml.safe_load(files["Chart.yaml"])
    values = yaml.safe_load(files["values.yaml"])
    templates = {name.split("/", 1)[1] for name in files if name.startswith("templates/")}
    return chart, values, templates


def strip_env(entries: list | None) -> list:
    return [e for e in entries or []
            if not STRIP_ENV.search(e["name"]) and "$(OTEL_" not in str(e.get("value", ""))]


def strip_container(name: str, cfg: dict) -> dict:
    """Override for one component or sidecar: env, annotations, ports."""
    out: dict = {"useDefault": {"env": False}}
    for key in ("env", "envOverrides"):
        if key in cfg:
            out[key] = strip_env(cfg[key])
    annotations = {k: None for k in cfg.get("podAnnotations") or {} if STRIP_ANNOTATION.search(k)}
    if annotations:
        out["podAnnotations"] = annotations
    if "ports" in cfg:
        ports = [p for p in cfg["ports"] if not STRIP_PORT.search(p["name"])]
        if ports != cfg["ports"]:
            out["ports"] = ports
    return out


def literal(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def special_cases(name: str, cfg: dict, out: dict, env: dict) -> None:
    """Component-specific edits. Each asserts the chart shape it expects."""
    def expect(cond: bool, what: str) -> None:
        if not cond:
            raise GenError(f"components.{name}: chart changed, expected {what}")

    if name in THIRD_PARTY_IMAGES:
        image = env[THIRD_PARTY_IMAGES[name]]
        repo, tag = image.rsplit(":", 1)
        out["imageOverride"] = {"repository": repo, "tag": tag}

    if name == "product-catalog":
        mounts = cfg.get("mountedConfigMaps") or []
        expect([m["name"] for m in mounts] == ["product-catalog-otel-config"],
                "only the OTel SDK config ConfigMap in mountedConfigMaps")
        out["mountedConfigMaps"] = []

    if name == "astronomy-db":
        cmd = cfg.get("command") or []
        expect(cmd[-2:] == ["-c", "shared_preload_libraries=pg_stat_statements"],
                "command ending in -c shared_preload_libraries=pg_stat_statements")
        out["command"] = cmd[:-2]
        mounts = cfg.get("mountedConfigMaps") or []
        expect([m.get("existingConfigMap") for m in mounts] == ["postgresql-init"],
                "mountedConfigMaps using existingConfigMap postgresql-init")
        out["mountedConfigMaps"] = [{
            "name": "init", "mountPath": mounts[0]["mountPath"],
            "data": {"init.sql": literal((ROOT / "src/postgresql/init.sql").read_text(encoding="utf-8"))},
        }]

    if name == "flagd":
        expect(cfg.get("additionalVolumes") == [{"name": "config-ro", "configMap": {"name": "flagd-config"}}],
                "additionalVolumes [config-ro -> ConfigMap flagd-config]")
        init = cfg.get("initContainers") or []
        expect(len(init) == 1 and {"name": "config-ro", "mountPath": "/config-ro"} in init[0]["volumeMounts"],
                "one initContainer mounting config-ro at /config-ro")
        out["additionalVolumes"] = []
        out["mountedConfigMaps"] = [{
            "name": "config-ro", "mountPath": "/config-ro",
            "data": {"demo.flagd.json": literal((ROOT / "src/flagd/demo.flagd.json").read_text(encoding="utf-8"))},
        }]
        sidecars = []
        for sidecar in cfg.get("sidecarContainers") or []:
            s = copy.deepcopy(sidecar)
            s.update(strip_container(s["name"], s))
            s.pop("podAnnotations", None)
            sidecars.append(s)
        out["sidecarContainers"] = sidecars

    if name == "agent":
        expect(cfg.get("additionalVolumes") == [{"name": "agent-fixtures", "configMap": {"name": "agent-fixtures"}}],
                "additionalVolumes [agent-fixtures -> ConfigMap agent-fixtures]")
        mounts = cfg.get("additionalVolumeMounts") or []
        expect([m["name"] for m in mounts] == ["agent-fixtures"], "additionalVolumeMounts [agent-fixtures]")
        cassettes = sorted((ROOT / "src/agent/fixtures/vcr_cassettes").glob("*.yaml"))
        expect(bool(cassettes), "cassettes under src/agent/fixtures/vcr_cassettes")
        out["additionalVolumes"] = []
        out["additionalVolumeMounts"] = []
        out["mountedConfigMaps"] = [{
            "name": "cassettes", "mountPath": mounts[0]["mountPath"],
            "data": {p.name: literal(p.read_text(encoding="utf-8")) for p in cassettes},
        }]

    for mount in out.get("mountedConfigMaps") or []:
        expect(f"{name}-{mount['name']}" not in REPLACED_CONFIGMAPS,
                f"a ConfigMap name the post-renderer does not delete, got {name}-{mount['name']}")


def merge(base, override):
    """Helm-style merge: maps merge, null deletes, everything else replaces."""
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            if value is None:
                result.pop(key, None)
            else:
                result[key] = merge(base.get(key), value)
        return result
    return copy.deepcopy(override)


def scan(path: str, value, errors: list[str]) -> None:
    """Report every key or string that still looks like observability."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "data" and path.endswith("]"):
                continue  # file contents from notel src/, covered by check_residuals.py
            if SUSPICIOUS.search(str(key)):
                errors.append(f"{path}.{key}")
            scan(f"{path}.{key}", child, errors)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            scan(f"{path}[{i}]", child, errors)
    elif isinstance(value, str) and SUSPICIOUS.search(value):
        errors.append(f"{path} = {value!r}")


def compose_services(env: dict) -> set[str]:
    image_name = env["IMAGE_NAME"]
    names = set()
    for file in COMPOSE_FILES:
        services = (yaml.safe_load((ROOT / file).read_text()) or {}).get("services") or {}
        for svc, cfg in services.items():
            image = str((cfg or {}).get("image", ""))
            if image.startswith("${IMAGE_NAME}") or image.startswith(image_name) or image.startswith("${"):
                names.add(svc)
    return names


def generate(chart: dict, values: dict, templates: set[str], env: dict, tag: str,
            version: str) -> str:
    errors: list[str] = []
    if chart.get("version") != version:
        errors.append(f"chart version {chart.get('version')} does not match pin {version}")
    if templates != KNOWN_TEMPLATES:
        errors.append(f"chart templates changed: new {sorted(templates - KNOWN_TEMPLATES)}, "
                        f"gone {sorted(KNOWN_TEMPLATES - templates)}")

    deps = {}
    for dep in chart.get("dependencies") or []:
        cond = dep.get("condition", "")
        if not cond.endswith(".enabled"):
            errors.append(f"dependency {dep['name']} has no <key>.enabled condition")
            continue
        deps[cond[: -len(".enabled")]] = {"enabled": False}
    unknown_top = set(values) - {"default", "serviceAccount", "components"} - set(deps)
    if unknown_top:
        errors.append(f"unknown top-level values keys: {sorted(unknown_top)}")

    components = values["components"]
    unknown = set(components) - KEEP - DISABLE
    if unknown:
        errors.append(f"unknown chart components (add to KEEP or DISABLE): {sorted(unknown)}")
    missing = (compose_services(env) - set(components) - set(SIDECARS)) | (KEEP - set(components))
    if missing:
        errors.append(f"notel services missing from the chart: {sorted(missing)}")
    if errors:
        raise GenError("\n".join(errors))

    overrides: dict = {}
    for name in sorted(components):
        cfg = components[name]
        if name in DISABLE:
            overrides[name] = {"enabled": False}
            continue
        out = strip_container(name, cfg)
        special_cases(name, cfg, out, env)
        overrides[name] = out

    default = {"env": [], "envOverrides": [],
                "image": {"repository": env["IMAGE_NAME"], "tag": tag}}
    result = {"default": default, "components": overrides, **dict(sorted(deps.items()))}

    effective_default = merge(values["default"], default)
    scan("default", effective_default, errors)
    for name in sorted(KEEP):
        scan(f"components.{name}", merge(components[name], overrides[name]), errors)
    if errors:
        raise GenError("left after stripping (extend the strip rules or ask the maintainer):\n  "
                        + "\n  ".join(errors))

    header = ("# SPDX-License-Identifier: Apache-2.0\n"
                f"# Generated by notel/scripts/gen_helm_values.py for the {CHART} chart "
                f"{version} (appVersion {chart.get('appVersion')}). Do not edit.\n"
                "# See notel/k8s/README.md.\n"
                "# Embedded cassette JSON and SQL cannot be wrapped.\n"
                "# yamllint disable rule:line-length\n")
    return header + yaml.dump(result, Dumper=Dumper, sort_keys=False, width=1000, allow_unicode=True)


class Dumper(yaml.SafeDumper):
    pass


def _str(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


Dumper.add_representer(str, _str)
Dumper.ignore_aliases = lambda self, data: True


def main() -> int:
    env = read_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tag", default=env.get("DEMO_VERSION", "latest"),
                        help="image tag prefix; images are <IMAGE_NAME>:<tag>-<service> "
                            "(default: DEMO_VERSION from .env)")
    parser.add_argument("--chart", help="local chart .tgz or directory instead of downloading the pin")
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--check", action="store_true", help="exit 1 if the output file is not up to date")
    parser.add_argument("--allow-app-version-mismatch", action="store_true",
                        help="accept a chart whose appVersion differs from IMAGE_VERSION in .env; "
                            "only with the maintainer's explicit agreement, noted in notel/verify/LAST_RUN.md")
    args = parser.parse_args()

    version = PIN_FILE.read_text().strip()
    try:
        chart, values, templates = load_chart(args.chart, version)
        if chart.get("appVersion") != env.get("IMAGE_VERSION") and not args.allow_app_version_mismatch:
            raise GenError(
                f"chart {version} is for demo {chart.get('appVersion')}, but .env has "
                f"IMAGE_VERSION={env.get('IMAGE_VERSION')}.\n"
                f"Pin a chart release whose appVersion matches in {PIN_FILE.relative_to(ROOT)}.\n"
                "If no such release exists, --allow-app-version-mismatch overrides this check. "
                "Use it only after the maintainer has explicitly agreed, and record its use "
                "in notel/verify/LAST_RUN.md.")
        text = generate(chart, values, templates, env, args.tag, version)
    except GenError as err:
        print(f"gen_helm_values: {err}", file=sys.stderr)
        return 1

    out = Path(args.output)
    if args.check:
        if not out.is_file() or out.read_text(encoding="utf-8") != text:
            print(f"{out} is out of date; run notel/scripts/gen_helm_values.py", file=sys.stderr)
            return 1
        return 0
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} (chart {version}, images {env['IMAGE_NAME']}:{args.tag}-<service>)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
