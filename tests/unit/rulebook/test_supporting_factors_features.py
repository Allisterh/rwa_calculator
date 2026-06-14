"""
Pins for the S11 supporting-factors regime migration.

Phase 5 S11 moves the CRR Art. 501/501a supporting factors off
``config.supporting_factors`` onto the rulepack:

- the regime ON/OFF gate ``config.supporting_factors.enabled`` -> pack Feature
  ``supporting_factors`` (CRR enabled / Basel 3.1 disabled);
- the factor multipliers (SME 0.7619 / 0.85, infrastructure 0.75) -> pack
  FormulaParams ``supporting_factors_values``, keyed identically to
  ``contracts/config.py::SupportingFactors`` so the engine read is a 1:1
  byte-identical swap.

The FX-derived SME exposure THRESHOLD (``config.thresholds.sme_exposure_threshold``)
stays on config until S11c, so it is deliberately NOT covered here.

This pin is the byte-identical-parity contract: a pack typo fails here before
the engine behaviour and the 10k stress parity gate.

References:
- CRR Art. 501 / 501a: SME / infrastructure supporting factors.
- PRA PS1/26: supporting factors removed under Basel 3.1.
"""

from __future__ import annotations

from datetime import date

from rwa_calc.contracts.config import SupportingFactors
from rwa_calc.rulebook.resolve import resolve

_CRR_PACK = resolve("crr", date(2026, 1, 1))
_B31_PACK = resolve("b31", date(2027, 1, 1))

_VALUE_KEYS = (
    "sme_factor_under_threshold",
    "sme_factor_above_threshold",
    "infrastructure_factor",
)


def test_supporting_factors_feature_per_regime() -> None:
    # Arrange / Act / Assert
    assert _CRR_PACK.feature("supporting_factors") is True
    assert _B31_PACK.feature("supporting_factors") is False


def test_supporting_factors_values_crr_match_config() -> None:
    params = _CRR_PACK.formula("supporting_factors_values").params
    cfg = SupportingFactors.crr()
    for key in _VALUE_KEYS:
        assert params[key] == getattr(cfg, key)


def test_supporting_factors_values_b31_match_config() -> None:
    params = _B31_PACK.formula("supporting_factors_values").params
    cfg = SupportingFactors.basel_3_1()
    for key in _VALUE_KEYS:
        assert params[key] == getattr(cfg, key)
