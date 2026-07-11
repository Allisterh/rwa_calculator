"""
Reporting-ledger builder for hand-rolled reconciliation test frames.

Pipeline position:
    test fixtures -> ReconciliationRunner (whose input contract is the sealed
    aggregator exit)

Key responsibilities:
- Mirror the aggregator's sealed reporting projection onto a hand-rolled
  our-side frame, so unit tests stay shape-identical to production without
  re-pinning every literal.

The sealed aggregator exit carries the Phase 7 canonical ledger columns
(``reporting_class``, ``reporting_class_origin``, ``reporting_approach``,
``reporting_approach_origin``). Production derives them once in the aggregator
(``_add_exposure_class_applied`` -> ``_add_post_crm_reporting_class`` /
``_approach`` -> ``_add_reporting_projection``); this builder applies the same
identities to whatever raw columns a test supplies — for an unguaranteed row
the applied and post-CRM classes ARE the origination class. Frames that set
the substitution columns explicitly keep their values.
"""

from __future__ import annotations

import polars as pl


def with_reporting_ledger(ours: pl.LazyFrame) -> pl.LazyFrame:
    """Add the canonical ``reporting_*`` ledger columns a test frame omits."""
    cols = set(ours.collect_schema().names())

    def first(*names: str) -> str | None:
        return next((n for n in names if n in cols), None)

    derivations = (
        (
            "reporting_class",
            ("exposure_class_post_crm", "exposure_class_applied", "exposure_class"),
        ),
        ("reporting_class_origin", ("exposure_class_applied", "exposure_class")),
        ("reporting_approach", ("approach_post_crm", "approach_applied")),
        ("reporting_approach_origin", ("approach_applied",)),
    )
    exprs: list[pl.Expr] = []
    for target, sources in derivations:
        src = first(*sources)
        if target not in cols and src is not None:
            exprs.append(pl.col(src).alias(target))
    return ours.with_columns(exprs) if exprs else ours
