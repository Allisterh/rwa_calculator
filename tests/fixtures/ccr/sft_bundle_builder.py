"""
SFT (FCCM) ``RawSFTBundle`` builders for the dark-launch SFT stage tests.

Pipeline position:
    fixture-builder output -> test-writer (tests/integration, tests/acceptance)
    -> engine SFT FCCM stage (engine/stages/sft.py)

SFT/FCCM separation Phase 5: the new ``sft_fccm`` stage reads
``RawDataBundle.sft`` (a :class:`RawSFTBundle`), whose lean shape differs from
the co-mingled :class:`RawCCRBundle` consumed by the legacy in-CCR path:

- ``counterparty_reference`` is denormalised onto the trade row (no separate
  netting-set table) — FCCM scope is single-trade single-counterparty netting
  sets (CRR Art. 220(1)(a)).
- every row is an SFT (no ``transaction_type`` discriminator).
- collateral is OPTIONAL (``RawSFTBundle.collateral is None`` for an
  uncollateralised SFT).

These builders deliberately reuse the CCR-A11 / CCR-A12 golden constants
(notional, counterparty, HE inputs, collateral) so the SFT stage's E* is
byte-identical to the legacy in-CCR FCCM result for the same trade — proving the
peer subsystem reproduces the regulatory math end-to-end.

The leaf frames are sealed through the SAME standard loader seal path
(``SFT_TABLE_EDGES`` / ``seal_lenient``) as production-loaded SFT files, so the
test bundle is shape-identical to a production load and satisfies the
``raw_sft_trades`` / ``raw_sft_collateral`` brands validated by the leaf
bundles' ``__post_init__``.

References:
- CRR Art. 220(1)(a), 223(5), 271(2) — FCCM SFT EAD.
- docs/plans/sft-fccm-separation.md (Phase 5 — peer stage / dark-launch).
- tests/fixtures/ccr/golden_ccr_a11_a12.py — shared scenario constants.
"""

from __future__ import annotations

import polars as pl

from rwa_calc.contracts.bundles import (
    RawSFTBundle,
    SftCollateralBundle,
    SftTradeBundle,
)
from rwa_calc.contracts.edges import SFT_TABLE_EDGES, seal_lenient
from rwa_calc.data.column_spec import dtypes_of
from rwa_calc.data.schemas import SFT_COLLATERAL_SCHEMA, SFT_TRADE_SCHEMA

from .golden_ccr_a11_a12 import (
    CCR_A11_A12_COUNTERPARTY_REF,
    CCR_A11_A12_CURRENCY,
    CCR_A11_A12_EXPOSURE_COLLATERAL_TYPE,
    CCR_A11_A12_EXPOSURE_SECURITY_CQS,
    CCR_A11_A12_EXPOSURE_SECURITY_RESIDUAL_MATURITY_YEARS,
    CCR_A11_A12_MATURITY_DATE,
    CCR_A11_A12_NOTIONAL,
    CCR_A11_A12_START_DATE,
    CCR_A11_NETTING_SET_ID,
    CCR_A11_TRADE_ID,
    CCR_A12_COLLATERAL_CURRENCY,
    CCR_A12_COLLATERAL_MARKET_VALUE,
    CCR_A12_COLLATERAL_REF,
    CCR_A12_COLLATERAL_TYPE,
    CCR_A12_NETTING_SET_ID,
    CCR_A12_TRADE_ID,
)

# SFT trade / netting-set identifiers for the dark-launch scenarios. Distinct
# from the CCR-A11/A12 ids so a future co-existence test can populate both
# raw.ccr and raw.sft without exposure_reference collisions.
SFT_DL_A11_TRADE_ID: str = "SFT_T_A11"
SFT_DL_A11_NETTING_SET_ID: str = "NS_SFT_DL_A11"
SFT_DL_A12_TRADE_ID: str = "SFT_T_A12"
SFT_DL_A12_NETTING_SET_ID: str = "NS_SFT_DL_A12"

SFT_DL_A11_EXPOSURE_REFERENCE: str = f"ccr__{SFT_DL_A11_NETTING_SET_ID}"
SFT_DL_A12_EXPOSURE_REFERENCE: str = f"ccr__{SFT_DL_A12_NETTING_SET_ID}"


def _seal_sft_trades(df: pl.DataFrame) -> pl.LazyFrame:
    """Seal an SFT trade frame exactly as the loader does (leniently)."""
    sealed, _missing = seal_lenient(df.lazy(), SFT_TABLE_EDGES["sft_trades"])
    return sealed


def _seal_sft_collateral(df: pl.DataFrame) -> pl.LazyFrame:
    """Seal an SFT collateral frame exactly as the loader does (leniently)."""
    sealed, _missing = seal_lenient(df.lazy(), SFT_TABLE_EDGES["sft_collateral"])
    return sealed


def _sft_trade_df(
    trade_id: str,
    netting_set_id: str,
    *,
    is_margined: bool = False,
    remargining_frequency_days: int = 1,
    mpor_floor_category: str = "repo_only",
    has_margin_dispute_doubling: bool = False,
    mpor_days_override: int | None = None,
) -> pl.DataFrame:
    """One-row SFT trade frame mirroring the CCR-A11/A12 corp-bond exposure.

    The Art. 285 margining columns (SFT/FCCM separation Phase 0b) default to the
    UNMARGINED branch, so the existing A11/A12 builders are unaffected. Pass the
    margining keywords to make a margined SFT representable (carry-only — the
    engine does not read these fields yet).
    """
    row = {
        "trade_id": trade_id,
        "netting_set_id": netting_set_id,
        "counterparty_reference": CCR_A11_A12_COUNTERPARTY_REF,
        "notional": CCR_A11_A12_NOTIONAL,
        "currency": CCR_A11_A12_CURRENCY,
        "maturity_date": CCR_A11_A12_MATURITY_DATE,
        "start_date": CCR_A11_A12_START_DATE,
        "exposure_collateral_type": CCR_A11_A12_EXPOSURE_COLLATERAL_TYPE,
        "exposure_security_cqs": CCR_A11_A12_EXPOSURE_SECURITY_CQS,
        "exposure_security_residual_maturity_years": (
            CCR_A11_A12_EXPOSURE_SECURITY_RESIDUAL_MATURITY_YEARS
        ),
        "is_margined": is_margined,
        "remargining_frequency_days": remargining_frequency_days,
        "mpor_floor_category": mpor_floor_category,
        "has_margin_dispute_doubling": has_margin_dispute_doubling,
        "mpor_days_override": mpor_days_override,
    }
    return pl.DataFrame([row], schema=dtypes_of(SFT_TRADE_SCHEMA))


def _sft_collateral_df(netting_set_id: str) -> pl.DataFrame:
    """One-row SFT collateral frame: GBP 60m cash (HC=0, HFX=0)."""
    row = {
        "sft_collateral_reference": CCR_A12_COLLATERAL_REF,
        "netting_set_id": netting_set_id,
        "collateral_type": CCR_A12_COLLATERAL_TYPE,
        "market_value": CCR_A12_COLLATERAL_MARKET_VALUE,
        "currency": CCR_A12_COLLATERAL_CURRENCY,
        "issuer_cqs": None,
        "residual_maturity_years": None,
    }
    return pl.DataFrame([row], schema=dtypes_of(SFT_COLLATERAL_SCHEMA))


def build_sft_bundle_a11() -> RawSFTBundle:
    """Uncollateralised SFT bundle (mirrors CCR-A11): E* = E·(1+HE), no collateral."""
    return RawSFTBundle(
        trades=SftTradeBundle(
            sft_trades=_seal_sft_trades(
                _sft_trade_df(SFT_DL_A11_TRADE_ID, SFT_DL_A11_NETTING_SET_ID)
            )
        ),
        collateral=None,
    )


def build_sft_bundle_a12() -> RawSFTBundle:
    """Cash-collateralised SFT bundle (mirrors CCR-A12): E* = E·(1+HE) − 60m."""
    return RawSFTBundle(
        trades=SftTradeBundle(
            sft_trades=_seal_sft_trades(
                _sft_trade_df(SFT_DL_A12_TRADE_ID, SFT_DL_A12_NETTING_SET_ID)
            )
        ),
        collateral=SftCollateralBundle(
            sft_collateral=_seal_sft_collateral(_sft_collateral_df(SFT_DL_A12_NETTING_SET_ID))
        ),
    )


def build_margined_sft_bundle(
    *,
    trade_id: str = "SFT_T_MARGINED",
    netting_set_id: str = "NS_SFT_MARGINED",
    remargining_frequency_days: int = 1,
    mpor_floor_category: str = "repo_only",
    has_margin_dispute_doubling: bool = False,
    mpor_days_override: int | None = None,
) -> RawSFTBundle:
    """A MARGINED SFT bundle carrying the Art. 285 MPOR inputs (Phase 0b).

    Mirrors the A11 corp-bond exposure but with ``is_margined=True`` and the
    supplied margin-period inputs denormalised onto the trade row. Carry-only:
    no engine math reads these fields yet, so this bundle's E* is identical to
    the unmargined A11 result — the fields exist to make a margined SFT
    representable for the math phases that follow.

    References:
        - CRR Art. 285(2)-(5) — MPOR floors / derivation
        - CRR Art. 224(2) final sub-para — margined holding period
    """
    return RawSFTBundle(
        trades=SftTradeBundle(
            sft_trades=_seal_sft_trades(
                _sft_trade_df(
                    trade_id,
                    netting_set_id,
                    is_margined=True,
                    remargining_frequency_days=remargining_frequency_days,
                    mpor_floor_category=mpor_floor_category,
                    has_margin_dispute_doubling=has_margin_dispute_doubling,
                    mpor_days_override=mpor_days_override,
                )
            )
        ),
        collateral=None,
    )


# ---------------------------------------------------------------------------
# CCR-A11 / CCR-A12 acceptance SFT bundles (Phase 6 source flip).
#
# After the SFT/FCCM separation Phase 6, the CCR-A11/A12 golden acceptance
# scenarios drive through ``RawDataBundle.sft`` (the peer ``sft_fccm`` stage)
# rather than ``RawDataBundle.ccr`` (the deleted in-CCR FCCM branch). These
# builders reuse the EXACT CCR-A11/A12 trade / netting-set / collateral
# identifiers (``CCR_A11_TRADE_ID`` / ``CCR_A11_NETTING_SET_ID`` / …) so the
# emitted synthetic exposure references (``ccr__NS_SFT_001`` /
# ``ccr__NS_SFT_002``) — and therefore every acceptance assertion in
# ``test_ccr_a11_a12_sft_fccm_ead.py`` — are byte-identical to the legacy
# in-CCR result. The E* math is identical: the SFT bundle and the old CCR
# bundle feed the same ``_build_sft_exposure_rows`` core.
# ---------------------------------------------------------------------------


def build_sft_bundle_ccr_a11() -> RawSFTBundle:
    """CCR-A11 SFT bundle (uncollateralised), keyed on the golden A11 ids.

    Reproduces ``build_raw_data_bundle_ccr_a11``'s SFT trade via ``raw.sft``:
    one GBP 60.7m SFT (corp bond CQS 1, residual 7y) in netting set
    ``NS_SFT_001`` against ``CP_INST_001``. No collateral → E* = E·(1+HE).
    """
    return RawSFTBundle(
        trades=SftTradeBundle(
            sft_trades=_seal_sft_trades(_sft_trade_df(CCR_A11_TRADE_ID, CCR_A11_NETTING_SET_ID))
        ),
        collateral=None,
    )


def build_sft_bundle_ccr_a12() -> RawSFTBundle:
    """CCR-A12 SFT bundle (GBP 60m cash collateral), keyed on the golden A12 ids.

    Reproduces ``build_raw_data_bundle_ccr_a12``'s SFT trade + collateral via
    ``raw.sft``: the same SFT in ``NS_SFT_002`` plus GBP 60m cash collateral
    (HC=0, HFX=0) → E* = E·(1+HE) − 60m.
    """
    return RawSFTBundle(
        trades=SftTradeBundle(
            sft_trades=_seal_sft_trades(_sft_trade_df(CCR_A12_TRADE_ID, CCR_A12_NETTING_SET_ID))
        ),
        collateral=SftCollateralBundle(
            sft_collateral=_seal_sft_collateral(_sft_collateral_df(CCR_A12_NETTING_SET_ID))
        ),
    )
