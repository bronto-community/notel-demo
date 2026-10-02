#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Report observability residuals that are not covered by the allowlist.

Scans every tracked and untracked (not ignored) file of the repository,
excluding notel/, .agents/, .claude/, .git and lockfiles. Every match of the
residual pattern must be fully covered by an allowlist entry that applies to
the file, otherwise it is reported and the exit code is 1.
"""

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ALLOWLIST = SCRIPT_DIR / "residuals-allowlist.txt"

# Any observability term the fork must not contain (case-insensitive).
RESIDUAL_RE = re.compile(
    r"opentelemetry|otel|OTEL_|jaeger|prometheus|grafana|opensearch|opamp|traceloop"
    r"|openllmetry|telemetry", re.IGNORECASE)

EXCLUDED_PREFIXES = ("notel/", ".agents/", ".claude/", ".git/")
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "go.sum", "Cargo.lock",
    "composer.lock", "Gemfile.lock", "mix.lock", "poetry.lock", "uv.lock",
    "Pipfile.lock", "packages.lock.json", "Podfile.lock", "gradle.lockfile",
}


def load_allowlist(path=ALLOWLIST):
    entries = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(" :: ")]
        if len(parts) != 3 or not all(parts):
            raise SystemExit(f"{path.name}:{n}: expected '<glob> :: <regex> :: <reason>'")
        glob, regex, reason = parts
        try:
            rx = re.compile(regex)
        except re.error as e:
            raise SystemExit(f"{path.name}:{n}: bad regex: {e}")
        entries.append({"line": n, "glob": glob, "rx": rx, "reason": reason, "used": False})
    return entries


def list_files(root):
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, check=True, capture_output=True).stdout.decode()
    files = []
    for rel in sorted(set(filter(None, out.split("\0")))):
        p = root / rel
        if rel.startswith(EXCLUDED_PREFIXES) or Path(rel).name in LOCKFILES:
            continue
        if p.is_file() and not p.is_symlink():
            files.append(rel)
    return files


def in_scope(rel, paths):
    if not paths:
        return True
    for p in paths:
        p = p.strip("/")
        if p in ("", ".") or rel == p or rel.startswith(p + "/"):
            return True
    return False


def unallowed_spans(text, entries):
    allowed = []
    for e in entries:
        for m in e["rx"].finditer(text):
            if m.end() > m.start():
                allowed.append((m.start(), m.end(), e))
    bad = []
    for m in RESIDUAL_RE.finditer(text):
        cover = [a for a in allowed if a[0] <= m.start() and m.end() <= a[1]]
        if cover:
            for a in cover:
                a[2]["used"] = True
        else:
            bad.append(m.group(0))
    return bad


def scan(root, paths=None, entries=None):
    root = Path(root)
    entries = load_allowlist() if entries is None else entries
    hits = []
    for rel in list_files(root):
        if not in_scope(rel, paths):
            continue
        applicable = [e for e in entries if fnmatch.fnmatchcase(rel, e["glob"])]
        if unallowed_spans(rel, applicable):
            hits.append((rel, 0, f"(path) {rel}"))
        data = (root / rel).read_bytes()
        if b"\0" in data[:8192]:
            continue
        for n, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if RESIDUAL_RE.search(line) and unallowed_spans(line, applicable):
                hits.append((rel, n, line.strip()))
    return hits


def print_hits(hits, summary=False):
    if summary:
        counts = {}
        for rel, _, _ in hits:
            counts[rel] = counts.get(rel, 0) + 1
        for rel, c in sorted(counts.items()):
            print(f"{c:6d}  {rel}")
        return
    for rel, n, text in hits:
        print(f"{rel}:{n}: {text[:200]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=SCRIPT_DIR.parent.parent)
    ap.add_argument("--paths", nargs="+", help="limit the scan to these files or directories")
    ap.add_argument("--summary", action="store_true", help="print hit counts per file only")
    ap.add_argument("--show-unused", action="store_true",
                    help="list allowlist entries that matched nothing in the scanned scope")
    args = ap.parse_args()
    entries = load_allowlist()
    hits = scan(args.root.resolve(), args.paths, entries)
    print_hits(hits, args.summary)
    if args.show_unused:
        for e in entries:
            if not e["used"]:
                print(f"unused allowlist entry (line {e['line']}): {e['glob']} :: {e['rx'].pattern}")
    if hits:
        print(f"\n{len(hits)} unallowed residual hits in {len({h[0] for h in hits})} files",
                file=sys.stderr)
        sys.exit(1)
    print("no unallowed residuals")


if __name__ == "__main__":
    main()
