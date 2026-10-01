# notel scripts

Deterministic helpers for building the notel-demo fork from an upstream
OpenTelemetry Demo commit. They need Python 3 (stdlib only), git and Docker.

## strip_infra.py

Removes observability from the parts of the repository that are not service
code: compose files, `.env` files, the Makefile, CI configuration, docs, and
the infrastructure images `frontend-proxy`, `image-provider`, `kafka` and
`postgresql`. It also deletes the observability-only components (collector,
backends, OpAMP, telemetry docs, telemetry schema, telemetry tests and their
workflows).

```sh
python3 notel/scripts/strip_infra.py           # apply
python3 notel/scripts/strip_infra.py --check   # report pending changes only
```

- **Fresh upstream tree** (the deleted paths still exist): every edit must
  find its anchor. If any anchor is missing, the script lists all of them,
  writes nothing, and exits 1.
- **Already stripped tree**: every edit is a no-op, so the script is safe to
  re-run.
- Edits match on YAML keys, Makefile targets and line patterns, not on line
  numbers. They delete lines and keep the rest of each file as is.
- The plain nginx base image digest is resolved with
  `docker buildx imagetools inspect`. Use `--nginx-digest sha256:...` to pin
  a known digest, or `--nginx-digest none` to drop the pin.
- CI is adapted to bronto (`adapt_ci`): only `release.yml` pushes images,
  tagged from the `notel/<sha>` release tag, `nightly-release.yml` is
  deleted, and Scorecard and zizmor run as local jobs with the permissions an
  internal repository needs. The script fails if any other workflow pushes.
- When it finishes, it runs `check_residuals.py` on its own scope and exits 1
  if anything is left.

## check_residuals.py

Searches the repository (tracked and untracked files, excluding `notel/`,
`.agents/`, `.claude/`, `.git` and lockfiles) for observability terms. It also
checks file names. Every hit must be covered by an entry in
`residuals-allowlist.txt`, otherwise the script reports it and exits 1.

```sh
python3 notel/scripts/check_residuals.py                       # whole repo
python3 notel/scripts/check_residuals.py --paths src/frontend  # limit scope
python3 notel/scripts/check_residuals.py --summary             # counts per file
python3 notel/scripts/check_residuals.py --show-unused         # stale entries
```

## residuals-allowlist.txt

One entry per line: `<path glob> :: <regex> :: <reason>`. A hit is allowed
only if an entry for that path has a regex match that fully covers it. Keep
entries narrow, always give a reason, and mark open questions as `PENDING`.
