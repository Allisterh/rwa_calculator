"""
Generate P1.122(a) fixtures: IRB borrower + null-PD corporate guarantor → SA-fallback branch.

Pipeline position:
    fixture-builder output -> test-writer -> engine-implementer (engine/irb/guarantee.py)

Scenario design (P1.122(a) — Option A: IRB borrower + SA-fallback guarantor):

    A single F-IRB corporate borrower is fully covered by an unfunded guarantee from a
    corporate guarantor whose internal_pd is null. Because the guarantor lacks a PD, the
    engine cannot route it through IRB (PSM); it must fall back to the SA risk-weight
    substitution method (RWSM) using the guarantor's external CQS.

    The critical code path is engine/irb/guarantee.py:269-281 — the SA-fallback branch
    of the guarantor approach selection logic.

    Defect under test (pre-fix):
        Under B31 SA RWSM (PRA PS1/26 Art. 235), a corporate guarantor with CQS 3 should
        receive a risk weight of 75% (Art. 122(2) Table 6). Pre-fix, the engine uses 100%
        (CRR Table 5 value), overstating capital by GBP 250,000 on a 1m GBP exposure.

    This scenario is distinct from P1.110 (both borrower and guarantor are pure SA; no IRB
    routing at all). Here the BORROWER is IRB-eligible (F-IRB, MODEL_BORROWER_FIRB) but
    the GUARANTOR falls through to SA because its rating row carries pd=None.

    The two-config pattern (B31 vs CRR) on identical fixture data exercises:
        B31 (post-fix):  guarantor SA RW corporate CQS 3 = 75% → RWA = 750,000
        B31 (pre-fix/bug): guarantor SA RW = 100%                → RWA = 1,000,000
        CRR (regression): guarantor SA RW corporate CQS 3 = 100% → RWA = 1,000,000

Counterparties (2 rows):
    CP_BORROWER_P1122A: entity_type="company" (→ SA: CORPORATE / IRB: CORPORATE),
        annual_revenue=100,000,000 (> GBP 44m SME threshold, not SME),
        total_assets=500,000,000; default_status=False, is_financial_sector_entity=False.
    CP_GUARANTOR_P1122A: entity_type="company", annual_revenue=100,000,000,
        default_status=False, is_financial_sector_entity=False.

Ratings (2 rows):
    Borrower  (CP_BORROWER_P1122A): rating_type="internal", pd=0.02, model_id=MODEL_BORROWER_FIRB.
        Drives F-IRB routing for the borrower exposure.
    Guarantor (CP_GUARANTOR_P1122A): rating_type="external", cqs=3, pd=None (CRITICAL).
        Null PD prevents IRB routing for the guarantor → engine falls back to SA.
        CQS 3 is the discriminating value:
            B31 Art. 122(2) Table 6 → 75%   (post-fix expected)
            CRR Art. 120/122 Table 5 → 100% (pre-fix bug + CRR regression)

Facility (1 row):
    FAC_P1122A: on-balance committed term loan facility for CP_BORROWER_P1122A.

Loan (1 row):
    LOAN_P1122A: GBP 1,000,000 term loan on CP_BORROWER_P1122A.
        seniority="senior"; effective_maturity=5.0y (explicit, avoids date-arithmetic divergence).

Guarantee (1 row):
    GTE_P1122A: 100% coverage of LOAN_P1122A by CP_GUARANTOR_P1122A.
        original_maturity_years=5.0 ≥ 1.0y → satisfies Art. 237(2)(a) eligibility.
        guarantor_seniority="senior" (schema completeness; not load-bearing on SA path).
        currency="GBP" matches loan → no FX mismatch haircut.

Model permissions (1 row):
    MODEL_BORROWER_FIRB: foundation_irb for exposure_class="corporate".
        Borrower's rating row references this model_id, enabling F-IRB routing.
        Guarantor has no model_id in its rating row → cannot route IRB.

Hand-calculation:
    Loan EAD = drawn_amount + interest = 1,000,000 + 0 = 1,000,000 GBP.

    B31 path (CalculationConfig.basel_3_1()):
        Borrower: F-IRB corporate (pd=0.02, corporate F-IRB supervisory LGD=40% senior).
        Guarantor approach = SA-fallback (pd=None → no IRB path).
        Guarantor SA RW: corporate CQS 3 → Art. 122(2) Table 6 = 75% (post-fix).
        Substitution: guarantor RW 75% < borrower unguaranteed RW → use 75%.
        RWA (post-fix) = 1,000,000 × 0.75 = 750,000.
        RWA (pre-fix)  = 1,000,000 × 1.00 = 1,000,000  (engine applied CRR table value).

    CRR path (CalculationConfig.crr()):
        Guarantor SA RW: corporate CQS 3 → CRR Table 5 = 100%.
        RWA = 1,000,000 × 1.00 = 1,000,000  (CRR regression — always 100% at CQS 3).

Note: The same parquet files are used for both framework assertions. The test
parametrises the framework by passing CalculationConfig.basel_3_1() vs
CalculationConfig.crr() — fixture data is config-agnostic.

Note on rating_type: VALID_RATING_TYPES in schemas.py accepts "external" and "internal".
The guarantor's rating is "external" (Moody's) so the engine resolves it via ECRA.

References:
    - PRA PS1/26 Art. 122(2) Table 6: Basel 3.1 corporate SA risk weights by CQS
      (CQS 3 = 75%). B31 reduces CQS 3 from 100% (CRR) to 75%.
    - PRA PS1/26 Art. 235: SA risk-weight substitution method (RWSM) for guarantees.
    - CRR Art. 237(2)(a): original maturity of unfunded credit protection ≥ 1 year.
    - engine/irb/guarantee.py:269-281: SA-fallback branch of guarantor approach selection.
    - src/rwa_calc/data/schemas.py: COUNTERPARTY_SCHEMA (entity_type "company" → CORPORATE).

Usage:
    uv run python tests/fixtures/p1_122a/p1_122a.py
    uv run python tests/fixtures/p1_122a/p1_122a.py --data-dir tests/fixtures/p1_122a/data
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

from rwa_calc.data.column_spec import dtypes_of
from rwa_calc.data.schemas import (
    COUNTERPARTY_SCHEMA,
    FACILITY_SCHEMA,
    GUARANTEE_SCHEMA,
    LOAN_SCHEMA,
    MODEL_PERMISSIONS_SCHEMA,
    RATINGS_SCHEMA,
)

# ---------------------------------------------------------------------------
# Scenario constants — single source of truth for test-writer assertions
# ---------------------------------------------------------------------------

# Counterparty references
BORROWER_REF: str = "CP_BORROWER_P1122A"
GUARANTOR_REF: str = "CP_GUARANTOR_P1122A"

# Exposure references
LOAN_REF: str = "LOAN_P1122A"
FACILITY_REF: str = "FAC_P1122A"

# Guarantee reference
GUARANTEE_REF: str = "GTE_P1122A"

# Rating references
RTG_BORROWER_REF: str = "RTG_P1122A_BORR"
RTG_GUARANTOR_REF: str = "RTG_P1122A_GTR"

# Model permission ID
MODEL_ID: str = "MODEL_BORROWER_FIRB"

# Dates — Basel 3.1 effective from 1 Jan 2027
VALUE_DATE: date = date(2027, 1, 2)
MATURITY_DATE: date = date(2032, 1, 2)  # 5y residual
GUARANTEE_MATURITY_DATE: date = date(2032, 1, 2)  # matches loan — no maturity mismatch
RATING_DATE: date = date(2027, 1, 2)

# Loan economics
DRAWN_AMOUNT: float = 1_000_000.0
LOAN_INTEREST: float = 0.0
EAD: float = DRAWN_AMOUNT + LOAN_INTEREST  # 1,000,000 GBP

# Guarantee coverage (full)
AMOUNT_COVERED: float = 1_000_000.0
PERCENTAGE_COVERED: float = 1.0
ORIGINAL_MATURITY_YEARS: float = 5.0  # ≥ 1y → satisfies Art. 237(2)(a) eligibility

# Effective maturity override (avoids date-arithmetic edge cases)
EFFECTIVE_MATURITY: float = 5.0

# Counterparty financials
# annual_revenue > GBP 44m SME threshold → classified as non-SME large corporate
ANNUAL_REVENUE: float = 100_000_000.0  # GBP 100m
TOTAL_ASSETS: float = 500_000_000.0  # GBP 500m (borrower only)

# Borrower internal PD — drives F-IRB routing when model_id is present
PD_BORROWER: float = 0.02  # 2.0% — well above Basel 3.1 corporate floor 0.0005

# Guarantor CQS — the discriminating value for the SA risk weight:
#   B31 Art. 122(2) Table 6: CQS 3 → 75%   (post-fix expected)
#   CRR Table 5:             CQS 3 → 100%   (pre-fix bug + CRR regression)
GUARANTOR_CQS: int = 3

# Expected SA risk weights (assertions live in the test)
EXPECTED_GUARANTOR_RW_B31: float = 0.75  # B31 Art. 122(2) Table 6, CQS 3 — POST-FIX
EXPECTED_GUARANTOR_RW_CRR: float = 1.00  # CRR Table 5,             CQS 3 — regression

EXPECTED_RWA_B31: float = EAD * EXPECTED_GUARANTOR_RW_B31  # 750,000
EXPECTED_RWA_CRR: float = EAD * EXPECTED_GUARANTOR_RW_CRR  # 1,000,000
EXPECTED_RWA_B31_PRE_FIX: float = EAD * EXPECTED_GUARANTOR_RW_CRR  # 1,000,000 (bug)


# ---------------------------------------------------------------------------
# Minimal dataclasses for this scenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Counterparty:
    """P1.122(a) counterparty row (borrower or guarantor)."""

    counterparty_reference: str
    counterparty_name: str
    entity_type: str
    country_code: str
    annual_revenue: float | None
    total_assets: float | None
    default_status: bool
    apply_fi_scalar: bool
    is_managed_as_retail: bool
    is_financial_sector_entity: bool

    def to_dict(self) -> dict:
        return {
            "counterparty_reference": self.counterparty_reference,
            "counterparty_name": self.counterparty_name,
            "entity_type": self.entity_type,
            "country_code": self.country_code,
            "annual_revenue": self.annual_revenue,
            "total_assets": self.total_assets,
            "default_status": self.default_status,
            "apply_fi_scalar": self.apply_fi_scalar,
            "is_managed_as_retail": self.is_managed_as_retail,
            "is_financial_sector_entity": self.is_financial_sector_entity,
        }


@dataclass(frozen=True)
class _Facility:
    """
    P1.122(a) parent facility for the borrower.

    The hierarchy resolver requires a parent facility for each loan.
    seniority="senior" matches the loan.
    effective_maturity=5.0 is set explicitly to prevent date-rounding divergence
    in the IRB maturity adjustment.
    """

    facility_reference: str
    product_type: str
    book_code: str
    counterparty_reference: str
    value_date: date
    maturity_date: date
    currency: str
    limit: float
    committed: bool
    seniority: str
    effective_maturity: float

    def to_dict(self) -> dict:
        return {
            "facility_reference": self.facility_reference,
            "product_type": self.product_type,
            "book_code": self.book_code,
            "counterparty_reference": self.counterparty_reference,
            "value_date": self.value_date,
            "maturity_date": self.maturity_date,
            "currency": self.currency,
            "limit": self.limit,
            "committed": self.committed,
            "seniority": self.seniority,
            "effective_maturity": self.effective_maturity,
        }


@dataclass(frozen=True)
class _Loan:
    """
    P1.122(a) senior corporate term loan.

    seniority="senior": drives F-IRB supervisory LGD to Art. 161(1)(a) = 40% (B31).
    effective_maturity=5.0: consistent with the parent facility.
    is_payroll_loan / is_buy_to_let / is_under_construction all False — standard
    corporate loan with no special routing flags.
    """

    loan_reference: str
    product_type: str
    book_code: str
    counterparty_reference: str
    value_date: date
    maturity_date: date
    currency: str
    drawn_amount: float
    interest: float
    seniority: str
    effective_maturity: float
    is_payroll_loan: bool
    is_buy_to_let: bool
    is_under_construction: bool

    def to_dict(self) -> dict:
        return {
            "loan_reference": self.loan_reference,
            "product_type": self.product_type,
            "book_code": self.book_code,
            "counterparty_reference": self.counterparty_reference,
            "value_date": self.value_date,
            "maturity_date": self.maturity_date,
            "currency": self.currency,
            "drawn_amount": self.drawn_amount,
            "interest": self.interest,
            "seniority": self.seniority,
            "effective_maturity": self.effective_maturity,
            "is_payroll_loan": self.is_payroll_loan,
            "is_buy_to_let": self.is_buy_to_let,
            "is_under_construction": self.is_under_construction,
        }


@dataclass(frozen=True)
class _Guarantee:
    """
    P1.122(a) guarantee row: 100% unfunded corporate guarantee from CP_GUARANTOR_P1122A.

    The discriminating element is the guarantor's CQS 3 combined with pd=None in its
    rating row. The null PD prevents PSM routing — the engine must use the SA fallback
    code path (engine/irb/guarantee.py:269-281) to look up the SA corporate risk weight.

        B31 Art. 122(2) Table 6: CQS 3 → 75%   (post-fix)
        CRR Table 5:             CQS 3 → 100%   (regression)

    original_maturity_years=5.0 ≥ 1.0y → satisfies Art. 237(2)(a) eligibility.
    guarantor_seniority="senior" → satisfies schema completeness (not load-bearing here).
    currency="GBP" matches loan → no FX mismatch haircut (H_fx = 0).
    """

    guarantee_reference: str
    guarantee_type: str
    guarantor: str
    currency: str
    maturity_date: date | None
    amount_covered: float
    percentage_covered: float
    beneficiary_type: str
    beneficiary_reference: str
    protection_type: str
    includes_restructuring: bool
    original_maturity_years: float
    guarantor_seniority: str

    def to_dict(self) -> dict:
        return {
            "guarantee_reference": self.guarantee_reference,
            "guarantee_type": self.guarantee_type,
            "guarantor": self.guarantor,
            "currency": self.currency,
            "maturity_date": self.maturity_date,
            "amount_covered": self.amount_covered,
            "percentage_covered": self.percentage_covered,
            "beneficiary_type": self.beneficiary_type,
            "beneficiary_reference": self.beneficiary_reference,
            "protection_type": self.protection_type,
            "includes_restructuring": self.includes_restructuring,
            "original_maturity_years": self.original_maturity_years,
            "guarantor_seniority": self.guarantor_seniority,
        }


@dataclass(frozen=True)
class _Rating:
    """P1.122(a) rating row (internal for borrower; external for guarantor)."""

    rating_reference: str
    counterparty_reference: str
    rating_type: str
    rating_agency: str
    rating_value: str
    cqs: int | None
    pd: float | None
    rating_date: date
    is_solicited: bool
    model_id: str | None

    def to_dict(self) -> dict:
        return {
            "rating_reference": self.rating_reference,
            "counterparty_reference": self.counterparty_reference,
            "rating_type": self.rating_type,
            "rating_agency": self.rating_agency,
            "rating_value": self.rating_value,
            "cqs": self.cqs,
            "pd": self.pd,
            "rating_date": self.rating_date,
            "is_solicited": self.is_solicited,
            "model_id": self.model_id,
        }


@dataclass(frozen=True)
class _ModelPermission:
    """P1.122(a) model-permission row."""

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
# Public DataFrame factories
# ---------------------------------------------------------------------------


def create_p1122a_counterparties() -> pl.DataFrame:
    """
    Return both P1.122(a) counterparties (borrower + guarantor) as a DataFrame.

    CP_BORROWER_P1122A:
        entity_type="company" → maps to SA: CORPORATE / IRB: CORPORATE.
        annual_revenue=100,000,000 (GBP 100m) > GBP 44m → non-SME corporate.
        total_assets=500,000,000: informational only; does not affect routing.
        Borrower has a rating row with pd=0.02 and model_id=MODEL_BORROWER_FIRB
        → engine routes to F-IRB.

    CP_GUARANTOR_P1122A:
        entity_type="company" → maps to SA: CORPORATE.
        annual_revenue=100,000,000: same band as borrower; no special routing.
        Guarantor has a rating row with pd=None → engine cannot route IRB;
        falls back to SA RWSM using CQS 3.
    """
    rows = [
        _Counterparty(
            counterparty_reference=BORROWER_REF,
            counterparty_name="P1.122a Borrower Corporate GB F-IRB",
            entity_type="company",
            country_code="GB",
            annual_revenue=ANNUAL_REVENUE,
            total_assets=TOTAL_ASSETS,
            default_status=False,
            apply_fi_scalar=False,
            is_managed_as_retail=False,
            is_financial_sector_entity=False,
        ),
        _Counterparty(
            counterparty_reference=GUARANTOR_REF,
            counterparty_name="P1.122a Guarantor Corporate GB SA-fallback CQS3",
            entity_type="company",
            country_code="GB",
            annual_revenue=ANNUAL_REVENUE,
            total_assets=None,  # guarantor total_assets not needed for this scenario
            default_status=False,
            apply_fi_scalar=False,
            is_managed_as_retail=False,
            is_financial_sector_entity=False,
        ),
    ]
    return pl.DataFrame([r.to_dict() for r in rows], schema=dtypes_of(COUNTERPARTY_SCHEMA))


def create_p1122a_facility() -> pl.DataFrame:
    """
    Return the P1.122(a) parent facility as a DataFrame.

    FAC_P1122A: committed senior term loan facility for BORROWER.
    effective_maturity=5.0 matches LOAN_P1122A to prevent date-arithmetic divergence
    in the IRB maturity-adjustment calculation.
    """
    row = _Facility(
        facility_reference=FACILITY_REF,
        product_type="term_loan",
        book_code="CORP_LENDING",
        counterparty_reference=BORROWER_REF,
        value_date=VALUE_DATE,
        maturity_date=MATURITY_DATE,
        currency="GBP",
        limit=DRAWN_AMOUNT,
        committed=True,
        seniority="senior",
        effective_maturity=EFFECTIVE_MATURITY,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(FACILITY_SCHEMA))


def create_p1122a_loan() -> pl.DataFrame:
    """
    Return the P1.122(a) loan as a DataFrame.

    LOAN_P1122A: GBP 1,000,000 senior term loan on CP_BORROWER_P1122A.
    seniority="senior": drives F-IRB supervisory LGD to Art. 161(1)(a) 40% (B31).
    effective_maturity=5.0: explicit M override consistent with the parent facility.
    EAD = drawn_amount + interest = 1,000,000 + 0 = 1,000,000 GBP.
    """
    row = _Loan(
        loan_reference=LOAN_REF,
        product_type="term_loan",
        book_code="CORP_LENDING",
        counterparty_reference=BORROWER_REF,
        value_date=VALUE_DATE,
        maturity_date=MATURITY_DATE,
        currency="GBP",
        drawn_amount=DRAWN_AMOUNT,
        interest=LOAN_INTEREST,
        seniority="senior",
        effective_maturity=EFFECTIVE_MATURITY,
        is_payroll_loan=False,
        is_buy_to_let=False,
        is_under_construction=False,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(LOAN_SCHEMA))


def create_p1122a_guarantee() -> pl.DataFrame:
    """
    Return the P1.122(a) guarantee as a DataFrame.

    GTE_P1122A: 100% unfunded corporate guarantee from CP_GUARANTOR_P1122A.

    The guarantor's rating row carries pd=None — this prevents IRB routing and forces
    the engine to use the SA fallback branch in engine/irb/guarantee.py:269-281.
    The engine must look up the SA corporate risk weight using guarantor CQS 3:
        B31 Art. 122(2) Table 6: CQS 3 → 75%   (post-fix expected)
        CRR Table 5:             CQS 3 → 100%   (pre-fix bug + CRR regression)

    original_maturity_years=5.0: > 1.0y → satisfies Art. 237(2)(a) eligibility.
    currency="GBP": matches loan → H_fx = 0 (no FX mismatch haircut).
    """
    row = _Guarantee(
        guarantee_reference=GUARANTEE_REF,
        guarantee_type="guarantee",
        guarantor=GUARANTOR_REF,
        currency="GBP",
        maturity_date=GUARANTEE_MATURITY_DATE,
        amount_covered=AMOUNT_COVERED,
        percentage_covered=PERCENTAGE_COVERED,
        beneficiary_type="loan",
        beneficiary_reference=LOAN_REF,
        protection_type="guarantee",
        includes_restructuring=True,
        original_maturity_years=ORIGINAL_MATURITY_YEARS,
        guarantor_seniority="senior",
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(GUARANTEE_SCHEMA))


def create_p1122a_ratings() -> pl.DataFrame:
    """
    Return both P1.122(a) ratings as a DataFrame.

    RTG_P1122A_BORR (borrower, internal):
        rating_type="internal", pd=0.02 (2%), model_id=MODEL_BORROWER_FIRB.
        The model_id links to the model_permission row → engine routes borrower to F-IRB.
        cqs=None: internal ratings do not carry a CQS; the PD is the load-bearing value.

    RTG_P1122A_GTR (guarantor, external):
        rating_type="external", cqs=3 (BBB, Moody's), pd=None (CRITICAL).
        Null PD is the discriminating condition: the engine cannot derive a PD from this
        rating row, so it cannot route the guarantor through IRB/PSM.
        The engine's SA-fallback branch (engine/irb/guarantee.py:269-281) must read the
        guarantor's CQS and look up the SA corporate risk weight.
        model_id=None: no model permission → confirms IRB is not available.

    The combination borrower-IRB + guarantor-SA is the unique fixture of P1.122(a)
    (as opposed to P1.110, where both counterparties are pure SA).
    """
    rows = [
        _Rating(
            rating_reference=RTG_BORROWER_REF,
            counterparty_reference=BORROWER_REF,
            rating_type="internal",
            rating_agency="internal",
            rating_value="BB",  # representative mid-grade for pd=2%
            cqs=None,  # internal rating: no ECAI CQS
            pd=PD_BORROWER,
            rating_date=RATING_DATE,
            is_solicited=False,
            model_id=MODEL_ID,  # links to MODEL_BORROWER_FIRB → F-IRB routing
        ),
        _Rating(
            rating_reference=RTG_GUARANTOR_REF,
            counterparty_reference=GUARANTOR_REF,
            rating_type="external",
            rating_agency="Moody's",
            rating_value="Baa2",  # Moody's BBB equivalent → CQS 3
            cqs=GUARANTOR_CQS,  # 3 — discriminating SA risk weight value
            pd=None,  # CRITICAL: null PD → SA fallback for guarantor
            rating_date=RATING_DATE,
            is_solicited=True,
            model_id=None,  # no model_id → guarantor cannot route IRB
        ),
    ]
    return pl.DataFrame([r.to_dict() for r in rows], schema=dtypes_of(RATINGS_SCHEMA))


def create_p1122a_model_permission() -> pl.DataFrame:
    """
    Return the P1.122(a) model permission as a DataFrame.

    MODEL_BORROWER_FIRB: grants foundation_irb for exposure_class="corporate".
    Covers only the borrower (CP_BORROWER_P1122A), whose rating references this
    model_id. The guarantor's rating row has model_id=None — deliberately excluded
    to prevent IRB routing for the guarantor.
    """
    row = _ModelPermission(
        model_id=MODEL_ID,
        exposure_class="corporate",
        approach="foundation_irb",
        country_codes=None,
        excluded_book_codes=None,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(MODEL_PERMISSIONS_SCHEMA))


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------


def save_p1122a_fixtures(output_dir: Path | None = None) -> dict[str, Path]:
    """
    Write all P1.122(a) parquet files and return a mapping of name to path.

    Args:
        output_dir: Target directory. Defaults to the ``data/`` subdirectory
            next to this file (``tests/fixtures/p1_122a/data/``).

    Returns:
        dict mapping artefact name to saved Path.
    """
    if output_dir is None:
        output_dir = Path(__file__).parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    artefacts = [
        ("counterparty", create_p1122a_counterparties()),
        ("facility", create_p1122a_facility()),
        ("loan", create_p1122a_loan()),
        ("guarantee", create_p1122a_guarantee()),
        ("rating", create_p1122a_ratings()),
        ("model_permission", create_p1122a_model_permission()),
    ]

    saved: dict[str, Path] = {}
    for name, df in artefacts:
        path = output_dir / f"{name}.parquet"
        df.write_parquet(path)
        saved[name] = path

    return saved


def print_summary(saved: dict[str, Path]) -> None:
    """Print a human-readable generation summary."""
    print("P1.122(a) fixture generation complete")
    print("-" * 70)
    for name, path in saved.items():
        df = pl.read_parquet(path)
        print(f"  {name:<20} {len(df):>3} row(s)  ->  {path}")
    print("-" * 70)
    print("Scenario: IRB borrower + null-PD corporate guarantor → SA-fallback branch")
    print(
        f"  Borrower:  {BORROWER_REF} (entity_type='company', annual_revenue={ANNUAL_REVENUE:,.0f})"
    )
    print(f"             F-IRB: pd={PD_BORROWER}, model_id={MODEL_ID}")
    print(f"  Guarantor: {GUARANTOR_REF} (entity_type='company', CQS {GUARANTOR_CQS})")
    print("             SA-fallback: pd=None, model_id=None")
    print(
        f"  Loan:      {LOAN_REF}  GBP {DRAWN_AMOUNT:,.0f}, seniority=senior, M={EFFECTIVE_MATURITY}y"
    )
    print(
        f"  Guarantee: {GUARANTEE_REF}  100% coverage, original_maturity={ORIGINAL_MATURITY_YEARS}y, senior"
    )
    print()
    print("  B31 (CalculationConfig.basel_3_1()) — post-fix:")
    print(
        f"    Guarantor SA RW (corporate CQS 3, Art. 122(2) Table 6) = {EXPECTED_GUARANTOR_RW_B31:.0%}"
    )
    print(f"    Expected RWA = {EXPECTED_RWA_B31:,.0f}")
    print(
        f"    Pre-fix bug RWA = {EXPECTED_RWA_B31_PRE_FIX:,.0f}  "
        f"(overstates by {EXPECTED_RWA_B31_PRE_FIX - EXPECTED_RWA_B31:,.0f})"
    )
    print()
    print("  CRR (CalculationConfig.crr()) — regression:")
    print(f"    Guarantor SA RW (corporate CQS 3, CRR Table 5) = {EXPECTED_GUARANTOR_RW_CRR:.0%}")
    print(f"    Expected RWA = {EXPECTED_RWA_CRR:,.0f}")


def main() -> None:
    """Entry point for standalone generation."""
    output_dir = None
    if "--data-dir" in sys.argv:
        idx = sys.argv.index("--data-dir")
        output_dir = Path(sys.argv[idx + 1])

    saved = save_p1122a_fixtures(output_dir)
    print_summary(saved)


if __name__ == "__main__":
    main()
