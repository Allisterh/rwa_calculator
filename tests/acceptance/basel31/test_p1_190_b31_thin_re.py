"""
P1.190 Basel 3.1 — F-IRB Foundation Collateral Method (Art. 230): b31_thin_re.

Scenario: £250k RRE collateral against £10m senior corporate exposure.
Coverage is thin (2.5% of EAD) — after HC=40%, effective secured portion
is tiny, so LGD* ≈ LGDU * unsecured_fraction + LGDS * secured_fraction.

Bugs being tested:
  (a) C* threshold (30%) must NOT apply under Basel 3.1. Pre-fix engine uses
      CRR C* gate, which zeros the collateral because £250k < 30% of £10m EAD.
      Post-fix: B31 has no C* threshold → thin coverage still recognised.
  (b) OC divisor must be 1.0 (not 1.4×) for non-financial under Basel 3.1.
  (c) HC for real_estate must be 0.40 (not 0.00) under Basel 3.1.

Hand-calculation (PS1/26 Art. 230(1), LGDU=40%, LGDS=20%, HC=40%):
    EAD                  = 10,000,000.00
    MV                   = 250,000.00
    HC                   = 0.40  (Art. 230(2) immovable property)
    Hfx                  = 0.00  (GBP/GBP)
    C_adjusted           = 250,000 × (1 - 0.40 - 0.00) = 150,000.00
    OC_ratio             = 1.0   (B31: no divisor for non-financial)
    ES                   = min(150,000 / 1.0, 10,000,000) = 150,000.00
    LGD*                 = 0.40 × (1 - 150,000/10,000,000) + 0.20 × (150,000/10,000,000)
                         = 0.40 × 0.985 + 0.20 × 0.015
                         = 0.3940 + 0.0030
                         = 0.3970

Expected:  lgd_floored == 0.3970 ± 1e-3
Anti-assert: lgd_floored != 0.4000 (= LGDU unsecured = bug (a) still active)

References:
    - PRA PS1/26 Art. 230(1): LGD* continuous formula
    - PRA PS1/26 Art. 230(2): HC table (40% immovable property), LGDS (20% RE)
    - PRA PS1/26 Art. 161(1)(aa): LGDU senior unsecured non-FSE corporate = 40%
    - IMPLEMENTATION_PLAN.md: P1.190 — b31_thin_re scenario
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from rwa_calc.contracts.bundles import RawDataBundle
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import PermissionMode
from rwa_calc.engine.pipeline import PipelineOrchestrator
from tests.fixtures.p1_190.p1_190 import (
    B31_THIN_RE_CP_REF,
    B31_THIN_RE_EXPECTED_LGD_STAR,
    B31_THIN_RE_FAC_REF,
    B31_THIN_RE_LOAN_REF,
    B31_THIN_RE_MODEL_ID,
    REPORTING_DATE,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "p1_190"
_SCENARIO = "b31_thin_re"

# Pre-fix value produced when bug (a) zeros thin collateral via C* gate
_PRE_FIX_LGD_BUG_A = 0.4000  # LGDU unsecured fallback

# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _run_pipeline() -> object:
    """Run Basel 3.1 F-IRB pipeline for the b31_thin_re scenario."""
    empty_mappings_lf = pl.LazyFrame(
        schema={
            "parent_counterparty_reference": pl.String,
            "child_counterparty_reference": pl.String,
        }
    )
    # Link the loan to its facility so facility-level collateral can flow
    # through to the loan exposure via the CRM facility lookup. Without this
    # mapping the loan's parent_facility_reference is null and the engine
    # cannot route the £250k RE pledge to the £10m loan.
    facility_mappings_lf = pl.LazyFrame(
        {
            "parent_facility_reference": [B31_THIN_RE_FAC_REF],
            "child_reference": [B31_THIN_RE_LOAN_REF],
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
    config = CalculationConfig.basel_3_1(
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


class TestP1190B31ThinRe:
    """
    P1.190 Basel 3.1 b31_thin_re: thin RE collateral with no C* gate.

    load-bearing: lgd_floored == 0.3970 ± 1e-3
    anti-assert:  lgd_floored != 0.4000 (LGDU = bug (a) C* gate still active)
    """

    @pytest.fixture(scope="class")
    def pipeline_result(self):
        """Run Basel 3.1 F-IRB pipeline for b31_thin_re and cache."""
        return _run_pipeline()

    @pytest.fixture(scope="class")
    def loan_rows(self, pipeline_result) -> list[dict]:
        """All result rows for the thin-RE loan."""
        rows = _find_loan_rows(pipeline_result, B31_THIN_RE_LOAN_REF)
        assert rows, (
            f"P1.190 b31_thin_re: no pipeline result rows for loan_ref='{B31_THIN_RE_LOAN_REF}'. "
            f"Counterparty {B31_THIN_RE_CP_REF} must be routed to F-IRB via "
            f"model_id='{B31_THIN_RE_MODEL_ID}'."
        )
        return rows

    def test_p1_190_b31_thin_re_irb_routed(self, loan_rows: list[dict]) -> None:
        """
        P1.190 b31_thin_re: confirm F-IRB routing — pd_floored must be present.

        Arrange: Basel 3.1 pipeline, b31_thin_re scenario.
        Act:     inspect pipeline result rows for B31_THIN_RE_LOAN_REF.
        Assert:  pd_floored is not None (confirms IRB routing, not SA fallback).
        """
        # Arrange (rows from class fixture)
        pd_floored = _first(loan_rows, "pd_floored")

        # Assert
        assert pd_floored is not None, (
            f"P1.190 b31_thin_re: pd_floored not found — loan may have fallen back to SA. "
            f"Check model_permission_{_SCENARIO}.parquet routes '{B31_THIN_RE_MODEL_ID}' "
            f"to foundation_irb for exposure_class=corporate."
        )

    def test_p1_190_b31_thin_re_lgd_star_expected(self, loan_rows: list[dict]) -> None:
        """
        P1.190 b31_thin_re LOAD-BEARING: lgd_floored == 0.3970 ± 1e-3.

        Pre-fix engine applies CRR C* threshold (30% of EAD = £3m). Since MV=£250k
        is below this threshold, collateral is zeroed → LGD* = LGDU = 0.40.

        Post-fix (B31 has no C*): collateral is recognised → LGD* = 0.3970.

        Arrange: Basel 3.1 F-IRB, b31_thin_re, MV=£250k, EAD=£10m, HC=40%.
        Act:     full pipeline (PipelineOrchestrator.run_with_data).
        Assert:  lgd_floored == 0.3970 ± 1e-3.

        Pre-fix: lgd_floored == 0.4000 → AssertionError.
        """
        # Arrange
        lgd_floored = _first(loan_rows, "lgd_floored")

        # Assert presence
        assert lgd_floored is not None, (
            f"P1.190 b31_thin_re: lgd_floored not in result rows for '{B31_THIN_RE_LOAN_REF}'."
        )

        # Assert value
        assert lgd_floored == pytest.approx(B31_THIN_RE_EXPECTED_LGD_STAR, abs=1e-3), (
            f"P1.190 b31_thin_re: expected lgd_floored={B31_THIN_RE_EXPECTED_LGD_STAR:.4f} "
            f"(PS1/26 Art. 230: 0.40×0.985 + 0.20×0.015). "
            f"Got {lgd_floored:.6f}. "
            f"If == 0.4000: CRR C* gate is still being applied under Basel 3.1 (bug a). "
            f"Fix: gate the C* check on 'not is_basel_3_1'."
        )

    def test_p1_190_b31_thin_re_anti_assert_bug_a(self, loan_rows: list[dict]) -> None:
        """
        P1.190 b31_thin_re anti-assert: lgd_floored must NOT equal 0.4000.

        0.4000 == LGDU for Basel 3.1 senior unsecured corporate (Art. 161(1)(aa)).
        If the C* gate (bug a) is still active it zeros the £250k collateral and
        the blended LGD* collapses to LGDU = 0.40.

        Arrange: same as load-bearing test.
        Act:     full pipeline.
        Assert:  abs(lgd_floored - 0.4000) > 1e-3.
        """
        # Arrange
        lgd_floored = _first(loan_rows, "lgd_floored")
        if lgd_floored is None:
            pytest.skip("lgd_floored unavailable — routing issue")

        # Assert
        assert abs(lgd_floored - _PRE_FIX_LGD_BUG_A) > 1e-3, (
            f"P1.190 b31_thin_re regression: lgd_floored == {_PRE_FIX_LGD_BUG_A:.4f} "
            f"(LGDU unsecured = bug (a) CRR C* gate still active under Basel 3.1). "
            f"Expected lgd_floored ≈ {B31_THIN_RE_EXPECTED_LGD_STAR:.4f}."
        )
