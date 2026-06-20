"""
SFT/FCCM separation Phase 7b — FCCM SFT reporting reclassification.

Pipeline position:
    raw.sft -> sft_fccm stage -> result.results
        -> COREPGenerator (C 07.00 row 0090 / C 34) + Pillar3Generator (CCR1/CCR8)

Key responsibilities (operator decision Q2):
- Prove FCCM SFT EAD is reported under COREP C 07.00 row 0090 ("SFT netting
  sets", PS1/26 App. 17) — NOT the SA-CCR templates (C 34.01/02/08, Pillar 3
  CCR1/CCR8). The synthetic SFT row carries risk_type == "CCR_SFT".
- Prove the reclassification conserves EAD: the SFT EAD appears in C 07.00 row
  0090 and is ABSENT from C 34 / CCR1 — moved without loss or duplication.

The reporting golden oracle (tests/fixtures/reporting_portfolio.py) is loan-only
and carries no CCR/SFT rows, so this focused test supplies its own minimal
SFT-bearing portfolio rather than perturbing the 95 frozen reporting goldens.

References:
    - PS1/26 App. 17: COREP C 07.00 row 0090 — SFT netting sets.
    - CRR Art. 271(2), 220-223: FCCM SFT EAD.
    - CRR Art. 274/306: SA-CCR / CCP exposures report under C 34 (not SFTs).
    - tests/fixtures/ccr/golden_ccr_a11_a12.py: shared SFT scenario constants.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import polars as pl
import pytest
from tests.fixtures.ccr.golden_ccr_a11_a12 import (
    CCR_A11_A12_EXPOSURE_CLASS_SA,
    build_raw_data_bundle_ccr_a11,
)

from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import PermissionMode
from rwa_calc.engine.pipeline import PipelineOrchestrator
from rwa_calc.reporting.corep.generator import COREPGenerator, COREPTemplateBundle
from rwa_calc.reporting.pillar3.generator import Pillar3Generator, Pillar3TemplateBundle

_REL_TOL = 1e-6


def _crr_config() -> CalculationConfig:
    return CalculationConfig.crr(
        reporting_date=date(2025, 12, 31), permission_mode=PermissionMode.STANDARDISED
    )


def _b31_config() -> CalculationConfig:
    return CalculationConfig.basel_3_1(
        reporting_date=date(2030, 1, 1), permission_mode=PermissionMode.STANDARDISED
    )


# regime key -> (framework string, config factory)
_REGIMES: dict[str, tuple[str, Callable[[], CalculationConfig]]] = {
    "crr": ("CRR", _crr_config),
    "b31": ("BASEL_3_1", _b31_config),
}


def _run(
    regime_key: str,
) -> tuple[pl.DataFrame, COREPTemplateBundle, Pillar3TemplateBundle]:
    """Run the uncollateralised FCCM SFT portfolio through one regime."""
    framework, config_factory = _REGIMES[regime_key]
    result = PipelineOrchestrator().run_with_data(build_raw_data_bundle_ccr_a11(), config_factory())
    results_df = result.results.collect()
    corep = COREPGenerator().generate_from_lazyframe(result.results, framework=framework)
    pillar3 = Pillar3Generator().generate_from_lazyframe(result.results, framework=framework)
    return results_df, corep, pillar3


def _sft_ead(results_df: pl.DataFrame) -> float:
    """Total FCCM SFT EAD from the pipeline result frame."""
    return float(results_df.filter(pl.col("risk_type") == "CCR_SFT")["ead_final"].sum())


@pytest.mark.parametrize("regime_key", list(_REGIMES))
class TestSFTReportedUnderC07Row0090:
    """FCCM SFT EAD reports under C 07.00 row 0090, not the SA-CCR templates."""

    def test_c07_row_0090_receives_sft_ead(self, regime_key: str) -> None:
        """
        C 07.00 row 0090 ("SFT netting sets") exposure value == the SFT EAD.

        Arrange: a single uncollateralised FCCM SFT (institution counterparty).
        Act:     run pipeline -> COREP generator.
        Assert:  the institution C 07.00 sheet's row 0090 col 0200
                 (exposure value) equals the pipeline SFT EAD.

        References:
            - PS1/26 App. 17: C 07.00 row 0090 — SFT netting sets.
        """
        # Arrange + Act
        results_df, corep, _ = _run(regime_key)
        sft_ead = _sft_ead(results_df)

        # Assert
        c07 = corep.c07_00.get(CCR_A11_A12_EXPOSURE_CLASS_SA)
        assert c07 is not None, (
            f"C 07.00 institution sheet must exist for the SFT class "
            f"({CCR_A11_A12_EXPOSURE_CLASS_SA!r})."
        )
        row_0090 = c07.filter(pl.col("row_ref") == "0090")
        assert row_0090.height == 1, "C 07.00 must carry exactly one row 0090."
        assert row_0090["0200"][0] == pytest.approx(sft_ead, rel=_REL_TOL), (
            f"C 07.00 row 0090 col 0200 (exposure value) must equal the FCCM SFT "
            f"EAD (expected ≈{sft_ead:,.2f}, got {row_0090['0200'][0]}). "
            "PS1/26 App. 17 reports SFTs under C 07.00 row 0090."
        )

    def test_sft_ead_absent_from_corep_c34(self, regime_key: str) -> None:
        """
        The SA-CCR COREP templates (C 34.01/02) are empty — SFT EAD left them.

        Arrange: a single FCCM SFT portfolio (no derivatives, no CCP).
        Act:     run pipeline -> COREP generator.
        Assert:  c34_01 is None and c34_02 == {} (no SA-CCR rows to report).

        References:
            - CRR Art. 274: C 34 reports SA-CCR derivatives, not FCCM SFTs.
        """
        # Arrange + Act
        _, corep, _ = _run(regime_key)

        # Assert
        assert corep.c34_01 is None, (
            "C 34.01 must be None for an SFT-only portfolio — the FCCM SFT EAD "
            "must leave the SA-CCR templates (Phase 7b)."
        )
        assert corep.c34_02 == {}, (
            "C 34.02 must be empty for an SFT-only portfolio — the FCCM SFT EAD "
            "must leave the SA-CCR per-netting-set template (Phase 7b)."
        )

    def test_sft_ead_absent_from_pillar3_ccr(self, regime_key: str) -> None:
        """
        The Pillar 3 CCR disclosure tables (CCR1/CCR8) are empty for an SFT book.

        Arrange: a single FCCM SFT portfolio.
        Act:     run pipeline -> Pillar 3 generator.
        Assert:  ccr1 is None and ccr8 is None (no SA-CCR / CCP rows).

        References:
            - CRR Art. 439: CCR1/CCR8 disclose derivatives / CCP, not FCCM SFTs.
        """
        # Arrange + Act
        _, _, pillar3 = _run(regime_key)

        # Assert
        assert pillar3.ccr1 is None, (
            "Pillar 3 CCR1 must be None for an SFT-only portfolio (Phase 7b)."
        )
        assert pillar3.ccr8 is None, (
            "Pillar 3 CCR8 must be None for an SFT-only portfolio (Phase 7b)."
        )

    def test_sft_ead_conserved_c34_to_c07(self, regime_key: str) -> None:
        """
        RECONCILIATION: the SFT EAD is in C 07.00 row 0090 AND absent from C 34.

        The move conserves EAD: it appears exactly once in the SA template
        (C 07.00 row 0090) and zero times in the SA-CCR template (C 34) — no
        loss, no duplication.

        Arrange: a single FCCM SFT portfolio.
        Act:     run pipeline -> COREP generator.
        Assert:  C 07.00 row 0090 col 0200 == SFT EAD, and the C 34 EAD == 0.
        """
        # Arrange + Act
        results_df, corep, _ = _run(regime_key)
        sft_ead = _sft_ead(results_df)
        assert sft_ead > 0.0, "Precondition: the SFT must carry a positive EAD."

        # Assert — present in C 07.00 row 0090
        c07 = corep.c07_00[CCR_A11_A12_EXPOSURE_CLASS_SA]
        c07_0090_ead = float(c07.filter(pl.col("row_ref") == "0090")["0200"][0])

        # Assert — absent from C 34 (None templates contribute 0 EAD)
        c34_ead = 0.0
        if corep.c34_01 is not None:
            c34_ead = float(corep.c34_01["0010"].fill_null(0.0).sum())

        assert c07_0090_ead == pytest.approx(sft_ead, rel=_REL_TOL), (
            f"Reconciliation: C 07.00 row 0090 must carry the full SFT EAD "
            f"(expected ≈{sft_ead:,.2f}, got {c07_0090_ead:,.2f})."
        )
        assert c34_ead == pytest.approx(0.0, abs=1e-6), (
            f"Reconciliation: the SA-CCR C 34 EAD must be 0 for an SFT-only "
            f"portfolio (got {c34_ead:,.2f}) — the SFT EAD must not be "
            "double-counted across C 07.00 and C 34."
        )
