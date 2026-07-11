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
        ("reporting_ead", ("ead_final",)),
        ("reporting_rw", ("risk_weight",)),
    )
    dtypes: dict[str, pl.DataType] = {
        "reporting_class": pl.String(),
        "reporting_class_origin": pl.String(),
        "reporting_approach": pl.String(),
        "reporting_approach_origin": pl.String(),
        "reporting_ead": pl.Float64(),
        "reporting_rw": pl.Float64(),
    }
    exprs: list[pl.Expr] = []
    for target, sources in derivations:
        if target in cols:
            continue
        src = first(*sources)
        if src is not None:
            exprs.append(pl.col(src).alias(target))
        else:
            # No source on this synthetic frame: inject a typed null, exactly
            # as the lenient seal would — the sealed ledger always carries the
            # column, and a null never matches a predicate.
            exprs.append(pl.lit(None, dtype=dtypes[target]).alias(target))
    return ours.with_columns(exprs) if exprs else ours


class LedgerShimPillar3Generator:
    """Test shim: a Pillar3Generator whose lazyframe entry first mirrors the
    sealed reporting projection onto the hand-rolled synthetic frame — the
    production input contract is the sealed aggregator exit, and the unit
    estate must stay shape-identical to it (Phase 7 S0b re-baseline rule)."""

    def __new__(cls):  # noqa: D102 - thin factory, keeps isinstance(Pillar3Generator)
        from rwa_calc.reporting.pillar3.generator import Pillar3Generator

        class _Shim(Pillar3Generator):
            # Mirrors the parent signature exactly — tests introspect it via
            # inspect.signature to feature-gate the prior-period kwarg.
            def generate_from_lazyframe(
                self,
                results,
                *,
                framework="CRR",
                capital_ratios=None,
                output_floor_summary=None,
                previous_period_results=None,
            ):
                return super().generate_from_lazyframe(
                    with_reporting_ledger(results),
                    framework=framework,
                    capital_ratios=capital_ratios,
                    output_floor_summary=output_floor_summary,
                    previous_period_results=previous_period_results,
                )

        return _Shim()
