"""
Integration tests for pre/post-CRM regulatory reporting on the sealed ledger.

Phase 7 S4: the per-leg reporting ledger sealed on ``AGGREGATOR_EXIT_EDGE`` IS
the pre/post-CRM view — ``reporting_class_origin`` is the pre-substitution
(obligor applied) dimension, ``reporting_class`` the post-substitution one,
and the persisted summaries are pure group-bys of it. These tests aggregate
physical guarantee legs (``__G_``/``__REM``, as ``engine/crm/guarantees.py``
emits them) through ``OutputAggregator`` and assert both dimensions.

References:
- CRR Art. 235: risk-weight substitution on the protected portion
- CRR Art. 112: exposure class assignment (origin dimension)
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from rwa_calc.contracts.bundles import AggregatedResultBundle
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.engine.aggregator import OutputAggregator
from tests.fixtures.contract_columns import (
    pad_irb_branch,
    pad_sa_branch,
    pad_slotting_branch,
)

# Padded zero-row branch frames mirroring the orchestrator's sealed branch
# collect — empty branches still carry the full edge schema in production.
EMPTY = pl.LazyFrame({"exposure_reference": pl.Series([], dtype=pl.String)})
EMPTY_IRB = pad_irb_branch(EMPTY)
EMPTY_SLOTTING = pad_slotting_branch(EMPTY)


@pytest.fixture
def crr_config() -> CalculationConfig:
    """Create CRR configuration for tests."""
    return CalculationConfig.crr(reporting_date=date(2024, 12, 31))


@pytest.fixture
def aggregator() -> OutputAggregator:
    return OutputAggregator()


@pytest.fixture
def single_guaranteed_crm_result(
    aggregator: OutputAggregator,
    crr_config: CalculationConfig,
) -> AggregatedResultBundle:
    """Aggregate one guaranteed exposure in its physical two-leg shape.

    Borrower CP001 (CORPORATE, RW 1.0) is 600k-guaranteed by GUAR001
    (CENTRAL_GOVT_CENTRAL_BANK, RW 0.0) on a 1M exposure: a ``__G_`` leg
    (600k at the guarantor's substituted RW) + a ``__REM`` retained leg
    (400k at the borrower's RW).
    """
    sa_results = pl.LazyFrame(
        {
            "exposure_reference": ["EXP001__G_GUAR001", "EXP001__REM"],
            "counterparty_reference": ["CP001", "CP001"],
            "exposure_class": ["CORPORATE", "CORPORATE"],
            "approach_applied": ["SA", "SA"],
            "ead_final": [600_000.0, 400_000.0],
            "risk_weight": [0.0, 1.0],
            "rwa_final": [0.0, 400_000.0],
            "pre_crm_counterparty_reference": ["CP001", "CP001"],
            "pre_crm_exposure_class": ["CORPORATE", "CORPORATE"],
            "post_crm_counterparty_guaranteed": ["GUAR001", None],
            "post_crm_exposure_class_guaranteed": ["CENTRAL_GOVT_CENTRAL_BANK", None],
            "is_guaranteed": [True, False],
            "guaranteed_portion": [600_000.0, 0.0],
            "unguaranteed_portion": [0.0, 400_000.0],
            "guarantor_reference": ["GUAR001", None],
            "parent_exposure_reference": ["EXP001", "EXP001"],
            "pre_crm_risk_weight": [1.0, 1.0],
            "guarantor_rw": [0.0, None],
        }
    )

    return aggregator.aggregate(
        sa_results=pad_sa_branch(sa_results),
        irb_results=EMPTY_IRB,
        slotting_results=EMPTY_SLOTTING,
        equity_bundle=None,
        config=crr_config,
    )


class TestLedgerLegRoles:
    """The sealed ledger names the physical guarantee split."""

    def test_guaranteed_exposure_carries_two_named_legs(
        self,
        single_guaranteed_crm_result: AggregatedResultBundle,
    ) -> None:
        """The __G_ leg reports under the guarantor; the __REM leg under the obligor."""
        df = single_guaranteed_crm_result.results.collect()
        assert len(df) == 2

        guaranteed = df.filter(pl.col("reporting_leg_role") == "guaranteed")
        assert len(guaranteed) == 1
        assert guaranteed["reporting_class"][0] == "CENTRAL_GOVT_CENTRAL_BANK"
        assert guaranteed["reporting_class_origin"][0] == "CORPORATE"
        assert guaranteed["reporting_ead"][0] == pytest.approx(600_000.0)

        retained = df.filter(pl.col("reporting_leg_role") == "retained")
        assert len(retained) == 1
        assert retained["reporting_class"][0] == "CORPORATE"
        assert retained["reporting_ead"][0] == pytest.approx(400_000.0)

    def test_non_guaranteed_exposure_is_a_single_whole_leg(
        self,
        aggregator: OutputAggregator,
        crr_config: CalculationConfig,
    ) -> None:
        """An unguaranteed exposure is one whole leg; both class dimensions agree."""
        sa_results = pl.LazyFrame(
            {
                "exposure_reference": ["EXP001"],
                "counterparty_reference": ["CP001"],
                "exposure_class": ["CORPORATE"],
                "approach_applied": ["SA"],
                "ead_final": [1_000_000.0],
                "risk_weight": [1.0],
                "rwa_final": [1_000_000.0],
                "pre_crm_exposure_class": ["CORPORATE"],
                "is_guaranteed": [False],
                "guaranteed_portion": [0.0],
                "unguaranteed_portion": [1_000_000.0],
            }
        )

        result = aggregator.aggregate(
            sa_results=pad_sa_branch(sa_results),
            irb_results=EMPTY_IRB,
            slotting_results=EMPTY_SLOTTING,
            equity_bundle=None,
            config=crr_config,
        )

        df = result.results.collect()
        assert len(df) == 1
        assert df["reporting_leg_role"][0] == "whole"
        assert df["reporting_class"][0] == "CORPORATE"
        assert df["reporting_class_origin"][0] == "CORPORATE"


class TestOriginDimension:
    """``reporting_class_origin`` is the pre-substitution (obligor) dimension."""

    def test_origin_groups_all_ead_under_the_obligor_class(
        self,
        single_guaranteed_crm_result: AggregatedResultBundle,
    ) -> None:
        """Grouping the ledger by origin reproduces the pre-CRM view: the whole
        1M stays under CORPORATE even though 600k reports under the guarantor."""
        df = single_guaranteed_crm_result.results.collect()
        origin = df.group_by("reporting_class_origin").agg(
            pl.col("reporting_ead").sum(),
            pl.len().alias("legs"),
        )
        assert origin.height == 1
        row = origin.row(0, named=True)
        assert row["reporting_class_origin"] == "CORPORATE"
        assert row["reporting_ead"] == pytest.approx(1_000_000.0)
        assert row["legs"] == 2


class TestSummaryByClassPostCRM:
    """summary_by_class buckets the guaranteed leg under the guarantor's class."""

    def test_summary_splits_by_guarantor_class(
        self,
        single_guaranteed_crm_result: AggregatedResultBundle,
    ) -> None:
        assert single_guaranteed_crm_result.summary_by_class is not None
        summary_df = single_guaranteed_crm_result.summary_by_class.collect()
        assert len(summary_df) == 2

        corp_row = summary_df.filter(pl.col("exposure_class") == "CORPORATE")
        assert len(corp_row) == 1
        assert corp_row["total_ead"][0] == pytest.approx(400_000.0)
        assert corp_row["total_rwa"][0] == pytest.approx(400_000.0)

        sov_row = summary_df.filter(pl.col("exposure_class") == "CENTRAL_GOVT_CENTRAL_BANK")
        assert len(sov_row) == 1
        assert sov_row["total_ead"][0] == pytest.approx(600_000.0)
        assert sov_row["total_rwa"][0] == pytest.approx(0.0)


class TestMixedSAIRBPortfolio:
    """Mixed SA and IRB guarantee legs aggregate coherently."""

    def test_mixed_sa_irb_portfolio_aggregation(
        self,
        aggregator: OutputAggregator,
        crr_config: CalculationConfig,
    ) -> None:
        """SA legs split to INSTITUTION, IRB legs to CENTRAL_GOVT_CENTRAL_BANK;
        origin keeps everything under CORPORATE; totals tie to rwa_final."""
        sa_results = pl.LazyFrame(
            {
                "exposure_reference": ["SA001__G_INST01", "SA001__REM"],
                "counterparty_reference": ["CP001", "CP001"],
                "exposure_class": ["CORPORATE", "CORPORATE"],
                "approach_applied": ["SA", "SA"],
                "ead_final": [250_000.0, 250_000.0],
                "risk_weight": [0.2, 1.0],
                "rwa_final": [50_000.0, 250_000.0],
                "pre_crm_exposure_class": ["CORPORATE", "CORPORATE"],
                "post_crm_exposure_class_guaranteed": ["INSTITUTION", None],
                "is_guaranteed": [True, False],
                "guaranteed_portion": [250_000.0, 0.0],
                "unguaranteed_portion": [0.0, 250_000.0],
                "parent_exposure_reference": ["SA001", "SA001"],
                "pre_crm_risk_weight": [1.0, 1.0],
                "guarantor_rw": [0.2, None],
            }
        )

        irb_results = pl.LazyFrame(
            {
                "exposure_reference": ["IRB001__G_GOV01", "IRB001__REM"],
                "counterparty_reference": ["CP002", "CP002"],
                "exposure_class": ["CORPORATE", "CORPORATE"],
                "approach": ["FIRB", "FIRB"],
                "approach_applied": ["FIRB", "FIRB"],
                "ead_final": [500_000.0, 500_000.0],
                "risk_weight": [0.0, 0.5],
                "rwa_final": [0.0, 250_000.0],
                "pre_crm_exposure_class": ["CORPORATE", "CORPORATE"],
                "post_crm_exposure_class_guaranteed": ["CENTRAL_GOVT_CENTRAL_BANK", None],
                "is_guaranteed": [True, False],
                "guaranteed_portion": [500_000.0, 0.0],
                "unguaranteed_portion": [0.0, 500_000.0],
                "parent_exposure_reference": ["IRB001", "IRB001"],
                "pre_crm_risk_weight": [0.5, 0.5],
                "guarantor_rw": [0.0, None],
            }
        )

        result = aggregator.aggregate(
            sa_results=pad_sa_branch(sa_results),
            irb_results=pad_irb_branch(irb_results),
            slotting_results=EMPTY_SLOTTING,
            equity_bundle=None,
            config=crr_config,
        )

        # Origin dimension: everything under CORPORATE (1.5M across 4 legs).
        df = result.results.collect()
        origin = df.group_by("reporting_class_origin").agg(pl.col("reporting_ead").sum())
        assert origin.height == 1
        assert origin["reporting_ead"][0] == pytest.approx(1_500_000.0)

        # Post-substitution: three classes, and the summary ties to rwa_final.
        assert result.summary_by_class is not None
        summary_df = result.summary_by_class.collect()
        assert len(summary_df) == 3
        assert summary_df["total_rwa"].sum() == pytest.approx(df["rwa_final"].sum())
