"""
Unit tests for partition_out_sft_rows — the SFT-in-raw.ccr guard (Phase 6).

SFT/FCCM separation (docs/plans/sft-fccm-separation.md, Phase 6): the SA-CCR
Art. 274 chain is derivatives-only. SFT EAD (CRR Art. 271(2), Art. 220-223 FCCM)
is computed by the peer ``sft_fccm`` stage from ``RawDataBundle.sft``. Any
``transaction_type == "sft"`` trade still present in ``RawDataBundle.ccr`` is
mis-placed input that the derivative chain would silently mis-price.

``partition_out_sft_rows`` follows the project error convention (CLAUDE.md):
a data-quality issue is reported via the ``list[CalculationError]`` channel —
NEVER a raised exception. It returns a derivative-only bundle (SFT trades and the
netting sets / collateral keyed only by them removed) plus one CCR020 ERROR per
offending netting set.

This single invariant subsumes the migration plan's separate "both raw.ccr (with
SFT) and raw.sft populated → double-count" guard: forbidding SFT in raw.ccr
removes the only path by which the same SFT EAD could be computed twice.

References:
    - CRR Art. 271(2) — SFT EAD via FCCM, not SA-CCR Art. 274.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from rwa_calc.contracts.bundles import (
    CCRCollateralBundle,
    MarginAgreementBundle,
    NettingSetBundle,
    RawCCRBundle,
    TradeBundle,
)
from rwa_calc.data.column_spec import dtypes_of
from rwa_calc.data.schemas import CCR_COLLATERAL_SCHEMA
from rwa_calc.domain.enums import ErrorCategory, ErrorSeverity
from rwa_calc.engine.ccr import partition_out_sft_rows
from rwa_calc.engine.ccr.pipeline_adapter import CCR_SFT_IN_DERIVATIVE_INPUT_ERROR_CODE
from tests.fixtures.ccr.margin_builder import create_margin_agreements
from tests.fixtures.ccr.netting_set_builder import create_netting_sets, make_netting_set
from tests.fixtures.ccr.trade_builder import create_trades, make_trade

_MATURITY = date(2030, 1, 1)
_START = date(2026, 1, 1)


def _bundle(*, with_sft: bool) -> RawCCRBundle:
    """A CCR bundle with one derivative NS and optionally one SFT NS."""
    trades = [
        make_trade(
            trade_id="T_DERIV",
            netting_set_id="NS_DERIV",
            asset_class="interest_rate",
            transaction_type="derivative",
            notional=100_000_000.0,
            currency="GBP",
            maturity_date=_MATURITY,
            start_date=_START,
        )
    ]
    netting_sets = [make_netting_set(netting_set_id="NS_DERIV", counterparty_reference="CP_D")]
    collateral_rows: list[dict] = []
    if with_sft:
        trades.append(
            make_trade(
                trade_id="T_SFT",
                netting_set_id="NS_SFT",
                asset_class="credit",
                transaction_type="sft",
                notional=60_000_000.0,
                currency="GBP",
                maturity_date=_MATURITY,
                start_date=_START,
            )
        )
        netting_sets.append(
            make_netting_set(netting_set_id="NS_SFT", counterparty_reference="CP_S")
        )
        collateral_rows.append(
            {
                "ccr_collateral_reference": "COLL_SFT",
                "netting_set_id": "NS_SFT",
                "collateral_type": "cash",
                "market_value": 10_000_000.0,
                "is_posted_by_firm": False,
                "is_segregated": False,
                "currency": "GBP",
                "issuer_cqs": None,
                "issuer_type": None,
                "residual_maturity_years": None,
                "haircut_override": None,
            }
        )
    collateral_df = pl.DataFrame(collateral_rows, schema=dtypes_of(CCR_COLLATERAL_SCHEMA))
    return RawCCRBundle(
        trades=TradeBundle(trades=create_trades(trades).lazy()),
        netting_sets=NettingSetBundle(netting_sets=create_netting_sets(netting_sets).lazy()),
        margin_agreements=MarginAgreementBundle(
            margin_agreements=create_margin_agreements([]).lazy()
        ),
        ccr_collateral=CCRCollateralBundle(ccr_collateral=collateral_df.lazy()),
    )


class TestPartitionOutSftRows:
    """partition_out_sft_rows excludes SFT trades + flags them via CCR020."""

    def test_pure_derivative_bundle_is_passed_through_unchanged(self) -> None:
        """A derivatives-only bundle returns the SAME object with no errors (fast path)."""
        # Arrange
        bundle = _bundle(with_sft=False)

        # Act
        derivative_only, errors = partition_out_sft_rows(bundle)

        # Assert — identity pass-through, no errors
        assert derivative_only is bundle
        assert errors == []

    def test_sft_trades_are_excluded_from_the_derivative_bundle(self) -> None:
        """The returned bundle drops the SFT trade, NS and collateral rows."""
        # Arrange
        bundle = _bundle(with_sft=True)

        # Act
        derivative_only, _errors = partition_out_sft_rows(bundle)

        # Assert — only the derivative NS survives in trades / netting sets / collateral
        trade_ns = derivative_only.trades.trades.collect()["netting_set_id"].to_list()
        ns_ids = derivative_only.netting_sets.netting_sets.collect()["netting_set_id"].to_list()
        coll_ns = derivative_only.ccr_collateral.ccr_collateral.collect()[
            "netting_set_id"
        ].to_list()
        assert trade_ns == ["NS_DERIV"]
        assert ns_ids == ["NS_DERIV"]
        assert "NS_SFT" not in coll_ns

    def test_one_ccr020_error_per_offending_netting_set(self) -> None:
        """Exactly one CCR020 DATA_QUALITY ERROR is returned for the SFT NS."""
        # Arrange
        bundle = _bundle(with_sft=True)

        # Act
        _derivative_only, errors = partition_out_sft_rows(bundle)

        # Assert
        assert len(errors) == 1
        err = errors[0]
        assert err.code == CCR_SFT_IN_DERIVATIVE_INPUT_ERROR_CODE == "CCR020"
        assert err.severity is ErrorSeverity.ERROR
        assert err.category is ErrorCategory.DATA_QUALITY
        assert "NS_SFT" in err.message
        assert err.field_name == "transaction_type"

    def test_guard_never_raises(self) -> None:
        """The guard must use the error channel, never raise (CLAUDE.md convention)."""
        # Arrange
        bundle = _bundle(with_sft=True)

        # Act — must not raise
        derivative_only, errors = partition_out_sft_rows(bundle)

        # Assert — returns normally with the offending rows excluded + flagged
        assert derivative_only.trades.trades.collect().height == 1
        assert len(errors) == 1
