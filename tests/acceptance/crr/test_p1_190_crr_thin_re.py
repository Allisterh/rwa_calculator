"""
P1.190 CRR mirror — F-IRB Foundation Collateral Method (Art. 230): crr_thin_re.

Scenario: £250k RRE collateral against £10m senior corporate exposure under CRR.
Coverage is thin (2.5% of EAD). Under CRR Art. 230, the C* threshold = 30% of EAD
= £3m. Since MV=£250k < C* the collateral is zeroed → LGD* = LGDU = 0.45.

Regression purpose: confirms the CRR path is NOT affected by the Basel 3.1 fixes.
After bugs (a)/(b)/(c) are fixed for B31, the CRR path must still zero thin
collateral via the C* gate and return LGDU=0.45 (not 0.3970 which is the B31 value).

Hand-calculation (CRR Art. 230, LGDU=45%, C* = 30%×EAD):
    EAD            = 10,000,000.00
    MV             = 250,000.00
    C*             = 0.30 × 10,000,000 = 3,000,000.00
    MV < C*?       YES (250,000 < 3,000,000) → collateral zeroed
    ES             = 0.00
    LGD*           = LGDU × 1.0 + LGDS × 0.0 = 0.45

Expected:  lgd_floored == 0.4500 ± 1e-3
Anti-assert: lgd_floored != 0.3970 (= B31 thin_re value — CRR must not inherit B31 formula)

References:
    - CRR Art. 230(2): C* threshold = 30% of E for real estate
    - CRR Art. 161(1)(a): LGDU senior unsecured corporate non-FSE = 45%
    - CRR Art. 230 Table 5: LGDS RE senior = 35%, OC = 1.4x
    - IMPLEMENTATION_PLAN.md: P1.190 — crr_thin_re scenario (CRR mirror)
"""

from __future__ import annotations

import pytest
from tests.acceptance.p1_190_pipeline_helpers import build_p1_190_bundle, find_loan_rows, first
from tests.fixtures.p1_190.p1_190 import (
    B31_THIN_RE_EXPECTED_LGD_STAR,
    CRR_THIN_RE_CP_REF,
    CRR_THIN_RE_EXPECTED_LGD_STAR,
    CRR_THIN_RE_FAC_REF,
    CRR_THIN_RE_LOAN_REF,
    CRR_THIN_RE_MODEL_ID,
    REPORTING_DATE,
)

from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import PermissionMode
from rwa_calc.engine.pipeline import PipelineOrchestrator

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_SCENARIO = "crr_thin_re"

# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _run_pipeline() -> object:
    """Run CRR F-IRB pipeline for the crr_thin_re scenario."""
    bundle = build_p1_190_bundle(_SCENARIO, CRR_THIN_RE_FAC_REF, CRR_THIN_RE_LOAN_REF)
    config = CalculationConfig.crr(
        reporting_date=REPORTING_DATE,
        permission_mode=PermissionMode.IRB,
    )
    return PipelineOrchestrator().run_with_data(bundle, config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestP1190CrrThinRe:
    """
    P1.190 CRR mirror crr_thin_re: C* gate zeros thin collateral → LGDU=0.45.

    load-bearing: lgd_floored == 0.4500 ± 1e-3
    anti-assert:  lgd_floored != 0.3970 (B31 thin_re value — CRR must not inherit B31 formula)
    """

    @pytest.fixture(scope="class")
    def pipeline_result(self):
        """Run CRR F-IRB pipeline for crr_thin_re and cache."""
        return _run_pipeline()

    @pytest.fixture(scope="class")
    def loan_rows(self, pipeline_result) -> list[dict]:
        """All result rows for the CRR thin-RE loan."""
        rows = find_loan_rows(pipeline_result, CRR_THIN_RE_LOAN_REF)
        assert rows, (
            f"P1.190 crr_thin_re: no pipeline result rows for "
            f"loan_ref='{CRR_THIN_RE_LOAN_REF}'. "
            f"Counterparty {CRR_THIN_RE_CP_REF} must be routed to F-IRB via "
            f"model_id='{CRR_THIN_RE_MODEL_ID}'."
        )
        return rows

    def test_p1_190_crr_thin_re_irb_routed(self, loan_rows: list[dict]) -> None:
        """
        P1.190 crr_thin_re: confirm F-IRB routing — pd_floored must be present.

        Arrange: CRR pipeline, crr_thin_re scenario.
        Act:     inspect pipeline result rows for CRR_THIN_RE_LOAN_REF.
        Assert:  pd_floored is not None.
        """
        pd_floored = first(loan_rows, "pd_floored")
        assert pd_floored is not None, (
            f"P1.190 crr_thin_re: pd_floored not found — loan may have fallen back to SA. "
            f"Check model_permission_{_SCENARIO}.parquet."
        )

    def test_p1_190_crr_thin_re_lgd_star_expected(self, loan_rows: list[dict]) -> None:
        """
        P1.190 crr_thin_re LOAD-BEARING: lgd_floored == 0.4500 ± 1e-3.

        Under CRR Art. 230 the C* threshold (30% of EAD = £3m) zeros collateral when
        MV < C*. Since MV=£250k < £3m, effective collateral = 0, LGD* = LGDU = 0.45.

        This test verifies the CRR C* gate still works correctly after the B31 fixes.
        After bug (a) fix the gate must only apply when is_basel_3_1=False.

        Arrange: CRR F-IRB, crr_thin_re, MV=£250k, EAD=£10m.
        Act:     full pipeline with CalculationConfig.crr().
        Assert:  lgd_floored == 0.4500 ± 1e-3.

        Pre-fix (before P1.190 bugs fixed): CRR path already produces 0.45
        via C* gate, so this test may already PASS — it is a regression guard.
        If the test fails it means bug (a) fix broke the CRR path.
        """
        lgd_floored = first(loan_rows, "lgd_floored")

        assert lgd_floored is not None, (
            f"P1.190 crr_thin_re: lgd_floored not in result rows for '{CRR_THIN_RE_LOAN_REF}'."
        )

        assert lgd_floored == pytest.approx(CRR_THIN_RE_EXPECTED_LGD_STAR, abs=1e-3), (
            f"P1.190 crr_thin_re: expected lgd_floored={CRR_THIN_RE_EXPECTED_LGD_STAR:.4f} "
            f"(CRR Art. 230: C* gate zeros MV=£250k < 30%×EAD=£3m; LGDU=0.45). "
            f"Got {lgd_floored:.6f}. "
            f"If ≈ 0.3970 (B31 value): the bug (a) fix has accidentally removed the "
            f"CRR C* gate. The gate must remain gated on 'not is_basel_3_1'."
        )

    def test_p1_190_crr_thin_re_anti_assert_b31_value(self, loan_rows: list[dict]) -> None:
        """
        P1.190 crr_thin_re anti-assert: lgd_floored must NOT equal 0.3970.

        0.3970 == B31_THIN_RE_EXPECTED_LGD_STAR — the Basel 3.1 value for the
        same scenario. If the CRR path returns this value, the bug (a) fix
        has incorrectly disabled the C* gate for the CRR framework.

        Arrange: same as load-bearing test.
        Act:     full pipeline with CRR config.
        Assert:  abs(lgd_floored - 0.3970) > 1e-3.
        """
        lgd_floored = first(loan_rows, "lgd_floored")
        if lgd_floored is None:
            pytest.skip("lgd_floored unavailable — routing issue")

        assert abs(lgd_floored - B31_THIN_RE_EXPECTED_LGD_STAR) > 1e-3, (
            f"P1.190 crr_thin_re regression: lgd_floored == {B31_THIN_RE_EXPECTED_LGD_STAR:.4f} "
            f"(the Basel 3.1 thin_re value — CRR must not inherit B31 formula). "
            f"The C* gate must remain active for CRR. Got {lgd_floored:.6f}."
        )
