"""
CRR rulebook pack — pre-Basel-3.1 cited regime entries.

Pipeline position:
    Amendment layer for the ``"crr"`` regime (``REGIME_PACKS["crr"] =
    ("common", "crr")``); overlaid on the common pack by
    ``rulebook/resolve.py``, overriding any colliding entry names.

Key responsibilities:
- Hold the CRR-specific proof-pack values: the IRB K scaling factor, the
  SME/infrastructure supporting-factor feature flag, and a small CQS->RW
  lookup demonstrating the ``LookupTable`` shape.

References:
- CRR Art. 153(1): IRB risk-weight scaling factor (1.06).
- CRR Art. 501: SME supporting factor (and Art. 501a infrastructure).
- CRR Art. 122: standardised corporate risk weights by credit-quality step.
"""

from __future__ import annotations

from decimal import Decimal

from rwa_calc.rulebook.model import (
    Citation,
    DecisionTable,
    Feature,
    LookupTable,
    RuleEntry,
    ScalarParam,
)

ENTRIES: dict[str, RuleEntry] = {
    "irb_scaling_factor": ScalarParam(
        name="irb_scaling_factor",
        value=Decimal("1.06"),
        citation=Citation("CRR", "153(1)"),
    ),
    "supporting_factors": Feature(
        name="supporting_factors",
        enabled=True,
        citation=Citation("CRR", "501"),
    ),
    "corporate_cqs_rw": LookupTable(
        name="corporate_cqs_rw",
        entries={1: Decimal("0.20"), 2: Decimal("0.50")},
        key="cqs",
        citation=Citation("CRR", "122"),
        default=Decimal("1.00"),
    ),
    # F-IRB collateral step-functions apply under CRR (Art. 230 Table 5): the
    # overcollateralisation divisor and the 30% C*/C** minimum threshold. Basel
    # 3.1 removes both (see packs/b31.py); the divisor/threshold values
    # themselves live regime-invariantly in packs/common.py.
    "firb_overcollateralisation_divisor_applies": Feature(
        name="firb_overcollateralisation_divisor_applies",
        enabled=True,
        citation=Citation("CRR", "230", "Table 5 overcollateralisation divisor applies"),
    ),
    "firb_min_collateralisation_threshold_applies": Feature(
        name="firb_min_collateralisation_threshold_applies",
        enabled=True,
        citation=Citation("CRR", "230", "30% C*/C** minimum collateralisation threshold applies"),
    ),
    # Canonical F-IRB supervisory LGD (CRR Art. 161 / Art. 230 Table 5). One
    # table at FIRB granularity (collateral_type, seniority, is_fse) — the
    # single source for both the IRB-direct lookups (S5) and the CRM-shape
    # simple-category projection (engine/crm/expressions.py::supervisory_lgd_values).
    # CRR has no FSE split, so is_fse True == False for unsecured senior; the
    # life_insurance row is CRM-only (Art. 232(2)(b)).
    "firb_supervisory_lgd": DecisionTable(
        name="firb_supervisory_lgd",
        key_names=("collateral_type", "seniority", "is_fse"),
        rows=(
            (("unsecured", "senior", False), Decimal("0.45")),
            (("unsecured", "senior", True), Decimal("0.45")),
            (("unsecured", "subordinated", False), Decimal("0.75")),
            (("covered_bond", "senior", False), Decimal("0.1125")),
            (("financial_collateral", "senior", False), Decimal("0.00")),
            (("financial_collateral", "subordinated", False), Decimal("0.00")),
            (("receivables", "senior", False), Decimal("0.35")),
            (("receivables", "subordinated", False), Decimal("0.65")),
            (("residential_re", "senior", False), Decimal("0.35")),
            (("residential_re", "subordinated", False), Decimal("0.65")),
            (("commercial_re", "senior", False), Decimal("0.35")),
            (("commercial_re", "subordinated", False), Decimal("0.65")),
            (("other_physical", "senior", False), Decimal("0.40")),
            (("other_physical", "subordinated", False), Decimal("0.70")),
            (("purchased_receivables", "senior", False), Decimal("0.45")),
            (("purchased_receivables", "subordinated", False), Decimal("1.00")),
            (("purchased_receivables", "dilution_risk", False), Decimal("0.75")),
            (("life_insurance", "senior", False), Decimal("0.40")),
        ),
        citation=Citation("CRR", "161", "F-IRB supervisory LGD (Art. 161 / Art. 230 Table 5)"),
    ),
}
