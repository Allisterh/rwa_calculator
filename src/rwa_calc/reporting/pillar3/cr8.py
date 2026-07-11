"""
Pillar 3 CR8 — RWEA flow statement for IRB, as a declarative TemplateSpec.

Pipeline position:
    sealed aggregator-exit ledger (IRB non-slotting subset)
        -> CR8_SPEC -> cellspec.execute() -> CR8 DataFrame

The first template through the ONE executor (Phase 7 S7 pilot). Cell
semantics (unchanged from the imperative generator, golden-gated):

- Row 9 (closing RWEA)  = Sum of the current period's ``rwa_final``.
- Row 1 (opening RWEA)  = the same sum over the prior-period frame; null when
  no prior period was supplied.
- Row 8 (Other)         = the signed residual ``closing - opening`` when a
  prior period exists (a None side coerces to zero — PS1/26 Annex XXII §11),
  null otherwise.
- Rows 2-7 (per-driver flow components) stay null — they need exposure-level
  period-over-period lineage two point-in-time snapshots cannot provide.

Input selection (the IRB non-slotting subset and the lenient prior-period
column handling) deliberately stays with the generator's dispatch router:
``previous_period_results`` is an EXTERNAL prior-run frame that may predate
the sealed reporting-ledger columns, so its filtering keeps the legacy
column fallbacks until the S8 retarget records otherwise.

References:
- CRR Part 8 Art. 438(h); PRA PS1/26 Annex XXII §11
- docs/plans/phase7-declarative-reporting.md §3.2 (S7)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rwa_calc.reporting.cellspec import CellSpec, Formula, PriorPeriod, Sum, TemplateSpec, execute
from rwa_calc.reporting.metadata import ReportingContext
from rwa_calc.reporting.pillar3.templates import CR8_COLUMNS, CR8_ROWS

if TYPE_CHECKING:
    from collections.abc import Mapping

    import polars as pl


def _other_flow(cells: Mapping[str, float | None], prior_available: bool) -> float | None:
    """Row 8 residual: ``closing - opening`` with a prior period, else null."""
    if not prior_available:
        return None
    return (cells["9"] or 0.0) - (cells["1"] or 0.0)


CR8_SPEC = TemplateSpec(
    name="cr8",
    rows=tuple(CR8_ROWS),
    column_refs=tuple(col.ref for col in CR8_COLUMNS),
    cells={
        ("1", "a"): CellSpec(PriorPeriod(Sum("rwa_final"))),
        ("8", "a"): CellSpec(Formula(refs=("9", "1"), fn=_other_flow)),
        ("9", "a"): CellSpec(Sum("rwa_final")),
    },
    empty_cell="null",
)


def generate_cr8(
    irb_data: pl.LazyFrame,
    prior_irb_data: pl.LazyFrame | None,
    cols: set[str],
    errors: list[str],
) -> pl.DataFrame | None:
    """Execute CR8 over the pre-filtered IRB (non-slotting) subset.

    Preserves the imperative generator's contract: a missing ``rwa_final``
    column (impossible on the sealed ledger; reachable via direct invocation
    with synthetic frames) records the CR8 error and yields no template.
    """
    if "rwa_final" not in cols:
        errors.append("CR8: missing RWA column")
        return None
    ctx = ReportingContext(template_set=None, previous_period_results=prior_irb_data)
    return execute(CR8_SPEC, irb_data, ctx)
