---
description: Refresh DOCS_IMPLEMENTATION_PLAN.md — audit docs/ vs the regulatory PDFs and source code for new gaps. Plan-only; no docs/ edits.
---

You are refreshing the project's documentation work queue at
`DOCS_IMPLEMENTATION_PLAN.md` (root of the repo). Plan-only
iteration — no `docs/` or `src/` edits are allowed.

## Step 1 — delegate to plan-curator

Invoke the `plan-curator` agent. Prompt:

> Curate `DOCS_IMPLEMENTATION_PLAN.md`. Audit `docs/`
> end-to-end against the regulatory PDFs in `docs/assets/` and
> against `src/rwa_calc/`. Apply your standard workflow, with the
> **audit pass first** — no skipping it on the grounds that the
> queue looks fine:
>
> 1. **Audit every existing item — open *and* completed.** Both
>    plan files are trust anchors for downstream agents; a wrong
>    bullet gets implemented as if it described a real gap. For
>    each bullet, verify: **claim is independently verifiable**
>    (don't take the bullet's reading of the regulation or the
>    docs on trust — confirm via the `basel31` / `crr` Skill that
>    the regulatory source says what the bullet claims, *and*
>    confirm by reading the cited docs page that it actually
>    misses or misstates the rule), cited target page still
>    exists, the gap is still real (the docs page hasn't been
>    written or corrected since the bullet was filed), no newer
>    duplicate, in the right plan file, right priority bucket,
>    right scope. Close `closed-claim-invalid` for bullets that
>    were wrong when filed; escalate `Unverifiable` when a claim
>    can't be confirmed in a reasonable spot-check rather than
>    leaving it silently in the queue. Close / re-prioritise /
>    re-scope / merge as needed per your system prompt's audit
>    rules. Surface items that should live on the code plan
>    instead.
> 2. **Scan for new findings**:
>    - PDF-to-docs mapping per `PROMPT_docs_plan.md`
>      (`ps126app1.pdf`, `crr.pdf`, comparison PDF, COREP/Pillar 3
>      instruction PDFs).
>    - Code-docs alignment — risk weights, formulas, article
>      references, scenario-ID coverage.
>    - Basel 3.1 spec parity vs. the matching CRR specs.
> 3. **Add new items** in priority order with the standard bullet
>    format. Use the existing `Phase N Findings` sub-headings or
>    open a new dated phase if appropriate.
>
> Cite every regulatory scalar via the `basel31` or `crr` Skill.
> Do not edit any file other than `DOCS_IMPLEMENTATION_PLAN.md`.
> Return the structured audit summary (Added / Closed /
> Re-scoped / Merged / Unverifiable / Cross-file) defined in your
> system prompt.

## Step 2 — review (top level)

Once plan-curator returns:

1. Run `git diff DOCS_IMPLEMENTATION_PLAN.md` and skim — focus on
   the audit changes (Closed, Re-scoped, Merged) as well as the
   Added list. Audit changes are easy to miss in diff because
   they're often a single bullet edit, but they're the load-bearing
   part of a refresh.
2. Confirm the diff is confined to `DOCS_IMPLEMENTATION_PLAN.md`.
3. If plan-curator's return value flagged any **cross-file
   recommendations** — items that are really code bugs and belong
   in `IMPLEMENTATION_PLAN.md` (Priority 3 "Docs Correct, Code Has
   Known Issue") — surface them and offer to trigger
   `/refresh-plan` afterwards.

## Step 3 — commit

Stage, commit, and push to the current branch with a message
`chore(plan): refresh DOCS_IMPLEMENTATION_PLAN.md (+N items, -M completed)`.

## Constraints

- No `docs/`, no `src/`, no test edits. Only the plan file.
- Do not auto-trigger `/next-doc` from here.
- If you discover the regulatory PDFs are missing from
  `docs/assets/`, surface that and stop — do not run
  `scripts/download_docs.py` from a plan-only loop.
