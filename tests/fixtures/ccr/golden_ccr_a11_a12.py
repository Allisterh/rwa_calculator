"""
Golden CCR-A11 / CCR-A12 scenarios: SFT EAD via FCCM (CRR Art. 271(2)).

Pipeline position:
    fixture-builder output -> test-writer (tests/acceptance/ccr/)
    -> engine sft_fccm FCCM stage (engine/stages/sft.py)

SFT/FCCM separation (Phase 6): the CCR-A11/A12 inputs are supplied via
``RawDataBundle.sft`` (the lean ``RawSFTBundle``, built in
``tests/fixtures/ccr/sft_bundle_builder.py``) and priced by the peer
``sft_fccm`` stage — NOT the deleted in-CCR ``transaction_type == "sft"`` branch.
The SFT trade / collateral identifiers (``NS_SFT_001`` / ``NS_SFT_002`` etc.)
are unchanged, so the emitted ``ccr__NS_SFT_001`` / ``ccr__NS_SFT_002``
synthetic rows and every numeric result match the legacy in-CCR result exactly.

Scenario design (plan item P8.38, scenarios CCR-A11 and CCR-A12):

    Both scenarios share the same single SFT trade (notional GBP 60.7m) against
    counterparty ``CP_INST_001`` (institution, CQS 2, GB). The exposure side is a
    corporate bond (CQS 1, residual maturity 7y) lending.

    Reporting date: 2026-06-30 (CRR window, pre-PS1/26 effective date).
    Framework: CRR, permission_mode=STANDARDISED, SFTConfig.method="fccm".

    CCR-A11 — uncollateralised SFT
        No collateral posted/received; E* = E·(1 + HE).

    CCR-A12 — cash-collateralised SFT
        GBP 60m cash collateral received; HC_cash=0, HFX=0 (GBP/GBP).

Regulatory hand-calc (CRR Art. 223(5) + Art. 224 Table 1 + Art. 226(2)):

    E (notional)  = 60_700_000.00

    HE derivation:
        Exposure-side security: corp_bond, CQS 1, residual maturity 7y -> "5y_plus" band.
        H_10  = 0.08  (Art. 224 Table 1: debt sec, CQS 1, >5y residual)
        Liquidation period for SFTs: 5 business days (Art. 224(2)(c)).
        Scaling: H_m = H_10 x sqrt(T_m / 10)  (Art. 226(2))
                     = 0.08 x sqrt(5/10)
                     = 0.08 x 0.7071067811865476
                     = 0.05656854249492381   [IEEE-754 correctly rounded]

    E*(1 + HE) = 60_700_000 x 1.05656854249492381 = 64_133_710.52944188 (Python float)

    CCR-A11 (no collateral):
        CVA * (1 - HC - HFX) = 0
        E* = max(0, 64_133_710.529 - 0) = 64_133_710.52944188
        EAD  = 64_133_710.52944188
        RWA  = EAD x 0.50 = 32_066_855.26472094

    CCR-A12 (GBP 60m cash collateral):
        HC_cash = 0 ; HFX = 0 (GBP/GBP same currency)
        CVA * (1 - 0 - 0) = 60_000_000.00
        E* = max(0, 64_133_710.529 - 60_000_000) = 4_133_710.52944188
        EAD  = 4_133_710.52944188
        RWA  = EAD x 0.50 = 2_066_855.26472094

    Note: The scenario-architect proposal stated HE = 0.056568542494923804, but
    Python IEEE-754 arithmetic gives 0.05656854249492381 (last digit differs by 1 ULP).
    The fixture uses math.sqrt for ground-truth values; test-writer must reference the
    module constants (CCR_A11_EAD, CCR_A12_EAD, etc.) rather than the proposal literals.

Counterparty:
    CP_INST_001 — institution, CQS 2, GB.
    SA risk weight: CRR Art. 120 Table 3 → CQS 2 → 50%.

    NOTE: The counterparty reference ``CP_INST_001`` used here is distinct from the
    ``CP_001`` used by CCR-A1/A3/A10 golden scenarios. A fresh counterparty builder
    is provided so this module is self-contained and does not collide with existing
    golden scenario CP_001 data.

Trade HE input columns (not yet in TRADE_SCHEMA — engine-implementer will add them):
    exposure_collateral_type              String (nullable)  — "corp_bond" for A11/A12
    exposure_security_cqs                 Int8   (nullable)  — 1
    exposure_security_residual_maturity_years  Float64 (nullable) — 7.0

References:
    - CRR Art. 271(2) — SFT EAD computed via FCCM (not SA-CCR Art. 274).
    - CRR Art. 220(1)(a) — single-counterparty SFT / master-netting set scope.
    - CRR Art. 220(3)(a)(i) — standardised supervisory haircuts.
    - CRR Art. 223(5) — E* = max(0, E·(1+HE) − CVA·(1−HC−HFX)).
    - CRR Art. 224(2)(c) — 5-BD liquidation period for SFTs.
    - CRR Art. 224 Table 1 — H_10 = 0.08 for corp bond CQS 1 residual > 5y.
    - CRR Art. 226(2) — H_m = H_10 × √(T_m / 10) haircut scaling.
    - CRR Art. 120 Table 3 — institution CQS 2 → 50% SA risk weight.
    - PRA PS1/26 Art. 271/220-223 — verbatim carry-forward of CRR FCCM mechanics.
"""

from __future__ import annotations

import math
from datetime import date as _date
from pathlib import Path

import polars as pl

from rwa_calc.contracts.bundles import (
    RawDataBundle,
)
from rwa_calc.data.column_spec import dtypes_of
from rwa_calc.data.schemas import (
    COUNTERPARTY_SCHEMA,
    FACILITY_MAPPING_SCHEMA,
    FACILITY_SCHEMA,
    LENDING_MAPPING_SCHEMA,
    LOAN_SCHEMA,
    RATINGS_SCHEMA,
)
from tests.fixtures.raw_bundle import make_raw_bundle

# ---------------------------------------------------------------------------
# Scenario constants — single source of truth for test-writer assertions.
# ---------------------------------------------------------------------------

# Counterparty
CCR_A11_A12_COUNTERPARTY_REF: str = "CP_INST_001"
CCR_A11_A12_CP_ENTITY_TYPE: str = "institution"
CCR_A11_A12_CP_COUNTRY_CODE: str = "GB"
CCR_A11_A12_CP_INSTITUTION_CQS: int = 2

# Rating
CCR_A11_A12_RATING_REF: str = "RTG_INST_001"
CCR_A11_A12_RATING_TYPE: str = "external"
CCR_A11_A12_RATING_AGENCY: str = "S&P"
CCR_A11_A12_RATING_VALUE: str = "A"
CCR_A11_A12_RATING_DATE: _date = _date(2026, 1, 15)

# Shared trade / netting-set parameters (consumed by the SFT trade builders in
# sft_bundle_builder.py — SFT/FCCM separation Phase 6).
CCR_A11_TRADE_ID: str = "T_SFT_001"
CCR_A12_TRADE_ID: str = "T_SFT_002"
CCR_A11_NETTING_SET_ID: str = "NS_SFT_001"
CCR_A12_NETTING_SET_ID: str = "NS_SFT_002"
CCR_A11_A12_NOTIONAL: float = 60_700_000.00
CCR_A11_A12_CURRENCY: str = "GBP"
CCR_A11_A12_START_DATE: _date = _date(2026, 6, 30)
CCR_A11_A12_MATURITY_DATE: _date = _date(2026, 9, 30)

# Exposure-side HE inputs (corp bond CQS 1, residual > 5y — "5y_plus" haircut band).
# Declared first-class on SFT_TRADE_SCHEMA (Phase 2) and consumed by the SFT
# trade builder; the Art. 223(5) HE lookup keys on these three fields.
CCR_A11_A12_EXPOSURE_COLLATERAL_TYPE: str = "corp_bond"
CCR_A11_A12_EXPOSURE_SECURITY_CQS: int = 1
CCR_A11_A12_EXPOSURE_SECURITY_RESIDUAL_MATURITY_YEARS: float = 7.0

# CCR-A12 collateral parameters
CCR_A12_COLLATERAL_REF: str = "COLL_SFT_001"
CCR_A12_COLLATERAL_TYPE: str = "cash"
CCR_A12_COLLATERAL_MARKET_VALUE: float = 60_000_000.00
CCR_A12_COLLATERAL_CURRENCY: str = "GBP"

# ---------------------------------------------------------------------------
# Hand-calculated expected outputs — single source of truth.
# ---------------------------------------------------------------------------

# HE calculation (Art. 224 Table 1 + Art. 226(2)):
#   H_10 = 0.08 (corp_bond CQS 1, residual > 5y)
#   liquidation_period = 5 BD (Art. 224(2)(c) SFT floor)
#   HE = H_10 × √(5/10)
CCR_A11_A12_H10: float = 0.08
CCR_A11_A12_LIQUIDATION_PERIOD_BD: int = 5
CCR_A11_A12_HE: float = CCR_A11_A12_H10 * math.sqrt(CCR_A11_A12_LIQUIDATION_PERIOD_BD / 10)
# = 0.056568542494923804

# E·(1+HE) — common to both scenarios
CCR_A11_A12_E_TIMES_1_PLUS_HE: float = CCR_A11_A12_NOTIONAL * (1.0 + CCR_A11_A12_HE)
# = 64_133_710.4314378749

# CCR-A11 — uncollateralised
CCR_A11_EAD: float = CCR_A11_A12_E_TIMES_1_PLUS_HE
# = 64_133_710.4314378749
CCR_A11_RISK_WEIGHT: float = 0.50
CCR_A11_RWA: float = CCR_A11_EAD * CCR_A11_RISK_WEIGHT
# = 32_066_855.2157189374

# CCR-A12 — GBP cash collateral (HC=0, HFX=0)
CCR_A12_CVA_NET: float = CCR_A12_COLLATERAL_MARKET_VALUE  # × (1 − 0 − 0) = 60_000_000
CCR_A12_EAD: float = max(0.0, CCR_A11_A12_E_TIMES_1_PLUS_HE - CCR_A12_CVA_NET)
# = 4_133_710.4314378749
CCR_A12_RISK_WEIGHT: float = 0.50
CCR_A12_RWA: float = CCR_A12_EAD * CCR_A12_RISK_WEIGHT
# = 2_066_855.2157189374

# Monetary tolerance for acceptance assertions (1 ppm, consistent with other goldens).
CCR_A11_A12_MONETARY_REL_TOLERANCE: float = 1e-6

# Expected output identifiers (matching pipeline_adapter format for SFT FCCM rows)
CCR_A11_EXPOSURE_REFERENCE: str = "ccr__NS_SFT_001"
CCR_A12_EXPOSURE_REFERENCE: str = "ccr__NS_SFT_002"
CCR_A11_A12_CCR_METHOD: str = "fccm_sft"
CCR_A11_A12_RISK_TYPE: str = "CCR_SFT"
CCR_A11_A12_EXPOSURE_CLASS_SA: str = "institution"


# ---------------------------------------------------------------------------
# SFT input frames.
#
# The CCR-A11/A12 SFT trade / collateral frames (SFT_TRADE_SCHEMA /
# SFT_COLLATERAL_SCHEMA, RawDataBundle.sft) live in
# ``tests/fixtures/ccr/sft_bundle_builder.py`` — ``build_sft_bundle_ccr_a11`` /
# ``build_sft_bundle_ccr_a12``, keyed on the A11/A12 ids defined above. The
# bundle assemblers and the parquet save helper below import them lazily (an
# import cycle would otherwise form, since sft_bundle_builder imports this
# module's scenario constants).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Portfolio-stub builders (counterparty + rating).
# ---------------------------------------------------------------------------


def _build_cp_inst_001_counterparty() -> pl.LazyFrame:
    """
    Return a one-row counterparty LazyFrame for CP_INST_001.

    CP_INST_001 is a GB institution with external CQS 2.
    entity_type="institution" → Classifier → ExposureClass.INSTITUTION.
    CRR Art. 120(1) Table 3: CQS 2 → 50% SA risk weight.

    institution_cqs=2 is set so narrow unit tests that bypass the rating
    inheritance pipeline can still resolve the risk weight.
    """
    row = {
        "counterparty_reference": CCR_A11_A12_COUNTERPARTY_REF,
        "counterparty_name": "P8.38 SFT Test Institution (CQS 2)",
        "entity_type": CCR_A11_A12_CP_ENTITY_TYPE,
        "country_code": CCR_A11_A12_CP_COUNTRY_CODE,
        "default_status": False,
        "apply_fi_scalar": False,
        "is_managed_as_retail": False,
        "institution_cqs": CCR_A11_A12_CP_INSTITUTION_CQS,
    }
    return pl.DataFrame([row], schema=dtypes_of(COUNTERPARTY_SCHEMA)).lazy()


def _build_cp_inst_001_rating() -> pl.LazyFrame:
    """
    Return a one-row external ratings LazyFrame for CP_INST_001.

    S&P "A" = CQS 2 under CRR ECRA.
    CRR Art. 120(1) Table 3: institution CQS 2 → 50% risk weight.
    pd=None — external ratings carry no PD.
    """
    row = {
        "rating_reference": CCR_A11_A12_RATING_REF,
        "counterparty_reference": CCR_A11_A12_COUNTERPARTY_REF,
        "rating_type": CCR_A11_A12_RATING_TYPE,
        "rating_agency": CCR_A11_A12_RATING_AGENCY,
        "rating_value": CCR_A11_A12_RATING_VALUE,
        "cqs": CCR_A11_A12_CP_INSTITUTION_CQS,
        "pd": None,
        "rating_date": CCR_A11_A12_RATING_DATE,
        "is_solicited": True,
        "model_id": None,
        "is_short_term": False,
        "scope_type": None,
        "scope_id": None,
    }
    return pl.DataFrame([row], schema=dtypes_of(RATINGS_SCHEMA)).lazy()


def _build_empty_facilities() -> pl.LazyFrame:
    return pl.LazyFrame(schema=dtypes_of(FACILITY_SCHEMA))


def _build_empty_loans() -> pl.LazyFrame:
    return pl.LazyFrame(schema=dtypes_of(LOAN_SCHEMA))


def _build_empty_facility_mappings() -> pl.LazyFrame:
    return pl.LazyFrame(schema=dtypes_of(FACILITY_MAPPING_SCHEMA))


def _build_empty_lending_mappings() -> pl.LazyFrame:
    return pl.LazyFrame(schema=dtypes_of(LENDING_MAPPING_SCHEMA))


# ---------------------------------------------------------------------------
# RawDataBundle assembly helpers (SFT/FCCM separation Phase 6: raw.sft).
# ---------------------------------------------------------------------------


def build_raw_data_bundle_ccr_a11() -> RawDataBundle:
    """
    Assemble a complete RawDataBundle for CCR-A11 (uncollateralised SFT).

    SFT/FCCM separation (Phase 6): the SFT trade is now supplied via
    ``RawDataBundle.sft`` (the lean ``RawSFTBundle``) and priced by the peer
    ``sft_fccm`` FCCM stage — NOT the deleted in-CCR ``transaction_type == "sft"``
    branch. The single SFT trade (T_SFT_001, GBP 60.7m, corp bond exposure CQS 1
    7y) in netting set NS_SFT_001 against CP_INST_001 (institution, CQS 2, GB)
    exercises the Art. 271(2) FCCM SFT path without any collateral offset. The
    emitted ``ccr__NS_SFT_001`` synthetic row and its EAD/RWA are byte-identical
    to the legacy in-CCR result (same ids, same E* core).

    Key assertion:
        EAD  = E × (1 + HE) = 64_133_710.4314378749 (Art. 223(5) with CVA=0)
        RWA  = EAD × 0.50   = 32_066_855.2157189374 (Art. 120 Table 3 CQS 2)

    References:
        CRR Art. 271(2), 223(5), 224 Table 1, 226(2), 120 Table 3.
    """
    # Function-local import to avoid a module-level import cycle
    # (sft_bundle_builder imports this module's scenario constants).
    from .sft_bundle_builder import build_sft_bundle_ccr_a11

    return make_raw_bundle(
        counterparties=_build_cp_inst_001_counterparty(),
        facilities=_build_empty_facilities(),
        loans=_build_empty_loans(),
        facility_mappings=_build_empty_facility_mappings(),
        lending_mappings=_build_empty_lending_mappings(),
        ratings=_build_cp_inst_001_rating(),
        sft=build_sft_bundle_ccr_a11(),
    )


def build_raw_data_bundle_ccr_a12() -> RawDataBundle:
    """
    Assemble a complete RawDataBundle for CCR-A12 (cash-collateralised SFT).

    SFT/FCCM separation (Phase 6): the SFT trade + collateral are now supplied
    via ``RawDataBundle.sft`` (the lean ``RawSFTBundle``) and priced by the peer
    ``sft_fccm`` FCCM stage. The single SFT trade (T_SFT_002, GBP 60.7m, corp bond
    exposure CQS 1 7y) in netting set NS_SFT_002 against CP_INST_001 (institution,
    CQS 2, GB) exercises the Art. 271(2) FCCM SFT path with GBP 60m cash
    collateral received (HC_cash=0, HFX=0 for same-currency pair).

    Key assertion:
        E* = max(0, E·(1+HE) − CVA) = 4_133_710.4314378749 (Art. 223(5))
        EAD  = 4_133_710.4314378749
        RWA  = EAD × 0.50 = 2_066_855.2157189374

    References:
        CRR Art. 271(2), 223(5), 224 Table 1, 226(2), 120 Table 3.
    """
    # Function-local import to avoid a module-level import cycle
    # (sft_bundle_builder imports this module's scenario constants).
    from .sft_bundle_builder import build_sft_bundle_ccr_a12

    return make_raw_bundle(
        counterparties=_build_cp_inst_001_counterparty(),
        facilities=_build_empty_facilities(),
        loans=_build_empty_loans(),
        facility_mappings=_build_empty_facility_mappings(),
        lending_mappings=_build_empty_lending_mappings(),
        ratings=_build_cp_inst_001_rating(),
        sft=build_sft_bundle_ccr_a12(),
    )


# ---------------------------------------------------------------------------
# Save helper — canonical entry point for generate_all.py and standalone use.
# ---------------------------------------------------------------------------


def save_ccr_a11_a12_fixtures(output_dir: Path | None = None) -> dict[str, Path]:
    """
    Write the CCR-A11 / CCR-A12 golden parquet files to *output_dir*.

    SFT/FCCM separation (Phase 6): the CCR-A11/A12 inputs are now SFT-shaped
    (``SFT_TRADE_SCHEMA`` / ``SFT_COLLATERAL_SCHEMA``, ``RawDataBundle.sft``),
    NOT the deleted in-CCR ``TRADE_SCHEMA`` ``transaction_type == "sft"`` rows.

    Files produced:
        sft_a11_trades.parquet      — 1 row (T_SFT_001, NS_SFT_001, no collateral)
        sft_a12_trades.parquet      — 1 row (T_SFT_002, NS_SFT_002, w/ collateral)
        sft_a12_collateral.parquet  — 1 row (COLL_SFT_001, cash, GBP 60m)

    The A11 SFT collateral is empty (uncollateralised) and not written.

    Args:
        output_dir: Target directory. Defaults to the directory containing
            this script (``tests/fixtures/ccr/``).

    Returns:
        Dict mapping artefact name (without .parquet) to saved absolute Path.
    """
    # Function-local import to avoid a module-level import cycle
    # (sft_bundle_builder imports this module's scenario constants).
    from .sft_bundle_builder import build_sft_bundle_ccr_a11, build_sft_bundle_ccr_a12

    if output_dir is None:
        output_dir = Path(__file__).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    a11 = build_sft_bundle_ccr_a11()
    a12 = build_sft_bundle_ccr_a12()
    assert a12.collateral is not None  # A12 always carries collateral

    artefacts: list[tuple[str, pl.DataFrame]] = [
        ("sft_a11_trades", a11.trades.sft_trades.collect()),
        ("sft_a12_trades", a12.trades.sft_trades.collect()),
        ("sft_a12_collateral", a12.collateral.sft_collateral.collect()),
    ]

    saved: dict[str, Path] = {}
    for name, df in artefacts:
        path = output_dir / f"{name}.parquet"
        df.write_parquet(path)
        saved[name] = path

    return saved


def main() -> None:
    """Entry point for standalone generation."""
    saved = save_ccr_a11_a12_fixtures()
    print("CCR-A11 / CCR-A12 golden fixture generation complete")
    print("-" * 70)
    for name, path in saved.items():
        df = pl.read_parquet(path)
        print(f"  {name:<35} {df.height:>2} row(s)  {len(df.columns):>2} cols  ->  {path.name}")
    print("-" * 70)
    he = CCR_A11_A12_HE
    e_times_1_he = CCR_A11_A12_E_TIMES_1_PLUS_HE
    print(f"HE  = {CCR_A11_A12_H10} × sqrt({CCR_A11_A12_LIQUIDATION_PERIOD_BD}/10)")
    print(f"    = {he:.18f}")
    print(f"E·(1+HE) = {CCR_A11_A12_NOTIONAL:,.2f} × (1 + {he:.18f})")
    print(f"         = {e_times_1_he:.10f}")
    print()
    print("CCR-A11 (uncollateralised):")
    print(f"  EAD  = {CCR_A11_EAD:.10f}")
    print(f"  RWA  = {CCR_A11_RWA:.10f}")
    print()
    print("CCR-A12 (GBP 60m cash collateral):")
    print(f"  CVA  = {CCR_A12_CVA_NET:,.2f}")
    print(f"  E*   = max(0, {e_times_1_he:.4f} - {CCR_A12_CVA_NET:,.2f})")
    print(f"  EAD  = {CCR_A12_EAD:.10f}")
    print(f"  RWA  = {CCR_A12_RWA:.10f}")


if __name__ == "__main__":
    main()
