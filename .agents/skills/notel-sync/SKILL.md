---
name: notel-sync
description: Regenerate the notel-demo fork (the OpenTelemetry Demo with all observability removed) on top of a new upstream commit. It applies the infra script, strips every service in parallel subagents, verifies the result, and rebuilds main. Use when the maintainer asks to sync, update or refresh notel-demo from upstream.
---

# Sync notel-demo with upstream

notel is regenerated on each sync, not merged. `main` is always laid out as
follows:

```text
<upstream commit>
  └ notel: tooling                         (notel/, .agents/, .claude symlink, AGENTS.md section)
    └ notel: delete observability components
    └ notel: strip infra                   (output of notel/scripts/strip_infra.py)
    └ notel(<service>): strip observability   (one commit per service)
    └ notel: verification record
```

Read `notel/DECISIONS.md` first; it is binding. Ask the maintainer before
making any decision it doesn't cover. Never push unless the maintainer
explicitly asks for it. The remote is `bronto-community/notel-demo`, never
upstream.

## Steps

1. **Prepare.**
   - Record the current values: `PREV_TAG` is the latest `notel/*` tag and
     `PREV_BASE` is its upstream base (`git merge-base PREV_TAG upstream/main`,
     or the sha in the tag name).
   - Run `git fetch upstream` and pick `NEW_BASE` (default `upstream/main`;
     the maintainer may name a release tag).
   - Run `git switch -c sync/<NEW_BASE-short> NEW_BASE`.
2. **Carry the tooling.** Run
   `git checkout PREV_TAG -- notel .agents .claude`, re-apply the notel
   section to `AGENTS.md`, and commit with the message `notel: tooling`.
   Upstream's `.gitignore` ignores `.claude/`, so add the symlink with
   `git add -f .claude/skills`.
3. **Triage what changed upstream.** Do this before touching code.
   - `git diff --stat PREV_BASE NEW_BASE`
   - `git diff PREV_BASE NEW_BASE -- src | grep -iE '^\+.*(otel|opentelemetry|tracer|meter|span|baggage|prometheus|traceloop|opamp)'`
   - List the new directories under `src/` that have no
     `references/services/<svc>.md`. A new service needs a full inventory.
   - List the new compose services, env vars, flags and dependencies.
   - Summarize the result for the maintainer. If upstream introduced a new
     kind of coupling (business logic depending on telemetry), stop and ask
     before continuing.
4. **Infra.**
   - `git rm` the observability-only components listed in
     `notel/scripts/README.md`, and commit them separately.
   - Run `python3 notel/scripts/strip_infra.py`. The script fails loudly
     when an anchor has drifted. If it does, fix the script, not the output
     by hand, so that the next sync benefits. Re-run it until it passes.
   - Kubernetes values. Compare `notel/k8s/chart-version` with the
     upstream chart. Pick the newest `opentelemetry-demo` chart release whose
     `appVersion` matches `IMAGE_VERSION` in `.env`. Update the pin if needed,
     then run
     `docker run --rm -v "$PWD":/w -w /w python:3.13-alpine sh -c 'pip install -q pyyaml && python3 notel/scripts/gen_helm_values.py'`.
     The script fails if the appVersion doesn't match, or if the chart has
     a new component, dependency, template or OTel-looking key. Use
     `--allow-app-version-mismatch` only after the maintainer has explicitly
     agreed to it, and note its use in `notel/verify/LAST_RUN.md`. If it
     fails, extend the script, not `values.yaml`. Ask the maintainer
     whether a new component is kept or disabled. Then run
     `notel/k8s/check_render.sh`.
   - Commit with `notel: strip infra`.
5. **Services.** Split the services by whether upstream touched them since
   `PREV_BASE`:

   ```sh
   git diff --name-only PREV_BASE NEW_BASE -- src/<service>
   ```

   - **Unchanged services:** cherry-pick their previous strip commit from
     `main` (`git log main --grep '^notel(<service>): strip observability$'`)
     with `git cherry-pick -x`. They must apply cleanly and pass
     `check_residuals.py --paths src/<service>`. A conflict moves the service
     to the next group.
   - **Changed services:** re-strip them with subagents, one per language
     group, in parallel. Each subagent follows
     `.agents/skills/notel-strip-service/SKILL.md`, starts from a cherry-pick
     of the previous strip commit, and resolves it against upstream's new
     files.
   - **Lockfiles:** for lockfile changes (the common case), the rule is to
     take upstream's new lockfile as the base and remove only OTel and the
     transitive dependencies nothing needs any more. Every package that
     remains keeps upstream's version, since upstream bumps often carry
     security fixes. The subagent must show a version diff against
     upstream's lockfile, and a clean cherry-pick is not proof of a
     consistent lockfile.
   - **Full re-strip:** use it as the fallback, for example for new services
     or large upstream refactors. Every service then goes to a subagent.

   Give each subagent its own git worktree, branched from the sync branch
   after the cherry-picks:
   `git worktree add <dir> -b wt/sync-<group> <sync-head>`. It commits its
   services there, and you cherry-pick the results onto the sync branch.
   Agents sharing one working tree have lost each other's edits through
   `git stash`, `reset` and `checkout`. No agent may run state-changing git
   commands outside its own worktree.

   Give each one:
   - Its services, the previous strip commit shas, and the files it owns.
   - The upstream changes from step 3 that are relevant to it.
   - The rules: commit only in its worktree, never push, use `docker build`
     directly, and stop and ask on anything that isn't covered.

   Suggested groups:
   - Go: checkout, product-catalog.
   - JVM: ad, fraud-detection.
   - .NET: cart, accounting.
   - Node: frontend, payment, react-native-app.
   - Python: recommendation, load-generator, agent, chatbot, mcp.
   - Ruby, PHP, Rust, Elixir: email, quote, shipping, flagd-ui.
   - C++: currency.
   - flagd: flag definitions only, usually a cherry-pick.

   Review each report. Add any new breaking items to `notel/BREAKING.md`,
   but only after the maintainer has seen them.
6. **Verify.** Follow `.agents/skills/notel-verify/SKILL.md` end to end. A
   failure sends you back to the relevant service. Commit
   `notel/verify/LAST_RUN.md` with the message `notel: verification record`.
7. **Publish locally.**
   - Run `git tag notel/<NEW_BASE-short>`.
   - Show the maintainer the summary: upstream range, per-service changes,
     new breaking items, new dormant cases, and the verification result.
   - Only after approval, reset main to the sync branch:
     `git branch -f main sync/<...>`. Pushing (force for main, plus the tag)
     happens only when the maintainer says so.

## Practical notes

- Commits may be signed through an SSH agent that asks for approval, such as
  Secretive with Touch ID. Rebuilding history re-signs every commit, so tell
  the maintainer to expect approval prompts. A git command that seems to
  hang is usually waiting on one.
- Run multi-arg compose invocations from bash scripts with arrays. zsh does
  not word-split `$VAR`.
- If host port 8080 is taken, export `ENVOY_PORT` for the verification run
  instead of editing files.

## Commit messages

Use an `Assisted-by: <tool and model>` trailer for AI-generated changes.
Never use `Co-authored-by` for AI; it breaks the EasyCLA check.
