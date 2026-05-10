"""
Generate P1.101 fixtures: CRR Art. 226(1) Non-Daily Revaluation Haircut Adjustment.

Pipeline position:
    fixture-builder output -> test-writer -> engine-implementer (crm/haircuts.py)

Key responsibilities:
- Produce one collateral parquet for COLL_CRM_REVAL with the new field
  ``revaluation_frequency_days=5``.  The engine-implementer will add this
  column to COLLATERAL_SCHEMA; this module carries it as a supplementary
  column added to the base-schema DataFrame after construction.
- Counterparty CP_CRM_REVAL and loan LOAN_CRM_REVAL are written into the
  main fixtures (corporate.py / loans.py) so the generate_all.py integrity
  check stays clean.  This module writes only the standalone collateral
  parquet (and a convenience copy of the counterparty + loan rows for the
  test-writer to reference directly).

Scenario design (CRR-D-REVAL):
    An SFT (is_sft=True) creates a 5-day holding period (T_m = 5).
    The collateral is revalued every 5 days (N = revaluation_frequency_days = 5).

    Step 1 — base 10-day haircut (CRR Art. 224 Table 1):
        corp_bond_cqs1_1_5y  = H_n = 4%  (CQS 1, 1–5y band)

    Step 2 — scale to SFT 5-day holding period (Art. 226(2)):
        H_m = H_n × sqrt(T_m / 10) = 0.04 × sqrt(5/10) = 0.028284271247461903

    Step 3 — non-daily revaluation adjustment (Art. 226(1)):
        H = H_m × sqrt((N + T_m - 1) / T_m)
          = H_m × sqrt((5 + 5 - 1) / 5)
          = H_m × sqrt(9 / 5)
          = H_m × sqrt(1.8)
          = 0.028284271247461903 × 1.3416407864998738
          = 0.037947331922020544

    Step 4 — adjusted collateral (CRR Art. 220):
        C* = 800,000 × (1 − 0.037947331922020544) = 769,642.13446238357

    Step 5 — EAD (net exposure):
        E* = max(0, 1,000,000 − 769,642.13446238357) = 230,357.86553761643

    Step 6 — SA risk weight (CRR Art. 122, unrated corporate):
        RW = 1.00

    Step 7 — RWA:
        RWA = 230,357.86553761643

    Counterfactual (without Art. 226(1) reval scaling):
        H = H_m = 0.028284271247461903
        C* = 800,000 × (1 − 0.028284271247461903) = 777,372.58
        E* = 1,000,000 − 777,372.58 = 222,627.42
        RWA ≈ 222,627.42  (delta ≈ +£7,730)

References:
    - CRR Art. 226(1): non-daily-mark-to-market / non-daily-remargining scaling
    - CRR Art. 226(2): liquidation-period scaling formula
    - CRR Art. 224 Table 1: supervisory haircut schedule
    - CRR Art. 220: adjusted exposure / collateral value formula
    - src/rwa_calc/data/tables/haircuts.py: corp_bond_cqs1_1_5y entry

Usage:
    uv run python tests/fixtures/p1_101/p1_101.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

from rwa_calc.data.column_spec import dtypes_of
from rwa_calc.data.schemas import COLLATERAL_SCHEMA, COUNTERPARTY_SCHEMA, LOAN_SCHEMA

# ---------------------------------------------------------------------------
# Scenario constants
# ---------------------------------------------------------------------------

COUNTERPARTY_REF = "CP_CRM_REVAL"
LOAN_REF = "LOAN_CRM_REVAL"
COLLATERAL_REF = "COLL_CRM_REVAL"

VALUE_DATE = date(2026, 1, 1)

# Collateral parameters (CRR Art. 224 Table 1 — corp_bond_cqs1_1_5y)
H_N: float = 0.04  # Base 10-day haircut, corp bond CQS 1, 1-5y band
T_M: int = 5  # Holding period days (SFT — Art. 224(2)(a))
N: int = 5  # Revaluation frequency days (new field: revaluation_frequency_days)

# Hand-calculated intermediate values (for test assertions)
H_M: float = H_N * math.sqrt(T_M / 10)  # Art. 226(2): scale to T_m
H_REVAL: float = H_M * math.sqrt((N + T_M - 1) / T_M)  # Art. 226(1): reval adjustment

MARKET_VALUE: float = 800_000.0
DRAWN_AMOUNT: float = 1_000_000.0

ADJUSTED_COLLATERAL: float = MARKET_VALUE * (1.0 - H_REVAL)
EAD_FINAL: float = max(0.0, DRAWN_AMOUNT - ADJUSTED_COLLATERAL)
SA_RISK_WEIGHT: float = 1.00  # CRR Art. 122, unrated corporate
RWA_FINAL: float = EAD_FINAL * SA_RISK_WEIGHT


# ---------------------------------------------------------------------------
# Private row builders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Collateral:
    """P1.101 collateral row with the new revaluation_frequency_days field."""

    collateral_reference: str
    collateral_type: str
    currency: str
    maturity_date: date | None
    market_value: float
    nominal_value: float
    beneficiary_type: str
    beneficiary_reference: str
    issuer_cqs: int
    issuer_type: str
    residual_maturity_years: float
    original_maturity_years: float
    is_eligible_financial_collateral: bool
    is_eligible_irb_collateral: bool
    valuation_date: date
    valuation_type: str
    liquidation_period_days: int | None
    revaluation_frequency_days: int | None  # NEW — Art. 226(1): N

    def to_base_dict(self) -> dict:
        """Return fields that belong to the existing COLLATERAL_SCHEMA."""
        return {
            "collateral_reference": self.collateral_reference,
            "collateral_type": self.collateral_type,
            "currency": self.currency,
            "maturity_date": self.maturity_date,
            "market_value": self.market_value,
            "nominal_value": self.nominal_value,
            "beneficiary_type": self.beneficiary_type,
            "beneficiary_reference": self.beneficiary_reference,
            "issuer_cqs": self.issuer_cqs,
            "issuer_type": self.issuer_type,
            "residual_maturity_years": self.residual_maturity_years,
            "original_maturity_years": self.original_maturity_years,
            "is_eligible_financial_collateral": self.is_eligible_financial_collateral,
            "is_eligible_irb_collateral": self.is_eligible_irb_collateral,
            "valuation_date": self.valuation_date,
            "valuation_type": self.valuation_type,
            "liquidation_period_days": self.liquidation_period_days,
        }


# ---------------------------------------------------------------------------
# Public DataFrame factories
# ---------------------------------------------------------------------------


def create_p1101_counterparty() -> pl.DataFrame:
    """
    Return the P1.101 counterparty (unrated corporate, GB) as a DataFrame.

    entity_type=corporate, unrated → SA RW = 100% (CRR Art. 122).
    default_status=False — performing exposure.
    Annual revenue £90m → large corporate (no SME factor).
    """
    row = {
        "counterparty_reference": COUNTERPARTY_REF,
        "counterparty_name": "Reval Haircut Test Corporate Ltd",
        "entity_type": "corporate",
        "country_code": "GB",
        "annual_revenue": 90_000_000.0,
        "total_assets": 70_000_000.0,
        "default_status": False,
        "sector_code": "64.19",
        "apply_fi_scalar": False,
        "is_managed_as_retail": False,
    }
    return pl.DataFrame([row], schema=dtypes_of(COUNTERPARTY_SCHEMA))


def create_p1101_loan() -> pl.DataFrame:
    """
    Return the P1.101 loan (£1m GBP SFT, is_sft=True) as a DataFrame.

    is_sft=True → engine derives T_m=5 for the SFT haircut-period branch
    (haircuts.py lines 144-149).  Maturity 2030-01-01 is before the collateral
    residual-maturity window (4.5y from VALUE_DATE ≈ 2030-07-01) to avoid
    triggering a maturity-mismatch haircut.
    """
    row = {
        "loan_reference": LOAN_REF,
        "product_type": "repo",
        "book_code": "FI_LENDING",
        "counterparty_reference": COUNTERPARTY_REF,
        "value_date": VALUE_DATE,
        "maturity_date": date(2030, 1, 1),
        "currency": "GBP",
        "drawn_amount": DRAWN_AMOUNT,
        "interest": 0.0,
        "lgd": 0.45,
        "beel": 0.0,
        "seniority": "senior",
        "is_sft": True,
    }
    return pl.DataFrame([row], schema=dtypes_of(LOAN_SCHEMA))


def create_p1101_collateral() -> pl.DataFrame:
    """
    Return the P1.101 collateral row as a DataFrame.

    The returned DataFrame contains all columns from COLLATERAL_SCHEMA plus the
    new ``revaluation_frequency_days`` column (Int32, nullable).  The engine-
    implementer will add this column to COLLATERAL_SCHEMA; until then the column
    is carried here as a supplementary field so the test-writer can assert on it
    before the schema migration lands.

    Collateral parameters:
    - collateral_type=corp_bond  (routes to corp_bond_cqs1 haircut family)
    - issuer_cqs=1, issuer_type=corporate
    - residual_maturity_years=4.5  (lands in 1_5y band → H_n=4%)
    - revaluation_frequency_days=5  (Art. 226(1): N=5 days)
    - liquidation_period_days=None  (engine derives T_m=5 from loan.is_sft)
    """
    row = _Collateral(
        collateral_reference=COLLATERAL_REF,
        collateral_type="corp_bond",
        currency="GBP",
        maturity_date=None,
        market_value=MARKET_VALUE,
        nominal_value=MARKET_VALUE,
        beneficiary_type="loan",
        beneficiary_reference=LOAN_REF,
        issuer_cqs=1,
        issuer_type="corporate",
        residual_maturity_years=4.5,
        original_maturity_years=5.0,
        is_eligible_financial_collateral=True,
        is_eligible_irb_collateral=True,
        valuation_date=VALUE_DATE,
        valuation_type="market",
        liquidation_period_days=None,
        revaluation_frequency_days=N,
    )

    # Build DataFrame from COLLATERAL_SCHEMA columns first, then append the
    # new revaluation_frequency_days column so it survives independently of
    # when the engine-implementer adds it to the schema.
    base_df = pl.DataFrame([row.to_base_dict()], schema=dtypes_of(COLLATERAL_SCHEMA))
    return base_df.with_columns(
        pl.lit(row.revaluation_frequency_days).cast(pl.Int32).alias("revaluation_frequency_days")
    )


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------


def save_p1101_fixtures(output_dir: Path | None = None) -> dict[str, Path]:
    """
    Write all P1.101 parquet files and return a mapping of name -> path.

    Three parquet files are written:
    - counterparty.parquet  (1 row: CP_CRM_REVAL)
    - loan.parquet          (1 row: LOAN_CRM_REVAL, is_sft=True)
    - collateral.parquet    (1 row: COLL_CRM_REVAL with revaluation_frequency_days=5)

    Args:
        output_dir: Target directory. Defaults to the package directory.

    Returns:
        dict mapping artefact name to saved Path.
    """
    if output_dir is None:
        output_dir = Path(__file__).parent

    saved: dict[str, Path] = {}

    artefacts = [
        ("counterparty", create_p1101_counterparty()),
        ("loan", create_p1101_loan()),
        ("collateral", create_p1101_collateral()),
    ]

    for name, df in artefacts:
        path = output_dir / f"{name}.parquet"
        df.write_parquet(path)
        saved[name] = path

    return saved


def print_summary(saved: dict[str, Path]) -> None:
    """Print a human-readable generation summary."""
    print("P1.101 fixture generation complete")
    print("-" * 70)
    for name, path in saved.items():
        df = pl.read_parquet(path)
        cols = len(df.columns)
        print(f"  {name:<20} {len(df):>3} row(s)  {cols:>3} col(s)  ->  {path}")
    print("-" * 70)
    print("Scenario: CRR Art. 226(1) — non-daily revaluation haircut adjustment")
    print(f"  H_n (base 10-day, corp_bond CQS1 1-5y)       = {H_N:.6f}  (4.0%)")
    print(f"  H_m (scaled to T_m={T_M}d SFT, Art. 226(2))      = {H_M:.15f}")
    print(f"  H   (reval adj N={N}d, Art. 226(1))             = {H_REVAL:.15f}")
    print(f"  Adjusted collateral C* = {ADJUSTED_COLLATERAL:,.5f}")
    print(f"  EAD = E* = {EAD_FINAL:,.5f}")
    print(f"  SA RW = {SA_RISK_WEIGHT:.0%}  |  RWA = {RWA_FINAL:,.5f}")

    # Confirm revaluation_frequency_days column is present
    coll_df = pl.read_parquet(saved["collateral"])
    if "revaluation_frequency_days" in coll_df.columns:
        val = coll_df["revaluation_frequency_days"][0]
        print(f"\n  revaluation_frequency_days column present: {val}")
    else:
        print("\n  WARNING: revaluation_frequency_days column missing from collateral parquet")


def main() -> None:
    """Entry point for standalone generation."""
    saved = save_p1101_fixtures()
    print_summary(saved)


if __name__ == "__main__":
    main()
