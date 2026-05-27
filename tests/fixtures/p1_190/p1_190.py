"""
Generate P1.190 fixtures: Basel 3.1 F-IRB Foundation Collateral Method (Art. 230)
continuous LGD* formula, and CRR mirror scenarios.

Pipeline position:
    fixture-builder output -> test-writer -> engine-implementer (crm/firb_lgd.py)

Scenario design:

    Six F-IRB senior corporate scenarios exercising Art. 230 LGD* calculation:

    Basel 3.1 scenarios (PS1/26 Art. 230(1) continuous formula):
        b31_thin_re           — RE collateral at 2.5% LTV (thin coverage)
        b31_full_re           — RE collateral at 100% LTV (full coverage)
        b31_other_physical    — other physical collateral 50% of EAD
        b31_re_threshold_30pct — RE collateral exactly at 30% threshold

    CRR scenarios (CRR Art. 230 step-function with C*/C** gate):
        crr_thin_re           — RE collateral at 2.5% LTV → C* gate zeros it
        crr_full_re           — RE collateral at 100% LTV → OC 1.4× path

Hand-calc expected LGD* values:
    b31_thin_re:           0.3970  (PS1/26 Art. 230(1) continuous formula)
    b31_full_re:           0.2800
    b31_other_physical:    0.3150
    b31_re_threshold_30pct: 0.3640
    crr_thin_re:           0.4500  (C* gate zeros thin collateral; LGDU fallback)
    crr_full_re:           0.378571 (CRR Art. 230 OC 1.4x path, LGDS=35%)

References:
    - PRA PS1/26 Art. 230(1): LGD* continuous formula
    - PRA PS1/26 Art. 230(2): HC table (40% non-financial) and LGDS table (0%/20%/20%/25%)
    - PRA PS1/26 Art. 161(1)(aa): LGDU senior unsecured non-FSE corporate = 40%
    - CRR Art. 230 Table 5: senior LGDS 35%/35%/35%/40%, OC 1.0x/1.25x/1.4x/1.4x
    - CRR Art. 161(1)(a): LGDU senior unsecured corporate = 45%
    - IMPLEMENTATION_PLAN.md: P1.190 entry

Usage:
    uv run python tests/fixtures/p1_190/p1_190.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl
from dateutil.relativedelta import relativedelta

from rwa_calc.data.column_spec import dtypes_of
from rwa_calc.data.schemas import (
    COLLATERAL_SCHEMA,
    COUNTERPARTY_SCHEMA,
    FACILITY_SCHEMA,
    LOAN_SCHEMA,
    MODEL_PERMISSIONS_SCHEMA,
    RATINGS_SCHEMA,
)

# ---------------------------------------------------------------------------
# Shared scenario constants
# ---------------------------------------------------------------------------

REPORTING_DATE = date(2026, 6, 30)
MATURITY_DATE = REPORTING_DATE + relativedelta(years=3)  # 2029-06-30 => M ≈ 3.0y
RATING_DATE = date(2026, 6, 30)
VALUE_DATE = date(2026, 6, 30)

DRAWN_AMOUNT: float = 10_000_000.00
FACILITY_LIMIT: float = 10_000_000.00
PD: float = 0.02  # 2%

# ---------------------------------------------------------------------------
# Per-scenario fixture ID constants
# ---------------------------------------------------------------------------

# Basel 3.1 scenarios
B31_THIN_RE_CP_REF = "B31-P1190-CP-b31_thin_re"
B31_THIN_RE_FAC_REF = "B31-P1190-F-b31_thin_re"
B31_THIN_RE_LOAN_REF = "B31-P1190-L-b31_thin_re"
B31_THIN_RE_COLL_REF = "B31-P1190-C-1"
B31_THIN_RE_MODEL_ID = "B31_CORP_FIRB_P1190_b31_thin_re"
B31_THIN_RE_EXPECTED_LGD_STAR: float = 0.3970

B31_FULL_RE_CP_REF = "B31-P1190-CP-b31_full_re"
B31_FULL_RE_FAC_REF = "B31-P1190-F-b31_full_re"
B31_FULL_RE_LOAN_REF = "B31-P1190-L-b31_full_re"
B31_FULL_RE_COLL_REF = "B31-P1190-C-2"
B31_FULL_RE_MODEL_ID = "B31_CORP_FIRB_P1190_b31_full_re"
B31_FULL_RE_EXPECTED_LGD_STAR: float = 0.2800

B31_OTHER_PHYSICAL_CP_REF = "B31-P1190-CP-b31_other_physical"
B31_OTHER_PHYSICAL_FAC_REF = "B31-P1190-F-b31_other_physical"
B31_OTHER_PHYSICAL_LOAN_REF = "B31-P1190-L-b31_other_physical"
B31_OTHER_PHYSICAL_COLL_REF = "B31-P1190-C-3"
B31_OTHER_PHYSICAL_MODEL_ID = "B31_CORP_FIRB_P1190_b31_other_physical"
# PS1/26 Art. 230(1) continuous formula with LGDU=0.40 (Art. 161(1)(aa) non-FSE
# corporate senior unsecured), LGDS=0.25 (Art. 230(2) other physical), HC=0.40
# (Art. 230(2) other physical), OC=1.0 (no divisor under B31):
#   C_adj = 5,000,000 × (1 - 0.40) = 3,000,000
#   ES    = min(3,000,000 / 1.0, 10,000,000) = 3,000,000
#   LGD*  = 0.40 × (1 - 0.30) + 0.25 × 0.30 = 0.2800 + 0.0750 = 0.3550
B31_OTHER_PHYSICAL_EXPECTED_LGD_STAR: float = 0.3550

B31_RE_THRESHOLD_CP_REF = "B31-P1190-CP-b31_re_threshold_30pct"
B31_RE_THRESHOLD_FAC_REF = "B31-P1190-F-b31_re_threshold_30pct"
B31_RE_THRESHOLD_LOAN_REF = "B31-P1190-L-b31_re_threshold_30pct"
B31_RE_THRESHOLD_COLL_REF = "B31-P1190-C-4"
B31_RE_THRESHOLD_MODEL_ID = "B31_CORP_FIRB_P1190_b31_re_threshold_30pct"
B31_RE_THRESHOLD_EXPECTED_LGD_STAR: float = 0.3640

# CRR mirror scenarios
CRR_THIN_RE_CP_REF = "CRR-P1190-CP-crr_thin_re"
CRR_THIN_RE_FAC_REF = "CRR-P1190-F-crr_thin_re"
CRR_THIN_RE_LOAN_REF = "CRR-P1190-L-crr_thin_re"
CRR_THIN_RE_COLL_REF = "CRR-P1190-C-1"
CRR_THIN_RE_MODEL_ID = "CRR_CORP_FIRB_P1190_crr_thin_re"
CRR_THIN_RE_EXPECTED_LGD_STAR: float = 0.4500

CRR_FULL_RE_CP_REF = "CRR-P1190-CP-crr_full_re"
CRR_FULL_RE_FAC_REF = "CRR-P1190-F-crr_full_re"
CRR_FULL_RE_LOAN_REF = "CRR-P1190-L-crr_full_re"
CRR_FULL_RE_COLL_REF = "CRR-P1190-C-2"
CRR_FULL_RE_MODEL_ID = "CRR_CORP_FIRB_P1190_crr_full_re"
CRR_FULL_RE_EXPECTED_LGD_STAR: float = 0.378571

# ---------------------------------------------------------------------------
# Private dataclasses (shared across scenarios)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Counterparty:
    counterparty_reference: str
    counterparty_name: str
    entity_type: str
    country_code: str
    default_status: bool
    is_financial_sector_entity: bool
    apply_fi_scalar: bool

    def to_dict(self) -> dict:
        return {
            "counterparty_reference": self.counterparty_reference,
            "counterparty_name": self.counterparty_name,
            "entity_type": self.entity_type,
            "country_code": self.country_code,
            "default_status": self.default_status,
            "is_financial_sector_entity": self.is_financial_sector_entity,
            "apply_fi_scalar": self.apply_fi_scalar,
        }


@dataclass(frozen=True)
class _Facility:
    facility_reference: str
    counterparty_reference: str
    currency: str
    value_date: date
    maturity_date: date
    limit: float
    committed: bool
    seniority: str
    risk_type: str

    def to_dict(self) -> dict:
        return {
            "facility_reference": self.facility_reference,
            "counterparty_reference": self.counterparty_reference,
            "currency": self.currency,
            "value_date": self.value_date,
            "maturity_date": self.maturity_date,
            "limit": self.limit,
            "committed": self.committed,
            "seniority": self.seniority,
            "risk_type": self.risk_type,
        }


@dataclass(frozen=True)
class _Loan:
    loan_reference: str
    counterparty_reference: str
    currency: str
    value_date: date
    maturity_date: date
    drawn_amount: float
    interest: float
    seniority: str

    def to_dict(self) -> dict:
        return {
            "loan_reference": self.loan_reference,
            "counterparty_reference": self.counterparty_reference,
            "currency": self.currency,
            "value_date": self.value_date,
            "maturity_date": self.maturity_date,
            "drawn_amount": self.drawn_amount,
            "interest": self.interest,
            "seniority": self.seniority,
        }


@dataclass(frozen=True)
class _Collateral:
    """Collateral row with optional RE-specific fields."""

    collateral_reference: str
    collateral_type: str
    currency: str
    market_value: float
    beneficiary_type: str
    beneficiary_reference: str
    is_eligible_financial_collateral: bool
    is_eligible_irb_collateral: bool
    # RE-specific fields (None for other_physical)
    property_type: str | None
    property_ltv: float | None

    def to_dict(self) -> dict:
        return {
            "collateral_reference": self.collateral_reference,
            "collateral_type": self.collateral_type,
            "currency": self.currency,
            "market_value": self.market_value,
            "beneficiary_type": self.beneficiary_type,
            "beneficiary_reference": self.beneficiary_reference,
            "is_eligible_financial_collateral": self.is_eligible_financial_collateral,
            "is_eligible_irb_collateral": self.is_eligible_irb_collateral,
            "property_type": self.property_type,
            "property_ltv": self.property_ltv,
        }


@dataclass(frozen=True)
class _Rating:
    rating_reference: str
    counterparty_reference: str
    rating_type: str
    pd: float
    model_id: str
    rating_date: date

    def to_dict(self) -> dict:
        return {
            "rating_reference": self.rating_reference,
            "counterparty_reference": self.counterparty_reference,
            "rating_type": self.rating_type,
            "pd": self.pd,
            "model_id": self.model_id,
            "rating_date": self.rating_date,
        }


@dataclass(frozen=True)
class _ModelPermission:
    model_id: str
    exposure_class: str
    approach: str
    country_codes: str | None
    excluded_book_codes: str | None

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "exposure_class": self.exposure_class,
            "approach": self.approach,
            "country_codes": self.country_codes,
            "excluded_book_codes": self.excluded_book_codes,
        }


# ---------------------------------------------------------------------------
# Private factory helpers
# ---------------------------------------------------------------------------


def _make_counterparty(cp_ref: str, scenario_label: str) -> pl.DataFrame:
    row = _Counterparty(
        counterparty_reference=cp_ref,
        counterparty_name=f"P1.190 F-IRB Corporate ({scenario_label})",
        entity_type="corporate",
        country_code="GB",
        default_status=False,
        is_financial_sector_entity=False,
        apply_fi_scalar=False,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(COUNTERPARTY_SCHEMA))


def _make_facility(fac_ref: str, cp_ref: str) -> pl.DataFrame:
    row = _Facility(
        facility_reference=fac_ref,
        counterparty_reference=cp_ref,
        currency="GBP",
        value_date=VALUE_DATE,
        maturity_date=MATURITY_DATE,
        limit=FACILITY_LIMIT,
        committed=True,
        seniority="senior",
        risk_type="funded",
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(FACILITY_SCHEMA))


def _make_loan(loan_ref: str, cp_ref: str) -> pl.DataFrame:
    row = _Loan(
        loan_reference=loan_ref,
        counterparty_reference=cp_ref,
        currency="GBP",
        value_date=VALUE_DATE,
        maturity_date=MATURITY_DATE,
        drawn_amount=DRAWN_AMOUNT,
        interest=0.0,
        seniority="senior",
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(LOAN_SCHEMA))


def _make_collateral(
    coll_ref: str,
    collateral_type: str,
    market_value: float,
    fac_ref: str,
    property_type: str | None,
    property_ltv: float | None,
) -> pl.DataFrame:
    """
    Build one collateral row.

    beneficiary_type=facility: collateral is pledged at facility level (per proposal).
    original_maturity_years=10.0: per proposal; no maturity mismatch.
    is_eligible_irb_collateral=True: RE and other physical are eligible F-IRB
        non-financial collateral per CRR Art. 199(4)/(5) / PS1/26 Art. 199.
    is_eligible_financial_collateral=False: RE/other-physical are not FCSM collateral.
    """
    row = _Collateral(
        collateral_reference=coll_ref,
        collateral_type=collateral_type,
        currency="GBP",
        market_value=market_value,
        beneficiary_type="facility",
        beneficiary_reference=fac_ref,
        is_eligible_financial_collateral=False,
        is_eligible_irb_collateral=True,
        property_type=property_type,
        property_ltv=property_ltv,
    )
    base = pl.DataFrame([row.to_dict()], schema=dtypes_of(COLLATERAL_SCHEMA))
    # original_maturity_years = 10.0 as per proposal (no maturity mismatch)
    return base.with_columns(pl.lit(10.0).alias("original_maturity_years").cast(pl.Float64))


def _make_rating(scenario_label: str, cp_ref: str, model_id: str) -> pl.DataFrame:
    row = _Rating(
        rating_reference=f"RTG-P1190-{scenario_label}",
        counterparty_reference=cp_ref,
        rating_type="internal",
        pd=PD,
        model_id=model_id,
        rating_date=RATING_DATE,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(RATINGS_SCHEMA))


def _make_model_permission(model_id: str) -> pl.DataFrame:
    """Corporate foundation_irb model permission, no geographic/book restriction."""
    row = _ModelPermission(
        model_id=model_id,
        exposure_class="corporate",
        approach="foundation_irb",
        country_codes=None,
        excluded_book_codes=None,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(MODEL_PERMISSIONS_SCHEMA))


# ---------------------------------------------------------------------------
# Per-scenario artefact sets
# ---------------------------------------------------------------------------


def _artefacts_for_scenario(
    scenario_label: str,
    cp_ref: str,
    fac_ref: str,
    loan_ref: str,
    coll_ref: str,
    model_id: str,
    collateral_type: str,
    market_value: float,
    property_type: str | None,
    property_ltv: float | None,
) -> list[tuple[str, pl.DataFrame]]:
    """Return all six artefact DataFrames for one scenario."""
    return [
        (f"counterparty_{scenario_label}", _make_counterparty(cp_ref, scenario_label)),
        (f"facility_{scenario_label}", _make_facility(fac_ref, cp_ref)),
        (f"loan_{scenario_label}", _make_loan(loan_ref, cp_ref)),
        (
            f"collateral_{scenario_label}",
            _make_collateral(
                coll_ref, collateral_type, market_value, fac_ref, property_type, property_ltv
            ),
        ),
        (f"rating_{scenario_label}", _make_rating(scenario_label, cp_ref, model_id)),
        (f"model_permission_{scenario_label}", _make_model_permission(model_id)),
    ]


def _all_scenario_artefacts() -> list[tuple[str, pl.DataFrame]]:
    """Return artefact list for all six scenarios."""
    scenarios: list[tuple] = [
        (
            "b31_thin_re",
            B31_THIN_RE_CP_REF,
            B31_THIN_RE_FAC_REF,
            B31_THIN_RE_LOAN_REF,
            B31_THIN_RE_COLL_REF,
            B31_THIN_RE_MODEL_ID,
            "real_estate",
            250_000.00,
            "residential",
            0.025,
        ),
        (
            "b31_full_re",
            B31_FULL_RE_CP_REF,
            B31_FULL_RE_FAC_REF,
            B31_FULL_RE_LOAN_REF,
            B31_FULL_RE_COLL_REF,
            B31_FULL_RE_MODEL_ID,
            "real_estate",
            10_000_000.00,
            "residential",
            1.00,
        ),
        (
            "b31_other_physical",
            B31_OTHER_PHYSICAL_CP_REF,
            B31_OTHER_PHYSICAL_FAC_REF,
            B31_OTHER_PHYSICAL_LOAN_REF,
            B31_OTHER_PHYSICAL_COLL_REF,
            B31_OTHER_PHYSICAL_MODEL_ID,
            "other_physical",
            5_000_000.00,
            None,
            None,
        ),
        (
            "b31_re_threshold_30pct",
            B31_RE_THRESHOLD_CP_REF,
            B31_RE_THRESHOLD_FAC_REF,
            B31_RE_THRESHOLD_LOAN_REF,
            B31_RE_THRESHOLD_COLL_REF,
            B31_RE_THRESHOLD_MODEL_ID,
            "real_estate",
            3_000_000.00,
            "residential",
            0.30,
        ),
        (
            "crr_thin_re",
            CRR_THIN_RE_CP_REF,
            CRR_THIN_RE_FAC_REF,
            CRR_THIN_RE_LOAN_REF,
            CRR_THIN_RE_COLL_REF,
            CRR_THIN_RE_MODEL_ID,
            "real_estate",
            250_000.00,
            "residential",
            0.025,
        ),
        (
            "crr_full_re",
            CRR_FULL_RE_CP_REF,
            CRR_FULL_RE_FAC_REF,
            CRR_FULL_RE_LOAN_REF,
            CRR_FULL_RE_COLL_REF,
            CRR_FULL_RE_MODEL_ID,
            "real_estate",
            10_000_000.00,
            "residential",
            1.00,
        ),
    ]

    result: list[tuple[str, pl.DataFrame]] = []
    for s in scenarios:
        result.extend(_artefacts_for_scenario(*s))
    return result


# ---------------------------------------------------------------------------
# Save helper
# ---------------------------------------------------------------------------


def save_p1190_fixtures(output_dir: Path | None = None) -> dict[str, Path]:
    """
    Write all P1.190 parquet files and return a mapping of name -> path.

    One parquet file is written per artefact per scenario (6 scenarios × 6 artefacts
    = 36 parquet files), written directly into output_dir.

    Args:
        output_dir: Target directory. Defaults to the package directory.

    Returns:
        dict mapping artefact name to saved Path.
    """
    if output_dir is None:
        output_dir = Path(__file__).parent

    output_dir.mkdir(parents=True, exist_ok=True)

    saved: dict[str, Path] = {}
    for name, df in _all_scenario_artefacts():
        path = output_dir / f"{name}.parquet"
        df.write_parquet(path)
        saved[name] = path

    return saved


def print_summary(saved: dict[str, Path]) -> None:
    """Print a human-readable generation summary."""
    print("P1.190 fixture generation complete")
    print("-" * 80)
    for name, path in saved.items():
        df = pl.read_parquet(path)
        print(f"  {name:<55} {df.shape[0]:>2} row(s)  ->  {path.name}")
    print("-" * 80)
    print("Scenarios: 4 Basel 3.1 + 2 CRR, all F-IRB senior corporate, PD=2%, GBP 10M")
    print()
    expected = [
        ("b31_thin_re", B31_THIN_RE_EXPECTED_LGD_STAR),
        ("b31_full_re", B31_FULL_RE_EXPECTED_LGD_STAR),
        ("b31_other_physical", B31_OTHER_PHYSICAL_EXPECTED_LGD_STAR),
        ("b31_re_threshold_30pct", B31_RE_THRESHOLD_EXPECTED_LGD_STAR),
        ("crr_thin_re", CRR_THIN_RE_EXPECTED_LGD_STAR),
        ("crr_full_re", CRR_FULL_RE_EXPECTED_LGD_STAR),
    ]
    for label, lgd_star in expected:
        print(f"  {label:<35} LGD* = {lgd_star:.6f}")


def main() -> None:
    """Entry point for standalone generation."""
    saved = save_p1190_fixtures()
    print_summary(saved)


if __name__ == "__main__":
    main()
