"""
Unit tests for P1.146: a null ``is_guaranteed`` never drops or mis-buckets a row.

Pipeline position:
    OutputAggregator (reporting ledger + summary group-bys)

Key responsibilities:
- Assert an exposure with ``is_guaranteed=null`` stays on the sealed results
  ledger as a ``whole`` leg under its applied class (never silently discarded).
- Assert ``summary_by_class`` counts it in the CORPORATE bucket and the
  guaranteed leg under the guarantor's class.
- Control: the ledger's total EAD is exact (nothing dropped, nothing doubled).

History: the original P1.146 defect was the ``_crm_reporting`` re-split's
``~pl.col("is_guaranteed")`` filters silently dropping the Boolean-null row
(``~null`` evaluates to null, not True). Phase 7 S4 retired that machinery —
the summaries are pure group-bys of the sealed reporting ledger, where a null
``is_guaranteed`` falls through the ``when`` chain to
``reporting_leg_role="whole"`` and the obligor's applied class. These pins
keep the null-row semantics locked on the surviving surface.

References:
    - engine/aggregator/aggregator.py::_add_reporting_projection
    - engine/aggregator/_summaries.py::generate_summary_by_class
    - P1.146 scenario proposal
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.engine.aggregator import OutputAggregator
from tests.fixtures.contract_columns import pad_irb_branch, pad_slotting_branch
from tests.fixtures.p1_146.p1_146 import (
    CORPORATE_EXPOSURE_COUNT,
    CORPORATE_TOTAL_EAD,
    EAD_NULL,
    EXP_NULL_REF,
    LEDGER_EXPECTED_ROWS,
    RW_NULL,
    SOVEREIGN_EXPOSURE_COUNT,
    SOVEREIGN_TOTAL_EAD,
    TOTAL_LEDGER_EAD,
    build_sa_results,
)

# Padded zero-row branch frames mirroring the orchestrator's sealed branch
# collect — empty branches still carry the full edge schema in production.
EMPTY = pl.LazyFrame({"exposure_reference": pl.Series([], dtype=pl.String)})
EMPTY_IRB = pad_irb_branch(EMPTY)
EMPTY_SLOTTING = pad_slotting_branch(EMPTY)


@pytest.fixture
def crr_config() -> CalculationConfig:
    """CRR configuration for P1.146 tests."""
    return CalculationConfig.crr(reporting_date=date(2024, 12, 31))


@pytest.fixture
def aggregator() -> OutputAggregator:
    """OutputAggregator instance."""
    return OutputAggregator()


def _aggregate(aggregator: OutputAggregator, config: CalculationConfig):
    return aggregator.aggregate(
        sa_results=build_sa_results(),
        irb_results=EMPTY_IRB,
        slotting_results=EMPTY_SLOTTING,
        equity_bundle=None,
        config=config,
    )


class TestP1146IsGuaranteedNullFilter:
    """Null ``is_guaranteed`` must not silently discard or mis-bucket exposures."""

    def test_ledger_keeps_the_null_is_guaranteed_row(
        self,
        aggregator: OutputAggregator,
        crr_config: CalculationConfig,
    ) -> None:
        """All four physical rows survive to the sealed ledger — nothing dropped.

        Arrange: 4-row SA results — the __G_/__REM legs, EXP_PLAIN (False),
                 EXP_NULL (Boolean null).
        Act:     aggregate() through OutputAggregator.
        Assert:  results height == 4 and EXP_NULL is present.
        """
        result = _aggregate(aggregator, crr_config)

        df = result.results.collect()
        assert df.height == LEDGER_EXPECTED_ROWS
        assert EXP_NULL_REF in df["exposure_reference"].to_list(), (
            "Null is_guaranteed row missing from the sealed results ledger."
        )

    def test_null_is_guaranteed_row_is_a_whole_leg_under_its_applied_class(
        self,
        aggregator: OutputAggregator,
        crr_config: CalculationConfig,
    ) -> None:
        """A Boolean-null flag falls through to whole/applied — never guaranteed.

        Arrange: EXP_NULL with is_guaranteed = Polars Boolean null.
        Act:     aggregate() through OutputAggregator.
        Assert:  reporting_leg_role='whole', reporting_class='CORPORATE',
                 reporting_ead/rw carry the row's sealed values.
        """
        result = _aggregate(aggregator, crr_config)

        row = result.results.collect().filter(pl.col("exposure_reference") == EXP_NULL_REF)
        assert row["reporting_leg_role"][0] == "whole"
        assert row["reporting_class"][0] == "CORPORATE"
        assert row["reporting_ead"][0] == pytest.approx(EAD_NULL)
        assert row["reporting_rw"][0] == pytest.approx(RW_NULL)

    def test_summary_by_class_buckets_include_the_null_row(
        self,
        aggregator: OutputAggregator,
        crr_config: CalculationConfig,
    ) -> None:
        """CORPORATE counts the null row + retained leg; the guaranteed leg
        reports under the guarantor's class.

        Arrange: the 4-row physical fixture.
        Act:     aggregate() through OutputAggregator.
        Assert:  CORPORATE total_ead=2_150_000 count=3;
                 CENTRAL_GOVT_CENTRAL_BANK total_ead=600_000 count=1.
        """
        result = _aggregate(aggregator, crr_config)

        assert result.summary_by_class is not None
        summary = result.summary_by_class.collect()
        corp = summary.filter(pl.col("exposure_class") == "CORPORATE")
        sov = summary.filter(pl.col("exposure_class") == "CENTRAL_GOVT_CENTRAL_BANK")

        assert corp["total_ead"][0] == pytest.approx(CORPORATE_TOTAL_EAD)
        assert corp["exposure_count"][0] == CORPORATE_EXPOSURE_COUNT
        assert sov["total_ead"][0] == pytest.approx(SOVEREIGN_TOTAL_EAD)
        assert sov["exposure_count"][0] == SOVEREIGN_EXPOSURE_COUNT

    def test_ledger_total_ead_is_exact(
        self,
        aggregator: OutputAggregator,
        crr_config: CalculationConfig,
    ) -> None:
        """Control: the ledger's total EAD — nothing dropped, nothing doubled.

        Arrange: the 4-row physical fixture (total EAD 2_750_000).
        Act:     aggregate() through OutputAggregator.
        Assert:  sum(reporting_ead) == sum(ead_final) == 2_750_000 and the
                 summary buckets tie to the same total.
        """
        result = _aggregate(aggregator, crr_config)

        df = result.results.collect()
        assert df["reporting_ead"].sum() == pytest.approx(TOTAL_LEDGER_EAD)
        assert df["ead_final"].sum() == pytest.approx(TOTAL_LEDGER_EAD)

        assert result.summary_by_class is not None
        summary = result.summary_by_class.collect()
        assert summary["total_ead"].sum() == pytest.approx(TOTAL_LEDGER_EAD)
