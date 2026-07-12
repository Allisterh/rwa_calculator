"""
Phase 7 F8 — the sealed per-leg guarantee RWA benefit (Art. 235 relief).

Pipeline position:
    Loader -> HierarchyResolver -> Classifier -> CRMProcessor -> SACalculator
        -> OutputAggregator (seals ``guarantee_rwa_benefit`` on AGGREGATOR_EXIT)

Key assertion:
    ``guarantee_rwa_benefit`` = leg EAD x (borrower-basis RW - substituted RW),
    PRE-supporting-factor and PRE-floor, on the physical ``__G_`` guaranteed
    leg; 0.0 on the retained leg; and the per-exposure sum ties to the
    whole-exposure Art. 235 relief.

Hand-calc (the P1.110 fixture book — one loan, 100% guaranteed):
    Borrower: corporate CQS 5 -> RW 1.50 (CRR Table 5 AND B31 Table 6)
    Guarantor: corporate CQS 3 -> RW 1.00 (CRR Table 5) / 0.75 (B31 Table 6)
    Loan EAD = 1,000,000, full coverage.

    CRR:  benefit = 1,000,000 x (1.50 - 1.00) = 500,000
    B31:  benefit = 1,000,000 x (1.50 - 0.75) = 750,000
    Retained ``__REM`` leg (EAD 0, fully covered): benefit 0.0.

References:
    - CRR / PS1/26 Art. 235: RWA = (E - G_A) x r + G_A x g — the benefit is
      the difference between the two terms for the covered portion,
      G_A x (r - g)
    - docs/plans/phase7-declarative-reporting.md §6 decision F8 (recorded)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from rwa_calc.contracts.config import CalculationConfig, PermissionMode
from rwa_calc.data.column_spec import dtypes_of
from rwa_calc.data.schemas import FACILITY_MAPPING_SCHEMA, FACILITY_SCHEMA, LENDING_MAPPING_SCHEMA
from rwa_calc.engine.pipeline import PipelineOrchestrator
from tests.fixtures.raw_bundle import make_raw_bundle

_FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "p1_110" / "data"
_LOAN_REF = "LOAN_P1110"

_EXPECTED_BENEFIT_CRR = 500_000.0  # 1,000,000 x (1.50 - 1.00)
_EXPECTED_BENEFIT_B31 = 750_000.0  # 1,000,000 x (1.50 - 0.75)


def _run(config: CalculationConfig) -> pl.DataFrame:
    bundle = make_raw_bundle(
        facilities=pl.LazyFrame(schema=dtypes_of(FACILITY_SCHEMA)),
        loans=pl.scan_parquet(_FIXTURES_DIR / "loan.parquet"),
        counterparties=pl.scan_parquet(_FIXTURES_DIR / "counterparty.parquet"),
        facility_mappings=pl.LazyFrame(schema=dtypes_of(FACILITY_MAPPING_SCHEMA)),
        lending_mappings=pl.LazyFrame(schema=dtypes_of(LENDING_MAPPING_SCHEMA)),
        guarantees=pl.scan_parquet(_FIXTURES_DIR / "guarantee.parquet"),
        ratings=pl.scan_parquet(_FIXTURES_DIR / "rating.parquet"),
    )
    result = PipelineOrchestrator().run_with_data(bundle, config)
    return result.results.filter(pl.col("exposure_reference").str.starts_with(_LOAN_REF)).collect()


def _legs(df: pl.DataFrame) -> tuple[dict, dict]:
    guaranteed = df.filter(pl.col("reporting_leg_role") == "guaranteed").to_dicts()
    retained = df.filter(pl.col("reporting_leg_role") == "retained").to_dicts()
    assert len(guaranteed) == 1, f"expected one __G_ leg, got {len(guaranteed)}"
    assert len(retained) == 1, f"expected one __REM leg, got {len(retained)}"
    return guaranteed[0], retained[0]


class TestGuaranteeRwaBenefitCRR:
    """CRR: benefit = 1,000,000 x (1.50 - 1.00) = 500,000."""

    @pytest.fixture(scope="class")
    def results(self) -> pl.DataFrame:
        return _run(
            CalculationConfig.crr(
                reporting_date=date(2025, 12, 31),
                permission_mode=PermissionMode.STANDARDISED,
            )
        )

    def test_guaranteed_leg_benefit(self, results: pl.DataFrame) -> None:
        guaranteed, _ = _legs(results)
        assert guaranteed["guarantee_rwa_benefit"] == pytest.approx(_EXPECTED_BENEFIT_CRR)

    def test_benefit_is_ead_times_rw_delta(self, results: pl.DataFrame) -> None:
        """The sealed figure ties to the sealed ingredients on the same leg."""
        guaranteed, _ = _legs(results)
        expected = guaranteed["ead_final"] * (
            guaranteed["pre_crm_risk_weight"] - guaranteed["risk_weight"]
        )
        assert guaranteed["guarantee_rwa_benefit"] == pytest.approx(expected)

    def test_retained_leg_benefit_is_zero(self, results: pl.DataFrame) -> None:
        _, retained = _legs(results)
        assert retained["guarantee_rwa_benefit"] == pytest.approx(0.0)

    def test_exposure_sum_ties_to_whole_relief(self, results: pl.DataFrame) -> None:
        total = float(results["guarantee_rwa_benefit"].fill_null(0.0).sum())
        assert total == pytest.approx(_EXPECTED_BENEFIT_CRR)


class TestGuaranteeRwaBenefitB31:
    """B31: benefit = 1,000,000 x (1.50 - 0.75) = 750,000."""

    @pytest.fixture(scope="class")
    def results(self) -> pl.DataFrame:
        return _run(
            CalculationConfig.basel_3_1(
                reporting_date=date(2027, 12, 31),
                permission_mode=PermissionMode.STANDARDISED,
            )
        )

    def test_guaranteed_leg_benefit(self, results: pl.DataFrame) -> None:
        guaranteed, _ = _legs(results)
        assert guaranteed["guarantee_rwa_benefit"] == pytest.approx(_EXPECTED_BENEFIT_B31)

    def test_exposure_sum_ties_to_whole_relief(self, results: pl.DataFrame) -> None:
        total = float(results["guarantee_rwa_benefit"].fill_null(0.0).sum())
        assert total == pytest.approx(_EXPECTED_BENEFIT_B31)
