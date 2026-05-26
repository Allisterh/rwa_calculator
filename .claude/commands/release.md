---
description: Run the release flow — preview the changelog promotion, run scripts/deploy.py, commit and tag. Optionally publish to PyPI.
---

You are running a release. The script `scripts/deploy.py` bumps versions, promotes
`[Unreleased]` changelog bullets into a new version section, regenerates the
citation matrix, syncs `uv.lock`, builds, commits, and tags. This command wraps
that flow with a preview + confirmation step so the operator can verify the
changelog promotion before it is committed.

## Step 1 — parse args

`$ARGUMENTS` may be:

- An explicit version: `0.2.15`
- A bump kind: `patch` / `minor` / `major`
- Empty: default to `patch` bump
- A trailing `--publish` flag (in any position): publish to PyPI after the commit

Resolve to a concrete `new_version` by reading the current version from
`pyproject.toml` (line containing `version = "..."`) and applying the bump if
needed. Confirm to the operator in one line: `Current: X.Y.Z → New: A.B.C`.

## Step 2 — preview the [Unreleased] promotion

Read `docs/appendix/changelog.md`. Extract the `[Unreleased]` block (everything
between `## [Unreleased]` and the next `---`).

Classify:

- **Empty / missing** — say so; warn that the new version section will be the
  hardcoded `Version bump for PyPI release` stub.
- **Placeholder-only** — every bullet is `- (Next release changes will go here)`;
  same warning as above.
- **Has real bullets** — count the bullets per subsection and list each
  subsection header + count, e.g.:
  ```
  Promoting from [Unreleased] into ## [0.2.15] - YYYY-MM-DD:
    ### Changed (1 bullet)
    ### Added   (5 bullets)
  ```
  Then quote the first ~80 chars of each real bullet so the operator can sanity-
  check what is moving.

## Step 3 — confirm

Print the resolved version, the publish flag, and the summary from step 2, then
**stop and wait** for the operator to confirm explicitly. Do NOT use
`AskUserQuestion` — just print the summary and a `Proceed? (yes/no)` prompt and
end the turn. The operator's next message is the go/no-go.

If the operator declines, stop. Do not mutate anything.

## Step 4 — run scripts/deploy.py

On `yes`, invoke the script via Bash:

```
uv run python scripts/deploy.py <new_version>          # without --publish
uv run python scripts/deploy.py <new_version> --publish # with --publish
```

Always pass the explicit version (not `--bump`) — resolution happened in step 1
and the operator confirmed it.

Stream the output. The script:

1. Runs tests (`uv run pytest -x -q`).
2. Updates version strings in pyproject, `__init__.py`, docs.
3. Promotes `[Unreleased]` via `scripts/_deploy_changelog.py` (this is the part
   that was broken before).
4. Regenerates `docs/development/citation-matrix.md`.
5. `uv sync`, `uv build`.
6. Stages release files, commits `chore(release): bump version to <ver>`, tags
   `v<ver>`.
7. If `--publish`: `uv publish`.

If any step fails, stop and surface the failure to the operator with the exact
script output. Do not retry automatically.

## Step 5 — report next steps

On success, print:

```
Release v<ver> committed and tagged locally.
To finish:
  git push origin master --tags
```

If `--publish` ran, also print the PyPI URL
(`https://pypi.org/project/rwa-calc/<ver>/`).

## Constraints

- One release per invocation. Do not chain.
- `--publish` requires explicit operator confirmation in step 3 even if it was on
  the slash-command args. PyPI uploads are irreversible.
- Never pass `--skip-tests` automatically. If tests fail, surface the failure;
  do not bypass.
- Never push tags to remote. The script does not, and neither do you. Pushing is
  the operator's final step.
- Never `git reset` or `git tag -d` to "recover" from a failed release. Stop and
  let the operator decide.
- If `[Unreleased]` is missing or placeholder-only, still proceed if the operator
  confirms — the script will fall back to the `Version bump for PyPI release`
  stub bullet.
