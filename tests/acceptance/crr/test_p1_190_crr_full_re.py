"""
P1.190 CRR mirror — F-IRB Foundation Collateral Method (Art. 230): crr_full_re.

Scenario: £10m RRE collateral against £10m senior corporate exposure under CRR.
Coverage is 100% of EAD. Under CRR Art. 230, MV=£10m >= C* (30% × £10m = £3m),
so collateral is recognised. OC ratio for RE = 1.4× (Art. 230 Table 5).

Regression purpose: confirms the CRR OC ratio (1.4×) remains in force after
the Basel 3.1 fixes. After bug (b) is fixed for B31, the CRR path must still
use OC=1.4× (not OC=1.0) and return the CRR-specific LGD*.

Hand-calculation (CRR Art. 230, LGDU=45%, LGDS=35%, OC=1.4×, HC=0):
    EAD            = 10,000,000.00
    MV             = 10,000,000.00
    HC             = 0.00  (CRR Art. 230 has no HC for non-financial collateral)
    Hfx            = 0.00  (GBP/GBP)
    C_adjusted     = 10,000,000 × (1 - 0 - 0) = 10,000,000.00
    OC_ratio       = 1.4   (CRR Art. 230 Table 5: RE senior)
    ES             = min(10,000,000 / 1.4, 10,000,000) = 7,142,857.14
    secured_frac   = 7,142,857.14 / 10,000,000 = 0.714286
    unsecured_frac = 1 - 0.714286 = 0.285714
    LGD*           = 0.45 × 0.285714 + 0.35 × 0.714286
                   = 0.128571 + 0.250000
                   = 0.378571

Expected:  lgd_floored == 0.378571 ± 1e-3
Anti-assert: lgd_floored != 0.2800 (= B31 full_re value — CRR must not inherit B31 formula)

References:
    - CRR Art. 230(2): C* threshold = 30% of E for real estate
    - CRR Art. 230 Table 5: RE senior LGDS=35%, OC=1.4x
    - CRR Art. 161(1)(a): LGDU senior unsecured corporate non-FSE = 45%
    - IMPLEMENTATION_PLAN.md: P1.190 — crr_full_re scenario (CRR mirror)
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from tests.fixtures.p1_190.p1_190 import (
    B31_FULL_RE_EXPECTED_LGD_STAR,
    CRR_FULL_RE_CP_REF,
    CRR_FULL_RE_EXPECTED_LGD_STAR,
    CRR_FULL_RE_FAC_REF,
    CRR_FULL_RE_LOAN_REF,
    CRR_FULL_RE_MODEL_ID,
    REPORTING_DATE,
)

from rwa_calc.contracts.bundles import RawDataBundle
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import PermissionMode
from rwa_calc.engine.pipeline import PipelineOrchestrator

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "p1_190"
_SCENARIO = "crr_full_re"

# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _run_pipeline() -> object:
    """Run CRR F-IRB pipeline for the crr_full_re scenario."""
    empty_mappings_lf = pl.LazyFrame(
        schema={
            "parent_counterparty_reference": pl.String,
            "child_counterparty_reference": pl.String,
        }
    )
    # Link the loan to its facility so facility-level collateral flows through
    # to the loan exposure via the CRM facility lookup.
    facility_mappings_lf = pl.LazyFrame(
        {
            "parent_facility_reference": [CRR_FULL_RE_FAC_REF],
            "child_reference": [CRR_FULL_RE_LOAN_REF],
            "child_type": ["loan"],
        },
        schema={
            "parent_facility_reference": pl.String,
            "child_reference": pl.String,
            "child_type": pl.String,
        },
    )

    bundle = RawDataBundle(
        facilities=pl.scan_parquet(_FIXTURES_DIR / f"facility_{_SCENARIO}.parquet"),
        loans=pl.scan_parquet(_FIXTURES_DIR / f"loan_{_SCENARIO}.parquet"),
        counterparties=pl.scan_parquet(_FIXTURES_DIR / f"counterparty_{_SCENARIO}.parquet"),
        collateral=pl.scan_parquet(_FIXTURES_DIR / f"collateral_{_SCENARIO}.parquet"),
        ratings=pl.scan_parquet(_FIXTURES_DIR / f"rating_{_SCENARIO}.parquet"),
        model_permissions=pl.scan_parquet(_FIXTURES_DIR / f"model_permission_{_SCENARIO}.parquet"),
        facility_mappings=facility_mappings_lf,
        lending_mappings=empty_mappings_lf,
    )
    config = CalculationConfig.crr(
        reporting_date=REPORTING_DATE,
        permission_mode=PermissionMode.IRB,
    )
    return PipelineOrchestrator().run_with_data(bundle, config)


def _find_loan_rows(results: object, loan_ref: str) -> list[dict]:
    """Return all result rows containing loan_ref in exposure_reference."""
    rows: list[dict] = []
    for lf in [results.sa_results, results.irb_results, results.slotting_results]:
        if lf is None:
            continue
        df = lf.filter(pl.col("exposure_reference").str.contains(loan_ref)).collect()
        rows.extend(df.to_dicts())
    return rows


def _first(rows: list[dict], field: str):
    """Return the first non-null value of field from the result rows."""
    for r in rows:
        v = r.get(field)
        if v is not None:
            return v
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestP1190CrrFullRe:
    """
    P1.190 CRR mirror crr_full_re: fully-covered RE with CRR OC=1.4× and LGDU=45%.

    load-bearing: lgd_floored == 0.378571 ± 1e-3
    anti-assert:  lgd_floored != 0.2800 (B31 full_re value — CRR must not inherit B31 formula)
    """

    @pytest.fixture(scope="class")
    def pipeline_result(self):
        """Run CRR F-IRB pipeline for crr_full_re and cache."""
        return _run_pipeline()

    @pytest.fixture(scope="class")
    def loan_rows(self, pipeline_result) -> list[dict]:
        """All result rows for the CRR full-RE loan."""
        rows = _find_loan_rows(pipeline_result, CRR_FULL_RE_LOAN_REF)
        assert rows, (
            f"P1.190 crr_full_re: no pipeline result rows for "
            f"loan_ref='{CRR_FULL_RE_LOAN_REF}'. "
            f"Counterparty {CRR_FULL_RE_CP_REF} must be routed to F-IRB via "
            f"model_id='{CRR_FULL_RE_MODEL_ID}'."
        )
        return rows

    def test_p1_190_crr_full_re_irb_routed(self, loan_rows: list[dict]) -> None:
        """
        P1.190 crr_full_re: confirm F-IRB routing — pd_floored must be present.

        Arrange: CRR pipeline, crr_full_re scenario.
        Act:     inspect pipeline result rows for CRR_FULL_RE_LOAN_REF.
        Assert:  pd_floored is not None.
        """
        pd_floored = _first(loan_rows, "pd_floored")
        assert pd_floored is not None, (
            f"P1.190 crr_full_re: pd_floored not found — loan may have fallen back to SA. "
            f"Check model_permission_{_SCENARIO}.parquet."
        )

    def test_p1_190_crr_full_re_lgd_star_expected(self, loan_rows: list[dict]) -> None:
        """
        P1.190 crr_full_re LOAD-BEARING: lgd_floored == 0.378571 ± 1e-3.

        Under CRR Art. 230: HC=0, OC=1.4×, LGDS=35%, LGDU=45%.
          ES = 10m / 1.4 = 7.143m
          LGD* = 0.45 × 0.2857 + 0.35 × 0.7143 = 0.378571

        This test verifies the CRR OC ratio (1.4×) remains in force after the B31 fixes.
        After bug (b) fix for B31, the CRR path must still use OC=1.4×.

        Arrange: CRR F-IRB, crr_full_re, MV=£10m, EAD=£10m.
        Act:     full pipeline with CalculationConfig.crr().
        Assert:  lgd_floored == 0.378571 ± 1e-3.
        """
        lgd_floored = _first(loan_rows, "lgd_floored")

        assert lgd_floored is not None, (
            f"P1.190 crr_full_re: lgd_floored not in result rows for '{CRR_FULL_RE_LOAN_REF}'."
        )

        assert lgd_floored == pytest.approx(CRR_FULL_RE_EXPECTED_LGD_STAR, abs=1e-3), (
            f"P1.190 crr_full_re: expected lgd_floored={CRR_FULL_RE_EXPECTED_LGD_STAR:.6f} "
            f"(CRR Art. 230: HC=0, OC=1.4×, ES=7.143m, 0.45×0.286 + 0.35×0.714). "
            f"Got {lgd_floored:.6f}. "
            f"If ≈ 0.2800 (B31 value): the bug (b)/(c) fix has broken the CRR path — "
            f"CRR must still use OC=1.4× for real estate collateral."
        )

    def test_p1_190_crr_full_re_anti_assert_b31_value(self, loan_rows: list[dict]) -> None:
        """
        P1.190 crr_full_re anti-assert: lgd_floored must NOT equal 0.2800.

        0.2800 == B31_FULL_RE_EXPECTED_LGD_STAR — the Basel 3.1 value for the
        same scenario. If the CRR path returns this value, the bug (b) or (c) fix
        has incorrectly changed the CRR path (OC=1.4× removed, or HC=0.40 applied).

        Arrange: same as load-bearing test.
        Act:     full pipeline with CRR config.
        Assert:  abs(lgd_floored - 0.2800) > 1e-3.
        """
        lgd_floored = _first(loan_rows, "lgd_floored")
        if lgd_floored is None:
            pytest.skip("lgd_floored unavailable — routing issue")

        assert abs(lgd_floored - B31_FULL_RE_EXPECTED_LGD_STAR) > 1e-3, (
            f"P1.190 crr_full_re regression: lgd_floored == {B31_FULL_RE_EXPECTED_LGD_STAR:.4f} "
            f"(the Basel 3.1 full_re value — CRR must not inherit B31 OC=1.0 / HC=0.40). "
            f"CRR must use OC=1.4× and HC=0. Got {lgd_floored:.6f}."
        )
