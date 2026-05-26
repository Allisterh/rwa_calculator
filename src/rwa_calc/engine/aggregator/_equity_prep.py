"""
Equity result preparation.

Internal module — not part of the public API.
"""

from __future__ import annotations

import polars as pl

from rwa_calc.domain.enums import ApproachType


def prepare_equity_results(equity_results: pl.LazyFrame) -> pl.LazyFrame:
    """Add equity approach tag, ensure exposure_class exists, and normalize RWA."""
    cols = set(equity_results.collect_schema().names())
    rwa_col = "rwa" if "rwa" in cols else "rwa_final"

    result = equity_results
    if "exposure_class" not in cols:
        result = result.with_columns([pl.lit("equity").alias("exposure_class")])

    return result.with_columns(
        [
            pl.lit(ApproachType.EQUITY.value).alias("approach_applied"),
            pl.col(rwa_col).alias("rwa_final"),
        ]
    )
