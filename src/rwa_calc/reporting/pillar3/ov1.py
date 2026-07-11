"""
Pillar 3 OV1 — Overview of RWEAs, as a declarative TemplateSpec.

Pipeline position:
    sealed aggregator-exit ledger + ReportingContext
        -> build_ov1_spec(framework) -> cellspec.execute() -> OV1 DataFrame

Cell semantics (unchanged from the imperative generator, golden-gated):

- Rows 1 / 29 (totals): Sum of ``rwa_final``; column c takes the generic
  8% own-funds shim.
- Row 2 (SA incl. equity) and the per-approach rows (3 F-IRB, 4 slotting,
  UK4a equity, 5 A-IRB): Sum of ``rwa_final`` over the ORIGIN approach
  (``reporting_approach_origin`` — the recorded pre-substitution basis;
  the post-substitution retarget is the plan's F-decision family). These
  cells report 0.0 for an absent approach (per-cell zero override on the
  Pillar 3 null template).
- Row 4a: pre-floor total (Sum of the conditional ``rwa_pre_floor``).
- Rows 5a-7b: pre-floor capital ratios x100 from the ReportingContext
  overrides (SideContext).
- Row 24: 250%-RW memo (Sum of ``rwa_final`` where ``reporting_rw`` is in
  the [2.495, 2.505] band).
- Rows 11-14 (Basel 3.1 equity sub-approaches): equity-origin legs narrowed
  by the presence-TOLERANT discriminators (``equity_transitional_approach``
  / ``ciu_approach`` — F6 columns the seal strips today, so these cells are
  recorded permanently-null in production).
- Row 26: output-floor multiplier (first non-null ``output_floor_pct``).
- Row 27: OF-ADJ from the output-floor summary (SideContext).
- Column b (T-1) stays null throughout; column c = a x 0.08 except the
  ratio rows and the floor rows 26/27 (the no-shim set).

References:
- CRR Part 8 Art. 438; PRA PS1/26 Annex XX (UKB OV1, incl. rows 11-14
  Art. 132-132C CIU sub-approaches and the floor rows 26/27)
- docs/plans/phase7-declarative-reporting.md §3.2 (S8 — Pillar 3 first)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from watchfire import cites

from rwa_calc.reporting.cellspec import (
    CellSpec,
    FirstNonNull,
    Formula,
    RowPredicate,
    SideContext,
    Sum,
    TemplateSpec,
    execute,
)
from rwa_calc.reporting.metadata import ReportingContext
from rwa_calc.reporting.pillar3.templates import OV1_COLUMNS, get_ov1_rows

if TYPE_CHECKING:
    from collections.abc import Mapping

    import polars as pl

    from rwa_calc.contracts.bundles import OutputFloorSummary
    from rwa_calc.contracts.config import Pillar3CapitalRatioOverrides

# Rows whose column ``a`` is a percentage (no 8% shim; SideContext ratio x100).
_RATIO_REFS: dict[str, str] = {
    "5a": "cet1_ratio_pre_floor",
    "5b": "cet1_ratio_pre_floor_transitional",
    "6a": "tier1_ratio_pre_floor",
    "6b": "tier1_ratio_pre_floor_transitional",
    "7a": "total_ratio_pre_floor",
    "7b": "total_ratio_pre_floor_transitional",
}

# Rows whose column ``a`` sums one origin approach (0.0 when absent).
_APPROACH_REFS: dict[str, tuple[str, ...]] = {
    "2": ("standardised", "equity"),
    "3": ("foundation_irb",),
    "4": ("slotting",),
    "UK4a": ("equity",),
    "5": ("advanced_irb",),
}

# Basel 3.1 equity sub-approach memo rows: origin equity legs narrowed by a
# presence-tolerant discriminator column == value (F6-stripped today).
_EQUITY_SUBAPPROACH_REFS: dict[str, tuple[str, str]] = {
    "11": ("equity_transitional_approach", "irb_transitional"),
    "12": ("ciu_approach", "look_through"),
    "13": ("ciu_approach", "mandate_based"),
    "14": ("ciu_approach", "fallback"),
}

# Floor rows whose column ``a`` is a multiplier (26) or RWA adjustment (27).
_FLOOR_NO_SHIM_REFS: frozenset[str] = frozenset({"26", "27"})


def _own_funds_shim(cells: Mapping[str, float | None], _prior: bool) -> float | None:
    """Column c = a x 0.08 (own-funds requirement) when a is populated."""
    a = cells["a"]
    return a * 0.08 if a is not None else None


def _row_a_cell(ref: str) -> CellSpec | None:
    """The column-``a`` binding for one OV1 row ref (None = stays null)."""
    if ref in ("1", "29"):
        return CellSpec(Sum("rwa_final"))
    if ref == "4a":
        return CellSpec(Sum("rwa_pre_floor"))
    if ref in _RATIO_REFS:
        return CellSpec(SideContext(_RATIO_REFS[ref], scale=100.0))
    if ref == "24":
        return CellSpec(Sum("rwa_final"), predicate=RowPredicate(rw_between=(2.495, 2.505)))
    if ref in _EQUITY_SUBAPPROACH_REFS:
        return CellSpec(
            Sum("rwa_final"),
            predicate=RowPredicate(
                approaches_origin=("equity",), equals=(_EQUITY_SUBAPPROACH_REFS[ref],)
            ),
        )
    if ref == "26":
        return CellSpec(FirstNonNull("output_floor_pct"))
    if ref == "27":
        return CellSpec(SideContext("of_adj"))
    if ref in _APPROACH_REFS:
        return CellSpec(
            Sum("rwa_final"),
            predicate=RowPredicate(approaches_origin=_APPROACH_REFS[ref]),
            empty_cell="zero",
        )
    return None


@cites("PS1/26, paragraph 132")
def build_ov1_spec(framework: str) -> TemplateSpec:
    """Build the OV1 TemplateSpec for one framework's row set.

    Carries the Art. 132-132C citation for the Basel 3.1 equity sub-approach
    memo rows 11-14 (moved here with the semantics from the retired
    ``_ov1_equity_subapproach_rwa`` generator helper).
    """
    rows = tuple(get_ov1_rows(framework))
    cells: dict[tuple[str, str], CellSpec] = {}
    for row in rows:
        a_cell = _row_a_cell(row.ref)
        if a_cell is not None:
            cells[(row.ref, "a")] = a_cell
            if row.ref not in _RATIO_REFS and row.ref not in _FLOOR_NO_SHIM_REFS:
                cells[(row.ref, "c")] = CellSpec(Formula(refs=("a",), fn=_own_funds_shim))
    return TemplateSpec(
        name="ov1",
        rows=rows,
        column_refs=tuple(col.ref for col in OV1_COLUMNS),
        cells=cells,
        empty_cell="null",
    )


_OV1_SPECS: dict[str, TemplateSpec] = {
    framework: build_ov1_spec(framework) for framework in ("CRR", "BASEL_3_1")
}


def generate_ov1(
    results: pl.LazyFrame,
    cols: set[str],
    framework: str,
    errors: list[str],
    capital_ratios: Pillar3CapitalRatioOverrides | None,
    output_floor_summary: OutputFloorSummary | None,
) -> pl.DataFrame | None:
    """Execute OV1 over the full sealed ledger.

    Preserves the imperative generator's contract: a missing ``rwa_final``
    column (impossible on the sealed ledger; reachable via direct invocation
    with synthetic frames) records the OV1 error and yields no template.
    """
    if "rwa_final" not in cols:
        errors.append("OV1: missing RWA column")
        return None
    spec = _OV1_SPECS.get(framework) or build_ov1_spec(framework)
    ctx = ReportingContext(
        output_floor_summary=output_floor_summary,
        capital_ratio_overrides=capital_ratios,
    )
    return execute(spec, results, ctx)
