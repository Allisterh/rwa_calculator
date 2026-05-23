"""
Maturity factor for SA-CCR trades (unmargined netting sets).

Pipeline position:
    Classifier -> CCRCalculator (maturity factor) -> ...

Key responsibilities:
- Compute ``MF = sqrt(min(M, 1y) / 1y)`` per CRR Art. 279c(1) for trades
  in unmargined netting sets.

References:
- CRR Art. 279c(1): Maturity factor (unmargined)
"""

from __future__ import annotations

import logging

import polars as pl
from watchfire import cites

from rwa_calc.data.tables.sa_ccr_factors import (
    MF_UNMARGINED_CAP_YEARS,
    MF_UNMARGINED_DENOM_YEARS,
)

logger = logging.getLogger(__name__)


# Watchfire's bundled CRR index does not yet contain Art. 279c; collapse the
# ``@cites`` to the parent Art. 279 and preserve sub-article attribution in the
# docstring (mirrors the P8.7 fix-commit pattern for Art. 280a/b/c).
@cites("CRR Art. 279")
def compute_maturity_factor_unmargined(trades: pl.LazyFrame) -> pl.LazyFrame:
    """Maturity factor for unmargined transactions per CRR Art. 279c(1).

    MF = sqrt(min(M, 1y) / 1y)

    Args:
        trades: LazyFrame containing a ``years_to_maturity`` column (Float64) —
            residual maturity in years from reporting date to trade maturity.

    Returns:
        The input LazyFrame with a new ``maturity_factor: Float64`` column.

    References:
        CRR Art. 279c(1); BCBS CRE52.50-52.
    """
    return trades.with_columns(
        (
            pl.min_horizontal(
                pl.col("years_to_maturity"),
                pl.lit(float(MF_UNMARGINED_CAP_YEARS)),
            )
            / float(MF_UNMARGINED_DENOM_YEARS)
        )
        .sqrt()
        .alias("maturity_factor")
    )
