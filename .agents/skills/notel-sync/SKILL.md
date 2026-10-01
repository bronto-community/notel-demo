---
name: notel-sync
description: Regenerate the notel-demo fork (the OpenTelemetry Demo with all observability removed) on top of a new upstream commit. It applies the infra script, strips every service in parallel subagents, verifies the result, and rebuilds main. Use when the maintainer asks to sync, update or refresh notel-demo from upstream.
---

# Sync notel-demo with upstream

notel is regenerated on each sync, not merged. `main` is always laid out as
follows:

```
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
   - Commit with `notel: strip infra`.
5. **Services.** Fan out one subagent per language group, in parallel. Each
   subagent follows `.agents/skills/notel-strip-service/SKILL.md` for its
   services.

   Give each subagent its own git worktree, branched from the infra commit:
   `git worktree add ../notel-wt-<group> -b wt/<group>`. It commits its
   services there, and you cherry-pick the results onto the sync branch.
   Agents sharing one working tree have lost each other's edits through
   `git stash`, `reset` and `checkout`. No agent may run state-changing git
   commands outside its own worktree.

   Give each one:
   - Its services and the files it owns, so that no two agents edit the same
     file.
   - The upstream changes from step 3 that are relevant to it.
   - The rules: never commit or push, use `docker build` directly, and stop
     and ask on anything that isn't covered.

   Suggested groups:
   - Go: checkout, product-catalog.
   - JVM: ad, fraud-detection.
   - .NET: cart, accounting.
   - Node: frontend, payment.
   - react-native-app, flagd-ui, flagd.
   - Python: recommendation, load-generator, agent, chatbot, mcp.
   - Ruby, PHP, Rust: email, quote, shipping.
   - C++: currency.

   Once they finish, review each report and commit per service:
   `notel(<service>): strip observability`. Add any new breaking items to
   `notel/BREAKING.md`, but only after the maintainer has seen them.
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
