"""
P1.146 fixtures: null ``is_guaranteed`` must never drop or mis-bucket a row.

Pipeline position:
    fixture-builder output → OutputAggregator.aggregate() (fed directly; no
    RawDataBundle or parquet inputs).

Key responsibilities:
- Provide an ``sa_results`` LazyFrame in the PHYSICAL per-leg shape the CRM
  stage emits (``engine/crm/guarantees.py``): a guaranteed exposure is a
  ``__G_`` guaranteed leg + a ``__REM`` retained leg, not one row carrying
  both portions.
- EXP_GUAR__G_/__REM: the two legs of a guaranteed CORPORATE exposure with a
  central-government guarantor.
- EXP_PLAIN: is_guaranteed=False (non-guaranteed control row).
- EXP_NULL:  is_guaranteed=null  (the P1.146 trigger: Polars Boolean null).

History: the original defect was ``_crm_reporting.py``'s
``~pl.col("is_guaranteed")`` filters silently dropping the Boolean-null row
from the post-CRM views (``~null`` evaluates to null, not True). Phase 7 S4
retired that entire re-split machinery — the summaries are now pure group-bys
of the sealed reporting ledger, where a null ``is_guaranteed`` falls through
the ``when`` chain to ``reporting_leg_role="whole"`` and the applied class.
The surviving pins assert exactly that: the null row is present on the ledger,
labelled ``whole``, bucketed under its applied class, and counted in
``summary_by_class``.

Ledger expectations (Phase 7 S4):
    results height == 4 (two physical legs + plain + null — nothing dropped)
    EXP_NULL: reporting_leg_role="whole", reporting_class="CORPORATE",
              reporting_ead=750_000.0, reporting_rw=1.0
    summary_by_class CORPORATE: total_ead = 400_000 (__REM) + 1_000_000
              (EXP_PLAIN) + 750_000 (EXP_NULL) = 2_150_000, count = 3
    summary_by_class CENTRAL_GOVT_CENTRAL_BANK: total_ead = 600_000 (the
              guaranteed leg under the guarantor's class), count = 1
    control: total ledger EAD = 2_750_000 (nothing dropped, nothing doubled)

References:
    - engine/aggregator/aggregator.py::_add_reporting_projection (leg roles)
    - engine/aggregator/_summaries.py (ledger group-bys)
"""

from __future__ import annotations

import polars as pl

from tests.fixtures.contract_columns import pad_sa_branch

# ---------------------------------------------------------------------------
# Scenario constants — referenced by tests for assertion values
# ---------------------------------------------------------------------------

EXP_GUAR_LEG_REF: str = "EXP_GUAR__G_GUAR001"
EXP_REM_LEG_REF: str = "EXP_GUAR__REM"
EXP_PLAIN_REF: str = "EXP_PLAIN"
EXP_NULL_REF: str = "EXP_NULL"

CP_GUAR_REF: str = "CP_GUAR"
CP_PLAIN_REF: str = "CP_PLAIN"
CP_NULL_REF: str = "CP_NULL"

GUARANTOR_REF: str = "GUAR001"

# EADs (per physical leg)
EAD_GUAR_LEG: float = 600_000.0
EAD_REM_LEG: float = 400_000.0
EAD_PLAIN: float = 1_000_000.0
EAD_NULL: float = 750_000.0

# Risk weights
RW_GUARANTOR: float = 0.0  # central govt guarantor (substituted onto the __G_ leg)
RW_BORROWER: float = 1.0  # CORPORATE borrower (the retained leg)
RW_PLAIN: float = 1.0
RW_NULL: float = 1.0

# Ledger control totals
TOTAL_LEDGER_EAD: float = EAD_GUAR_LEG + EAD_REM_LEG + EAD_PLAIN + EAD_NULL  # 2_750_000.0
LEDGER_EXPECTED_ROWS: int = 4

# summary_by_class expectations
CORPORATE_TOTAL_EAD: float = EAD_REM_LEG + EAD_PLAIN + EAD_NULL  # 2_150_000.0
CORPORATE_EXPOSURE_COUNT: int = 3
SOVEREIGN_TOTAL_EAD: float = EAD_GUAR_LEG  # 600_000.0
SOVEREIGN_EXPOSURE_COUNT: int = 1


# ---------------------------------------------------------------------------
# Public builder — returns LazyFrame directly (no parquet involved)
# ---------------------------------------------------------------------------


def build_sa_results() -> pl.LazyFrame:
    """Return the four-row physical-leg SA results LazyFrame for P1.146.

    Fed directly to ``OutputAggregator.aggregate()``, bypassing the loader and
    CRM processor. ``is_guaranteed`` is explicitly cast to ``pl.Boolean`` so
    the null on EXP_NULL is a true Polars Boolean null (not a Python ``None``
    in an object column); the sa_branch pad does not fill it.
    """
    return pad_sa_branch(
        pl.LazyFrame(
            {
                "exposure_reference": [
                    EXP_GUAR_LEG_REF,
                    EXP_REM_LEG_REF,
                    EXP_PLAIN_REF,
                    EXP_NULL_REF,
                ],
                "counterparty_reference": [CP_GUAR_REF, CP_GUAR_REF, CP_PLAIN_REF, CP_NULL_REF],
                "exposure_class": ["CORPORATE"] * 4,
                "approach_applied": ["SA"] * 4,
                "ead_final": [EAD_GUAR_LEG, EAD_REM_LEG, EAD_PLAIN, EAD_NULL],
                "risk_weight": [RW_GUARANTOR, RW_BORROWER, RW_PLAIN, RW_NULL],
                "rwa_final": [
                    EAD_GUAR_LEG * RW_GUARANTOR,
                    EAD_REM_LEG * RW_BORROWER,
                    EAD_PLAIN * RW_PLAIN,
                    EAD_NULL * RW_NULL,
                ],
                "pre_crm_exposure_class": ["CORPORATE"] * 4,
                "post_crm_exposure_class_guaranteed": [
                    "CENTRAL_GOVT_CENTRAL_BANK",
                    None,
                    None,
                    None,
                ],
                "is_guaranteed": pl.Series(
                    [True, False, False, None],
                    dtype=pl.Boolean,
                ),
                "guaranteed_portion": [EAD_GUAR_LEG, 0.0, 0.0, 0.0],
                "unguaranteed_portion": [0.0, EAD_REM_LEG, EAD_PLAIN, EAD_NULL],
                "guarantor_reference": [GUARANTOR_REF, None, None, None],
                "parent_exposure_reference": ["EXP_GUAR", "EXP_GUAR", None, None],
                "pre_crm_risk_weight": [RW_BORROWER, RW_BORROWER, RW_PLAIN, RW_NULL],
                "guarantor_rw": [RW_GUARANTOR, None, None, None],
            }
        )
    )
