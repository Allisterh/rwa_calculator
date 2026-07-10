"""
Generate P1.218 fixtures: guarantee coverage fraction must be measured on the
CCF=100% basis (``ead_for_crm``), not on the post-CCF ``ead_after_collateral``.

Pipeline position:
    fixture-builder output -> test-writer -> engine-implementer (crm/guarantees.py)

Key responsibilities:
- Produce two counterparty rows:
    CP_BORROWER:  corporate, GB, unrated (no rating row) -> 100% SA RW (Art. 122).
    CP_GUARANTOR: corporate, GB, CQS 1 (external rating) -> 20% SA RW (Art. 122).
- Produce one facility row (the undrawn commitment, no linked loan):
    FAC_UNDRAWN: GBP 1,000,000 limit, committed=True, risk_type="MR" (Medium
    Risk -> 50% SA CCF, CRR Art. 111/Annex I). No loan row -> drawn = 0, the
    exposure is 100% undrawn (off-balance-sheet).
- Produce one external rating row: CP_GUARANTOR, CQS 1, long-term (is_short_term
    left at schema default False -- isolates this scenario from the P1.216/
    P1.223 short-term-ECAI path).
- Produce one guarantee row: GTE_1, guarantor=CP_GUARANTOR, beneficiary_type=
    "facility", beneficiary_reference=FAC_UNDRAWN, amount_covered=400,000 GBP
    (an absolute amount, not a percentage), currency=GBP (= exposure currency,
    no FX haircut), original_maturity_years=3.0 and maturity_date equal to the
    facility's maturity_date (>= exposure maturity -> no Art. 239(3) mismatch
    scaling), attachment/detachment null (first-loss attach, no Art. 234
    tranching).

Scenario rationale (P1.218 / WS2 unfunded-protection mechanics):
    CRR Art. 235(1) (RWSM) / Art. 236(3) (PSM CCF=100% override) require that
    the covered part ``Eg = min(GA, E)`` measures the off-balance-sheet
    exposure value ``E`` BEFORE any credit conversion factor -- i.e. against
    the CCF=100% basis (``ead_for_crm`` in the engine) -- with the CCF
    re-applied to the covered/uncovered split afterwards. The pre-fix engine
    instead caps and pro-rates guarantee coverage against
    ``ead_after_collateral``, which is already post-CCF. On this fully-undrawn
    Medium-Risk (50% CCF) commitment that shrinks the coverage denominator
    from 1,000,000 to 500,000, over-recognising cover and understating RWA by
    47.06% (160,000 out of the correct 340,000).

    This fixture isolates the defect from neighbouring scenarios:
    - risk_type="MR" is set explicitly -> pins the CCF and neutralises P1.217
      (original-vs-remaining maturity CCF keying).
    - Guarantee maturity_date == facility maturity_date -> t == T -> no
      Art. 239(3) mismatch scaling -> neutralises P1.219.
    - GA (400,000) < E (1,000,000) -> the min(GA, E) cap does not bind, so
      this scenario does NOT exercise the cap-binding edge (GA > E) -- a
      separate scenario should cover that.

Hand-calculation (CRR, CalculationConfig.crr(reporting_date=date(2027, 1, 1))):

    Off-balance-sheet exposure value at CCF=100% (E):
        E = ead_for_crm = on_bs (0) + undrawn nominal (1,000,000) = 1,000,000

    CCF (Medium Risk commitment, CRR Art. 111/Annex I):
        CCF = 0.50

    Post-CCF exposure (no collateral):
        effective_ccf         = 0.50
        ead_after_collateral  = E x effective_ccf = 1,000,000 x 0.50 = 500,000

    Guarantee amount after Art. 233/239 haircuts (none apply -- same currency,
    no maturity mismatch):
        G* = amount_covered = 400,000
        GA = G* (multiplier = 1, t == T)  = 400,000

    Covered part -- measured against E at 100% (the fix, CRR Art. 235(1)):
        Eg = min(GA, E) = min(400,000, 1,000,000) = 400,000
        coverage_fraction f = Eg / E = 400,000 / 1,000,000 = 0.40

    Re-apply CCF to covered / uncovered parts (Art. 236(3)):
        Covered EAD   = f x ead_after_collateral = 0.40 x 500,000 = 200,000
        Uncovered EAD = (1 - f) x ead_after_collateral = 0.60 x 500,000 = 300,000

    Risk weights:
        guarantor RW = 0.20 (CRR Art. 122, corporate CQS 1)
        borrower  RW = 1.00 (CRR Art. 122, unrated corporate)
        substitution beneficial: 0.20 < 1.00 -> apply (Art. 213-217)

    RWA:
        Covered   RWA = 200,000 x 0.20 = 40,000
        Uncovered RWA = 300,000 x 1.00 = 300,000
        Total EAD                     = 500,000
        Total RWA = 40,000 + 300,000  = 340,000
        Blended RW = 340,000 / 500,000 = 0.68

Contrast -- pre-fix (buggy) engine output (regression sentinel, NOT the
assertion target):
    _scale      = min(1, ead_after_collateral / GA) = min(1, 500,000/400,000) = 1.0
    _effective  = GA x _scale = 400,000
    _guar_ratio = _effective / ead_after_collateral = 400,000/500,000 = 0.80  (BUG)
    guarantor sub-row EAD = _effective = 400,000
    remainder EAD = 500,000 - 400,000 = 100,000
    buggy RWA = 400,000x0.20 + 100,000x1.00 = 80,000 + 100,000 = 180,000
    buggy blended RW = 180,000 / 500,000 = 0.36
    Understatement = 340,000 - 180,000 = 160,000 (= 47.06% of the correct RWA)

EAD is invariant (500,000) between buggy and fixed -- the defect moves RWA
only, by shifting exposure from the 100% band to the 20% band.

References:
    - CRR Art. 235(1): RWSM covered part Eg = min(GA, E).
    - CRR Art. 236(3): PSM CCF=100% override when computing the covered/
      uncovered exposure-value split.
    - PS1/26 Art. 235(1)(a) / 236(1)(a): "prior to the application of any
      applicable conversion factors" (ps126app1.pdf p.213).
    - CRR Art. 111 / Annex I: SA CCF; Medium Risk commitment = 50%
      (rulebook pack packs/crr.py sa_ccf, entry "MR": 0.50).
    - CRR Art. 122: corporate risk weights (CQS 1 = 20%, unrated = 100%).
    - CRR Art. 233 / 239(3): FX and maturity-mismatch guarantee adjustments
      (both neutral in this scenario).
    - src/rwa_calc/engine/crm/collateral.py:1079-1103 (ead_after_collateral
      is the post-CCF basis; ead_for_crm is the CCF=100% basis).
    - src/rwa_calc/engine/crm/guarantees.py:647-668, 676, 916, 939-944 (the
      bug site -- coverage measured against ead_after_collateral).
    - docs/plans/compliance-audit-crr-111-241-rectification.md Section 5 WS2,
      P1.218 (lines 138-142).

Usage:
    uv run python tests/fixtures/p1_218/p1_218.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

from rwa_calc.data.column_spec import dtypes_of
from rwa_calc.data.schemas import (
    COUNTERPARTY_SCHEMA,
    FACILITY_SCHEMA,
    GUARANTEE_SCHEMA,
    RATINGS_SCHEMA,
)

# ---------------------------------------------------------------------------
# Scenario constants -- exported for test-writer assertions
# ---------------------------------------------------------------------------

# Counterparty references
BORROWER_REF = "CP_BORROWER"
GUARANTOR_REF = "CP_GUARANTOR"

# Facility (the fully-undrawn commitment) and guarantee references
FACILITY_REF = "FAC_UNDRAWN"
GUARANTEE_REF = "GTE_1"

RATING_REF = "RTG_P1218_GUARANTOR"

# Dates: reporting_date == facility value_date; maturity 3.0y out (> 1y ->
# supports the Medium-Risk >1y commitment narrative; not load-bearing given
# the explicit risk_type="MR"). Guarantee maturity_date matches the facility
# maturity_date exactly -> t == T -> no Art. 239(3) mismatch scaling.
REPORTING_DATE = date(2027, 1, 1)
VALUE_DATE = date(2027, 1, 1)
MATURITY_DATE = date(2030, 1, 1)  # exactly 3.0y from REPORTING_DATE
GUARANTEE_MATURITY_DATE = date(2030, 1, 1)  # == facility maturity -> no mismatch
RATING_DATE = date(2027, 1, 2)

# Facility economics: fully undrawn commitment, no linked loan.
FACILITY_LIMIT: float = 1_000_000.0  # E = ead_for_crm (CCF=100% basis)
RISK_TYPE: str = "MR"  # Medium Risk commitment -> 50% SA CCF (CRR Art. 111/Annex I)
CCF_MR: float = 0.50

# Guarantee economics.
AMOUNT_COVERED: float = 400_000.0  # GA -- absolute amount, not percentage_covered
ORIGINAL_MATURITY_YEARS: float = 3.0  # >= 1.0 -> passes Art. 237(2)(a) eligibility

# Guarantor rating.
GUARANTOR_CQS: int = 1
_GUARANTOR_RATING_VALUE = "AA"  # CQS 1: AAA-AA-
RATING_AGENCY = "S&P"

# ---------------------------------------------------------------------------
# Expected outputs (post-fix) -- anchors for test-writer assertions
# ---------------------------------------------------------------------------

# E = ead_for_crm = on_bs (0) + undrawn nominal (1,000,000)
EXPOSURE_VALUE_AT_CCF_100: float = FACILITY_LIMIT  # 1,000,000

# ead_after_collateral = E x CCF (no collateral -> effective_ccf == CCF_MR)
EXPECTED_EAD_AFTER_COLLATERAL: float = EXPOSURE_VALUE_AT_CCF_100 * CCF_MR  # 500,000

# GA (no FX/maturity-mismatch haircuts apply)
EXPECTED_GA: float = AMOUNT_COVERED  # 400,000

# Eg = min(GA, E); coverage fraction measured against E (the CCF=100% basis)
EXPECTED_EG: float = min(EXPECTED_GA, EXPOSURE_VALUE_AT_CCF_100)  # 400,000
EXPECTED_COVERAGE_FRACTION: float = EXPECTED_EG / EXPOSURE_VALUE_AT_CCF_100  # 0.40

# CCF re-applied to the covered/uncovered split (Art. 236(3))
EXPECTED_COVERED_EAD: float = EXPECTED_COVERAGE_FRACTION * EXPECTED_EAD_AFTER_COLLATERAL  # 200,000
EXPECTED_UNCOVERED_EAD: float = EXPECTED_EAD_AFTER_COLLATERAL - EXPECTED_COVERED_EAD  # 300,000

# Risk weights (CRR Art. 122)
EXPECTED_GUARANTOR_RW: float = 0.20  # corporate CQS 1
EXPECTED_BORROWER_RW: float = 1.00  # unrated corporate

# RWA (post-fix, the correct hand-calculated result)
EXPECTED_COVERED_RWA: float = EXPECTED_COVERED_EAD * EXPECTED_GUARANTOR_RW  # 40,000
EXPECTED_UNCOVERED_RWA: float = EXPECTED_UNCOVERED_EAD * EXPECTED_BORROWER_RW  # 300,000
EXPECTED_TOTAL_EAD: float = EXPECTED_EAD_AFTER_COLLATERAL  # 500,000 (invariant vs bug)
EXPECTED_TOTAL_RWA: float = EXPECTED_COVERED_RWA + EXPECTED_UNCOVERED_RWA  # 340,000
EXPECTED_BLENDED_RW: float = EXPECTED_TOTAL_RWA / EXPECTED_TOTAL_EAD  # 0.68

# --- Pre-fix (buggy) contrastive values -- regression sentinel, NOT the target ---
# _scale = min(1, ead_after_collateral / GA); _guar_ratio computed against
# ead_after_collateral instead of ead_for_crm (the bug).
_BUGGY_SCALE: float = min(1.0, EXPECTED_EAD_AFTER_COLLATERAL / EXPECTED_GA)  # 1.0
BUGGY_EFFECTIVE_AMOUNT: float = EXPECTED_GA * _BUGGY_SCALE  # 400,000
BUGGY_GUAR_RATIO: float = BUGGY_EFFECTIVE_AMOUNT / EXPECTED_EAD_AFTER_COLLATERAL  # 0.80
BUGGY_COVERED_EAD: float = BUGGY_EFFECTIVE_AMOUNT  # 400,000
BUGGY_REMAINDER_EAD: float = EXPECTED_EAD_AFTER_COLLATERAL - BUGGY_EFFECTIVE_AMOUNT  # 100,000
BUGGY_TOTAL_RWA: float = (
    BUGGY_COVERED_EAD * EXPECTED_GUARANTOR_RW + BUGGY_REMAINDER_EAD * EXPECTED_BORROWER_RW
)  # 180,000
BUGGY_BLENDED_RW: float = BUGGY_TOTAL_RWA / EXPECTED_TOTAL_EAD  # 0.36
UNDERSTATEMENT: float = EXPECTED_TOTAL_RWA - BUGGY_TOTAL_RWA  # 160,000


# ---------------------------------------------------------------------------
# Minimal dataclasses for this scenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Counterparty:
    """
    P1.218 counterparty row (borrower or guarantor).

    Both are entity_type="corporate" -- the borrower is unrated (no rating
    row -> 100% SA RW, Art. 122) and the guarantor is CQS 1 rated via a
    separate ratings row (-> 20% SA RW, Art. 122).
    """

    counterparty_reference: str
    counterparty_name: str
    entity_type: str
    country_code: str
    default_status: bool
    apply_fi_scalar: bool

    def to_dict(self) -> dict:
        return {
            "counterparty_reference": self.counterparty_reference,
            "counterparty_name": self.counterparty_name,
            "entity_type": self.entity_type,
            "country_code": self.country_code,
            "default_status": self.default_status,
            "apply_fi_scalar": self.apply_fi_scalar,
        }


@dataclass(frozen=True)
class _Facility:
    """
    P1.218 facility: the fully-undrawn committed Medium-Risk commitment.

    limit=1,000,000: no linked loan -> drawn=0, the entire limit is the
    undrawn (off-balance-sheet) nominal amount -- E at CCF=100%
    (``ead_for_crm``) in the hand-calc.
    committed=True: genuine commitment (not conditionally cancellable).
    risk_type="MR": Medium Risk -> 50% SA CCF (CRR Art. 111/Annex I). Set
    explicitly to pin the CCF and isolate this scenario from P1.217
    (original-vs-remaining maturity CCF keying).
    maturity_date=2030-01-01: 3.0y original maturity (> 1yr) -- supports the
    MR classification narrative; not load-bearing given the explicit
    risk_type.
    """

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
class _Rating:
    """P1.218 external ECAI rating: guarantor only, long-term, CQS 1."""

    rating_reference: str
    counterparty_reference: str
    rating_type: str
    rating_agency: str
    rating_value: str
    cqs: int
    pd: float | None
    rating_date: date
    is_solicited: bool
    model_id: str | None
    is_short_term: bool

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
            "is_short_term": self.is_short_term,
        }


@dataclass(frozen=True)
class _Guarantee:
    """
    P1.218 guarantee row: single unfunded SA guarantee covering the facility.

    amount_covered=400,000 (absolute amount, not percentage_covered) so
    coverage is a nominal credit-protection value, per the scenario proposal.
    beneficiary_type="facility" attaches the guarantee to FAC_UNDRAWN.
    currency="GBP" == exposure currency -> no FX haircut (Art. 233).
    original_maturity_years=3.0 and maturity_date == facility maturity_date
    -> t == T -> no Art. 239(3) maturity-mismatch scaling (GA = G* = 400,000).
    attachment_amount / detachment_amount left null (schema default) ->
    first-loss attach (a = 0), no Art. 234 tranching.
    """

    guarantee_reference: str
    guarantee_type: str
    guarantor: str
    currency: str
    maturity_date: date
    amount_covered: float
    beneficiary_type: str
    beneficiary_reference: str
    protection_type: str
    includes_restructuring: bool
    original_maturity_years: float

    def to_dict(self) -> dict:
        return {
            "guarantee_reference": self.guarantee_reference,
            "guarantee_type": self.guarantee_type,
            "guarantor": self.guarantor,
            "currency": self.currency,
            "maturity_date": self.maturity_date,
            "amount_covered": self.amount_covered,
            "beneficiary_type": self.beneficiary_type,
            "beneficiary_reference": self.beneficiary_reference,
            "protection_type": self.protection_type,
            "includes_restructuring": self.includes_restructuring,
            "original_maturity_years": self.original_maturity_years,
        }


# ---------------------------------------------------------------------------
# Public DataFrame factories
# ---------------------------------------------------------------------------


def create_p1218_counterparties() -> pl.DataFrame:
    """
    Return the two P1.218 counterparty rows (borrower + guarantor) as a DataFrame.

    CP_BORROWER:  corporate, GB, unrated (no rating row) -> 100% SA RW.
    CP_GUARANTOR: corporate, GB, CQS 1 (external rating) -> 20% SA RW.
    """
    rows = [
        _Counterparty(
            counterparty_reference=BORROWER_REF,
            counterparty_name="P1.218 Borrower Corporate GB Unrated",
            entity_type="corporate",
            country_code="GB",
            default_status=False,
            apply_fi_scalar=False,
        ),
        _Counterparty(
            counterparty_reference=GUARANTOR_REF,
            counterparty_name="P1.218 Guarantor Corporate GB CQS1",
            entity_type="corporate",
            country_code="GB",
            default_status=False,
            apply_fi_scalar=False,
        ),
    ]
    return pl.DataFrame([r.to_dict() for r in rows], schema=dtypes_of(COUNTERPARTY_SCHEMA))


def create_p1218_facilities() -> pl.DataFrame:
    """
    Return the P1.218 facility row as a DataFrame.

    FAC_UNDRAWN: GBP 1,000,000 committed, fully undrawn (no loan row),
    risk_type="MR" (50% SA CCF). This is the sole exposure for CP_BORROWER.
    """
    row = _Facility(
        facility_reference=FACILITY_REF,
        counterparty_reference=BORROWER_REF,
        currency="GBP",
        value_date=VALUE_DATE,
        maturity_date=MATURITY_DATE,
        limit=FACILITY_LIMIT,
        committed=True,
        seniority="senior",
        risk_type=RISK_TYPE,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(FACILITY_SCHEMA))


def create_p1218_ratings() -> pl.DataFrame:
    """
    Return the P1.218 guarantor external rating as a DataFrame.

    CP_GUARANTOR: CQS 1 / S&P AA -> 20% SA corporate RW (Art. 122).
    is_short_term=False (schema default kept explicit): a long-term rating
    keeps this scenario clear of the P1.216/P1.223 short-term-ECAI path.
    No rating row for CP_BORROWER -- unrated -> 100% RW.
    """
    row = _Rating(
        rating_reference=RATING_REF,
        counterparty_reference=GUARANTOR_REF,
        rating_type="external",
        rating_agency=RATING_AGENCY,
        rating_value=_GUARANTOR_RATING_VALUE,
        cqs=GUARANTOR_CQS,
        pd=None,
        rating_date=RATING_DATE,
        is_solicited=True,
        model_id=None,
        is_short_term=False,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(RATINGS_SCHEMA))


def create_p1218_guarantees() -> pl.DataFrame:
    """
    Return the P1.218 guarantee row as a DataFrame.

    GTE_1: CP_GUARANTOR covers GBP 400,000 (absolute amount) of FAC_UNDRAWN.
    Same currency (GBP), no maturity mismatch (guarantee maturity_date ==
    facility maturity_date) -> GA = amount_covered = 400,000 unchanged.
    """
    row = _Guarantee(
        guarantee_reference=GUARANTEE_REF,
        guarantee_type="guarantee",
        guarantor=GUARANTOR_REF,
        currency="GBP",
        maturity_date=GUARANTEE_MATURITY_DATE,
        amount_covered=AMOUNT_COVERED,
        beneficiary_type="facility",
        beneficiary_reference=FACILITY_REF,
        protection_type="guarantee",
        includes_restructuring=False,
        original_maturity_years=ORIGINAL_MATURITY_YEARS,
    )
    return pl.DataFrame([row.to_dict()], schema=dtypes_of(GUARANTEE_SCHEMA))


# ---------------------------------------------------------------------------
# Save helpers (one parquet per artefact type)
# ---------------------------------------------------------------------------


def save_p1218_fixtures(output_dir: Path | None = None) -> dict[str, Path]:
    """
    Write all P1.218 parquet files and return a mapping of name -> path.

    Files produced:
        counterparty.parquet  -- 2 rows (CP_BORROWER, CP_GUARANTOR)
        facility.parquet      -- 1 row  (FAC_UNDRAWN, GBP 1,000,000, MR, no loan)
        rating.parquet        -- 1 row  (CP_GUARANTOR, CQS 1)
        guarantee.parquet     -- 1 row  (GTE_1, amount_covered=400,000)

    Args:
        output_dir: Target directory. Defaults to the package directory.

    Returns:
        dict mapping artefact name to saved Path.
    """
    if output_dir is None:
        output_dir = Path(__file__).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    artefacts: list[tuple[str, pl.DataFrame]] = [
        ("counterparty", create_p1218_counterparties()),
        ("facility", create_p1218_facilities()),
        ("rating", create_p1218_ratings()),
        ("guarantee", create_p1218_guarantees()),
    ]

    saved: dict[str, Path] = {}
    for name, df in artefacts:
        path = output_dir / f"{name}.parquet"
        df.write_parquet(path)
        saved[name] = path

    return saved


def print_summary(saved: dict[str, Path]) -> None:
    """Print a human-readable generation summary."""
    print("P1.218 fixture generation complete")
    print("-" * 70)
    for name, path in saved.items():
        df = pl.read_parquet(path)
        print(f"  {name:<20} {len(df):>3} row(s)  ->  {path}")
    print("-" * 70)
    print("Scenario: guarantee coverage fraction measured on CCF=100% basis (Art. 235(1)/236(3))")
    print(f"  Borrower:  {BORROWER_REF} (corporate, unrated, RW={EXPECTED_BORROWER_RW:.0%})")
    print(f"  Guarantor: {GUARANTOR_REF} (corporate, CQS 1, RW={EXPECTED_GUARANTOR_RW:.0%})")
    print(
        f"  Facility:  {FACILITY_REF}  GBP {FACILITY_LIMIT:,.0f}  risk_type={RISK_TYPE}  (no loan)"
    )
    print(f"  Guarantee: {GUARANTEE_REF}  amount_covered=GBP {AMOUNT_COVERED:,.0f}")
    print()
    print(f"  E (ead_for_crm, CCF=100%)   = {EXPOSURE_VALUE_AT_CCF_100:,.0f}")
    print(f"  ead_after_collateral (CCF=50%) = {EXPECTED_EAD_AFTER_COLLATERAL:,.0f}")
    print(f"  GA = {EXPECTED_GA:,.0f}; Eg = min(GA, E) = {EXPECTED_EG:,.0f}")
    print(f"  coverage_fraction f = Eg / E = {EXPECTED_COVERAGE_FRACTION:.2f}")
    print(
        f"  Covered EAD   = {EXPECTED_COVERED_EAD:,.0f}  x RW {EXPECTED_GUARANTOR_RW:.0%} = "
        f"{EXPECTED_COVERED_RWA:,.0f}"
    )
    print(
        f"  Uncovered EAD = {EXPECTED_UNCOVERED_EAD:,.0f}  x RW {EXPECTED_BORROWER_RW:.0%} = "
        f"{EXPECTED_UNCOVERED_RWA:,.0f}"
    )
    print(
        f"  Total EAD = {EXPECTED_TOTAL_EAD:,.0f}  Total RWA = {EXPECTED_TOTAL_RWA:,.0f}  "
        f"Blended RW = {EXPECTED_BLENDED_RW:.4f}"
    )
    print()
    print(
        f"  Pre-fix (buggy) total RWA = {BUGGY_TOTAL_RWA:,.0f}  "
        f"(understated by {UNDERSTATEMENT:,.0f} = "
        f"{UNDERSTATEMENT / EXPECTED_TOTAL_RWA:.4%})"
    )


def main() -> None:
    """Entry point for standalone generation."""
    saved = save_p1218_fixtures()
    print_summary(saved)


if __name__ == "__main__":
    main()
