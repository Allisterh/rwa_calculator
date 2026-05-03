---
description: Pick top N non-conflicting items from IMPLEMENTATION_PLAN.md, run the four-stage agent pipeline as parallel waves in per-item git worktrees, then squash-merge each item back into the current branch under a single global validation gate. Default N=3, capped at 5. Hard-excludes items that touch shared engine files.
argument-hint: [N]
---

You are draining `IMPLEMENTATION_PLAN.md` in batches. Each item in
the batch runs in its **own git worktree**, on its own
`batch/<batch-id>/<P-code>` branch. After all four waves finish, you
squash-merge each worktree branch back into the **current branch**
(the operator pre-creates a feature branch before invoking this
command), run the global validation gate **once** on the merged tree,
then tick the plan and clean up the worktrees.

Parse `$ARGUMENTS` as integer **N** (default 3, cap 5). If
`$ARGUMENTS` is empty or not an integer, use 3.

This command is more delicate than `/next-docs` because the validation
gate is global. Worktree isolation removes the silent-overwrite class
of bugs the old "collision rules" tried to prevent — collisions now
surface as merge conflicts you can triage per-item.

## Step 1 — pick a batch

Read `IMPLEMENTATION_PLAN.md`. Walk tiers in order:

1. Tier 1: Calculation Correctness
2. Tier 2: Test Coverage Gaps
3. Tier 3: COREP Reporting Completeness
4. Tier 4: Pillar III Disclosure Gaps
5. (skip Tier 5: Documentation — that's `/next-docs` territory)
6. Tier 6: Code Quality
7. (skip Tier 7: Future / v2.0)

For each candidate item, infer its expected change footprint by
reading the bullet's `Ref:` field, the cited file paths, and the
named test.

**Soft preferences** (try to satisfy, but a violation is no longer a
disqualifier — the worktree merge surfaces conflicts cleanly):

1. Distinct top-level under `src/rwa_calc/engine/` (e.g. `engine/sa/`,
   `engine/irb/`, `engine/crm/`, `engine/slotting/`, `engine/equity/`,
   `engine/re_splitter.py`, `engine/hierarchy.py`,
   `engine/classifier.py`).
2. Distinct file in `src/rwa_calc/data/tables/`.
3. Distinct new test path under `tests/`.

If two candidates clearly target the same shared helper or the same
data-table row, prefer to defer one to the next batch — that avoids
a known-bad merge before you start.

**Hard exclusions** — any candidate that requires changes to:

- `src/rwa_calc/engine/pipeline.py`
- `src/rwa_calc/contracts/protocols.py`
- `src/rwa_calc/contracts/bundles.py`
- `src/rwa_calc/engine/aggregator/aggregator.py`

is forced single-stream. Pick it alone, even if N>1 was requested,
report the downgrade ("Picked P-code only; touches pipeline.py —
single-stream, no worktree"), and run it in the **main tree** as the
old flow did. The worktree machinery is only worth it when N>1.

If the queue is empty, report "nothing to do" and stop.

Generate a short batch identifier `<batch-id>` (e.g. timestamp
`YYYYMMDD-HHMM`) — used for branch names and commit footers.

## Step 2 — confirm before dispatch

Capture the **current branch** (`git branch --show-current`) — this
is the merge target. If it is `master`, warn the operator: squash
commits will land on master unless they abort and check out a feature
branch.

State to the operator, one line per item:
`<P-code> | Tier <n> | engine: <subpkg> | table: <file or none> | test: <path> | branch: batch/<batch-id>/<P-code> | worktree: ../rwa_calculator-<P-code>`

If any candidate was downgraded to single-stream, say so and skip
Step 3 (no worktree).

## Step 3 — provision worktrees

Skip this step entirely for single-stream / hard-excluded items.

For each batched item, run from the main repo:

```
git worktree add -b batch/<batch-id>/<P-code> ../rwa_calculator-<P-code> HEAD
```

This creates one branch + one tree per item, all rooted at the
current HEAD of the merge-target branch. Capture each worktree's
absolute path — agents will need it.

Sanity check after all worktrees are created:

```
git worktree list
```

Expect the main tree plus N sibling entries.

## Step 4 — four parallel waves

Run the agent pipeline as **four sequential waves**, each wave
parallel across the N items.

Every agent prompt (Waves 2–4) must include this preamble verbatim,
with `<absolute worktree path>` and `<absolute main .venv path>`
substituted:

> Operate inside the worktree at `<absolute worktree path>` for this
> task. Use absolute paths beginning with that prefix in all Read /
> Edit / Write / Bash calls. Do **not** edit files in the main repo
> tree. The repo's main virtual environment is shared via
> `UV_PROJECT_ENVIRONMENT=<absolute main .venv path>` — prepend it
> to any `uv run` command, e.g.
> `UV_PROJECT_ENVIRONMENT=<...> uv run pytest <...>`.

Wave 1 (`scenario-architect`) is read-only and does **not** receive
this preamble — let it operate in the main tree, since it produces
no edits.

### Wave 1 — scenario-architect (parallel)

In a single message, dispatch N `scenario-architect` calls, one per
item. Each gets the item's bullet verbatim:

> Design the work needed for **<P-CODE>**. Read the bullet from
> `IMPLEMENTATION_PLAN.md` below and the cited spec.
> Produce the structured proposal per your system prompt.
>
> --- plan item ---
> {{exact bullet text}}

Wait for all N proposals.

### Wave 2 — fixture-builder (parallel, may include skips)

For each item whose proposal calls for new fixtures, dispatch
`fixture-builder` with that item's proposal **plus the worktree
preamble**. Items needing no fixture changes are skipped (pass an
empty fixture report into Wave 3 for those).

Run all needed fixture-builder calls in one parallel message. Wait
for all to return.

### Wave 3 — test-writer (parallel)

In one parallel message, dispatch N `test-writer` calls. Each gets
its item's proposal + its fixture report (or "no new fixtures") +
the worktree preamble. Each writer must leave its test failing for
the right reason — verified inside its worktree — before returning.

### Wave 4 — engine-implementer (parallel)

In one parallel message, dispatch N `engine-implementer` calls. Each
gets its item's proposal + the failing-test report + the worktree
preamble.

Append to each engine-implementer prompt:

> Run only this item's targeted pytest target inside the worktree —
> **not** the global validation gate. The orchestrator runs the
> global gate once on the merged feature branch after Wave 4. Do
> not run `ruff check src/`, `ty src/`, or `pytest tests/contracts/`
> here — those are deferred. The targeted test you must verify
> green is the path your test-writer reported.

Per-worktree, the implementer should still run its scoped
`arch_check.py` so an obvious architectural breach is caught before
merge.

## Step 5 — squash-merge into the current branch

Single-stream / hard-excluded items: this step is replaced by the
old in-place commit sequence (`git add` the engine-implementer's
files, commit with `feat(<P-code>): <summary> [batch <batch-id>]`).
Skip to Step 6.

For multi-item batches, in **tier-priority order**:

```
git checkout <merge-target-branch>
git merge --squash batch/<batch-id>/<P-code>
git commit -m "feat(<P-code>): <one-line summary> [batch <batch-id>]"
```

The pre-commit gate (`scripts/pre_commit_gate.sh`) fires on each
commit and runs `arch_check.py` + `ruff check src/`. Substantive
gating happens once at Step 6.

### Conflict policy

If `git merge --squash` reports a conflict for item X:

1. `git merge --abort` (resets the index but leaves the worktree
   branch intact).
2. Mark item X as **dropped** from this batch. Surface to the
   operator: "Dropped <P-code>: merge conflict in <files>". Do not
   tick it in `IMPLEMENTATION_PLAN.md`. The branch and worktree are
   torn down with the others in Step 8 — the work is not lost
   because the failing item is regenerated cleanly in a future
   batch.
3. Continue with the remaining items. Do **not** abort the rest of
   the batch.

Drop also applies if a per-commit hook fails for item X (e.g.
arch_check spots a violation introduced by the merge resolution).

## Step 6 — single global validation gate

Run once, on the merged tree, in this order:

```
uv run python scripts/arch_check.py
uv run ruff check src/ && uv run ruff format --check src/
uv run ty src/
uv run pytest tests/contracts/ --benchmark-skip -q
uv run pytest <union of all merged items' new test paths> -x --benchmark-skip
```

The "merged items" set excludes anything dropped in Step 5.

If anything fails, surface:
- the gate command that failed,
- the failing test names or arch_check messages,
- a best-effort attribution to the merged item (match failing file
  paths to the engine sub-package each item targeted in Step 1).

**Do not tick the plan if the gate is red.** The squash commits are
already on the feature branch — the operator decides whether to
revert specific commits, fix forward, or push as-is for review.

## Step 7 — tick the plan

For each item that successfully merged **and** survived the global
gate, edit `IMPLEMENTATION_PLAN.md` at the top level: toggle from
`[ ]` to `[x] FIXED v<x.y.z>` with a one-line summary. One Edit per
item, then a single commit:

```
chore(plan): tick N code items [batch <batch-id>]
```

## Step 8 — cleanup and push

For every item — including dropped ones — tear down the worktree and
its branch:

```
git worktree remove --force ../rwa_calculator-<P-code>
git branch -D batch/<batch-id>/<P-code>
```

Sanity check: `git worktree list` should show only the main tree;
`git branch --list 'batch/*'` should be empty.

Push the merge-target branch to its remote (`loop.sh` also does this
on iteration end, but pushing here makes the batch boundary
observable).

## Constraints

- Cap N at 5 even if the user asks for more.
- Never tick the plan if the global gate is red.
- Do not run the global gate inside any engine-implementer — it runs
  once at Step 6 on the merged tree.
- If an agent in Waves 2–4 fails for a single item (e.g. test-writer
  can't produce a clean failure), drop that item from the batch:
  tear down its worktree + branch immediately, report it, continue
  with the rest. The tier-priority loop in Step 5 simply skips it.
- Hard-excluded items never appear in a multi-item batch — they
  always run alone, in the main tree, with no worktree machinery
  (Step 3 and Step 5's merge are both skipped for them).
