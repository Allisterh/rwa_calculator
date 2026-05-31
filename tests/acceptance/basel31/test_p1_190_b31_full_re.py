"""
P1.190 Basel 3.1 — F-IRB Foundation Collateral Method (Art. 230): b31_full_re.

Scenario: £10m RRE collateral against £10m senior corporate exposure.
Coverage is 100% of EAD — fully secured scenario.

Bugs being tested:
  (b) OC divisor must be 1.0 (not 1.4×) for non-financial under Basel 3.1.
  (c) HC for real_estate must be 0.40 (not 0.00) under Basel 3.1.

Hand-calculation (PS1/26 Art. 230(1), LGDU=40%, LGDS=20%, HC=40%):
    EAD                  = 10,000,000.00
    MV                   = 10,000,000.00
    HC                   = 0.40  (Art. 230(2) immovable property)
    Hfx                  = 0.00  (GBP/GBP)
    C_adjusted           = 10,000,000 × (1 - 0.40 - 0.00) = 6,000,000.00
    OC_ratio             = 1.0   (B31: no divisor for non-financial)
    ES                   = min(6,000,000 / 1.0, 10,000,000) = 6,000,000.00
    secured_fraction     = 6,000,000 / 10,000,000 = 0.60
    unsecured_fraction   = 1 - 0.60 = 0.40
    LGD*                 = 0.40 × 0.40 + 0.20 × 0.60
                         = 0.1600 + 0.1200
                         = 0.2800

Expected:  lgd_floored == 0.2800 ± 1e-3
Anti-assert: lgd_floored != 0.2571 (= pre-fix bugs (b)+(c) compounding)

Pre-fix compound effect:
  - HC=0.00: C_adjusted = 10,000,000 (no HC reduction)
  - OC_ratio=1.4: ES = 10,000,000 / 1.4 = 7,142,857
  - secured_fraction = 7,142,857 / 10,000,000 = 0.7143
  - LGD* = 0.40 × 0.2857 + 0.20 × 0.7143 = 0.1143 + 0.1429 = 0.2571

References:
    - PRA PS1/26 Art. 230(1): LGD* continuous formula
    - PRA PS1/26 Art. 230(2): HC table (40% immovable property), LGDS (20% RE)
    - PRA PS1/26 Art. 161(1)(aa): LGDU senior unsecured non-FSE corporate = 40%
    - IMPLEMENTATION_PLAN.md: P1.190 — b31_full_re scenario
"""

from __future__ import annotations

import pytest

from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import PermissionMode
from rwa_calc.engine.pipeline import PipelineOrchestrator
from tests.acceptance.p1_190_pipeline_helpers import build_p1_190_bundle, find_loan_rows, first
from tests.fixtures.p1_190.p1_190 import (
    B31_FULL_RE_CP_REF,
    B31_FULL_RE_EXPECTED_LGD_STAR,
    B31_FULL_RE_FAC_REF,
    B31_FULL_RE_LOAN_REF,
    B31_FULL_RE_MODEL_ID,
    REPORTING_DATE,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_SCENARIO = "b31_full_re"

# Pre-fix value: bugs (b) HC=0.00 + (c) OC=1.4x compound to give 0.2571
_PRE_FIX_LGD_BUGS_BC = 0.2571

# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _run_pipeline() -> object:
    """Run Basel 3.1 F-IRB pipeline for the b31_full_re scenario."""
    bundle = build_p1_190_bundle(_SCENARIO, B31_FULL_RE_FAC_REF, B31_FULL_RE_LOAN_REF)
    config = CalculationConfig.basel_3_1(
        reporting_date=REPORTING_DATE,
        permission_mode=PermissionMode.IRB,
    )
    return PipelineOrchestrator().run_with_data(bundle, config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestP1190B31FullRe:
    """
    P1.190 Basel 3.1 b31_full_re: fully-covered RE collateral with corrected HC and OC.

    load-bearing: lgd_floored == 0.2800 ± 1e-3
    anti-assert:  lgd_floored != 0.2571 (bugs (b)+(c) compound pre-fix value)
    """

    @pytest.fixture(scope="class")
    def pipeline_result(self):
        """Run Basel 3.1 F-IRB pipeline for b31_full_re and cache."""
        return _run_pipeline()

    @pytest.fixture(scope="class")
    def loan_rows(self, pipeline_result) -> list[dict]:
        """All result rows for the full-RE loan."""
        rows = find_loan_rows(pipeline_result, B31_FULL_RE_LOAN_REF)
        assert rows, (
            f"P1.190 b31_full_re: no pipeline result rows for loan_ref='{B31_FULL_RE_LOAN_REF}'. "
            f"Counterparty {B31_FULL_RE_CP_REF} must be routed to F-IRB via "
            f"model_id='{B31_FULL_RE_MODEL_ID}'."
        )
        return rows

    def test_p1_190_b31_full_re_irb_routed(self, loan_rows: list[dict]) -> None:
        """
        P1.190 b31_full_re: confirm F-IRB routing — pd_floored must be present.

        Arrange: Basel 3.1 pipeline, b31_full_re scenario.
        Act:     inspect pipeline result rows for B31_FULL_RE_LOAN_REF.
        Assert:  pd_floored is not None.
        """
        pd_floored = first(loan_rows, "pd_floored")
        assert pd_floored is not None, (
            f"P1.190 b31_full_re: pd_floored not found — loan may have fallen back to SA. "
            f"Check model_permission_{_SCENARIO}.parquet."
        )

    def test_p1_190_b31_full_re_lgd_star_expected(self, loan_rows: list[dict]) -> None:
        """
        P1.190 b31_full_re LOAD-BEARING: lgd_floored == 0.2800 ± 1e-3.

        Pre-fix bugs (b) and (c) compound:
          - bug (c): HC=0.00 instead of 0.40 → C_adjusted = 10m (too high)
          - bug (b): OC_ratio=1.4 → ES = 10m/1.4 = 7.143m (too high)
          → LGD* = 0.2571 (overstates secured portion, understates LGD*)

        Post-fix (HC=0.40, OC_ratio=1.0):
          C_adjusted = 6m, ES = 6m, LGD* = 0.2800.

        Arrange: Basel 3.1 F-IRB, b31_full_re, MV=£10m, EAD=£10m, HC=0.40.
        Act:     full pipeline.
        Assert:  lgd_floored == 0.2800 ± 1e-3.

        Pre-fix: lgd_floored ≈ 0.2571 → AssertionError.
        """
        lgd_floored = first(loan_rows, "lgd_floored")

        assert lgd_floored is not None, (
            f"P1.190 b31_full_re: lgd_floored not in result rows for '{B31_FULL_RE_LOAN_REF}'."
        )

        assert lgd_floored == pytest.approx(B31_FULL_RE_EXPECTED_LGD_STAR, abs=1e-3), (
            f"P1.190 b31_full_re: expected lgd_floored={B31_FULL_RE_EXPECTED_LGD_STAR:.4f} "
            f"(PS1/26 Art. 230: 0.40×0.40 + 0.20×0.60). "
            f"Got {lgd_floored:.6f}. "
            f"If ≈ 0.2571: bugs (b)+(c) still compound — HC=0 and OC=1.4× both active."
        )

    def test_p1_190_b31_full_re_anti_assert_bugs_bc(self, loan_rows: list[dict]) -> None:
        """
        P1.190 b31_full_re anti-assert: lgd_floored must NOT equal 0.2571.

        0.2571 is the pre-fix value when both bug (b) (OC=1.4×) and bug (c)
        (HC=0.00) are active, producing ES=7.143m instead of ES=6m.

        Arrange: same as load-bearing test.
        Act:     full pipeline.
        Assert:  abs(lgd_floored - 0.2571) > 1e-3.
        """
        lgd_floored = first(loan_rows, "lgd_floored")
        if lgd_floored is None:
            pytest.skip("lgd_floored unavailable — routing issue")

        assert abs(lgd_floored - _PRE_FIX_LGD_BUGS_BC) > 1e-3, (
            f"P1.190 b31_full_re regression: lgd_floored == {_PRE_FIX_LGD_BUGS_BC:.4f} "
            f"(pre-fix: bugs (b)+(c) both active). "
            f"Expected lgd_floored ≈ {B31_FULL_RE_EXPECTED_LGD_STAR:.4f}."
        )
