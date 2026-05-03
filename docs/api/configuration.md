# Configuration API

The configuration module provides immutable dataclasses for controlling calculation
behavior. All configurations are frozen (`@dataclass(frozen=True)`) and use factory
methods for self-documenting creation.

## Module: `rwa_calc.contracts.config`

### `PolarsEngine`

```python
PolarsEngine = Literal["cpu", "gpu", "streaming"]
```

Type alias controlling the Polars collection engine. `"streaming"` (default) processes
in batches for lower memory usage; `"cpu"` loads everything into memory.

### `CalculationConfig`

Master configuration for RWA calculations. Bundles all framework-specific settings.
Use factory methods `.crr()` and `.basel_3_1()` instead of constructing directly.

```python
@dataclass(frozen=True)
class CalculationConfig:
    """
    Attributes:
        framework: Regulatory framework (CRR or BASEL_3_1).
        reporting_date: As-of date for the calculation.
        base_currency: Currency for reporting (default "GBP").
        apply_fx_conversion: Whether to convert exposures to base_currency.
        pd_floors: PD floor configuration.
        lgd_floors: LGD floor configuration (A-IRB).
        supporting_factors: SME/infrastructure factors.
        output_floor: Output floor configuration.
        retail_thresholds: Retail classification thresholds.
        permission_mode: STANDARDISED (all SA) or IRB (model permissions drive routing).
        scaling_factor: 1.06 scaling for IRB K (CRR Art. 153), 1.0 for Basel 3.1.
        eur_gbp_rate: EUR/GBP exchange rate for threshold conversion.
        collect_engine: Polars engine for .collect() — "cpu" (default).
    """

    framework: RegulatoryFramework
    reporting_date: date
    base_currency: str = "GBP"
    apply_fx_conversion: bool = True
    pd_floors: PDFloors
    lgd_floors: LGDFloors
    supporting_factors: SupportingFactors
    output_floor: OutputFloorConfig
    retail_thresholds: RetailThresholds
    permission_mode: PermissionMode = PermissionMode.STANDARDISED
    scaling_factor: Decimal = Decimal("1.06")
    eur_gbp_rate: Decimal = Decimal("0.8732")
    collect_engine: PolarsEngine = "cpu"
    spill_dir: Path | None = None
```

#### Properties

```python
    @property
    def is_crr(self) -> bool:
        """Check if using CRR framework."""

    @property
    def is_basel_3_1(self) -> bool:
        """Check if using Basel 3.1 framework."""

    def get_output_floor_percentage(self) -> Decimal:
        """Get the applicable output floor percentage for the reporting date."""
```

#### Factory Methods

```python
    @classmethod
    def crr(
        cls,
        reporting_date: date,
        permission_mode: PermissionMode = PermissionMode.STANDARDISED,
        eur_gbp_rate: Decimal = Decimal("0.8732"),
        enable_double_default: bool = False,
        crm_collateral_method: CRMCollateralMethod = CRMCollateralMethod.COMPREHENSIVE,
        collect_engine: PolarsEngine = "cpu",
        spill_dir: Path | None = None,
        log_level: str = "INFO",
        log_format: Literal["text", "json"] = "text",
    ) -> CalculationConfig:
        """
        Create CRR (Basel 3.0) configuration.

        CRR characteristics:
        - Single PD floor (0.03%) for all classes
        - No LGD floors for A-IRB
        - SME supporting factor (0.7619/0.85)
        - Infrastructure supporting factor (0.75)
        - No output floor
        - 1.06 scaling factor for IRB K
        - Optional double-default treatment (Art. 153(3), 202)
        """

    @classmethod
    def basel_3_1(
        cls,
        reporting_date: date,
        permission_mode: PermissionMode = PermissionMode.STANDARDISED,
        post_model_adjustments: PostModelAdjustmentConfig | None = None,
        use_investment_grade_assessment: bool = False,
        institution_type: InstitutionType | None = None,
        reporting_basis: ReportingBasis | None = None,
        gcra_amount: float = 0.0,
        sa_t2_credit: float = 0.0,
        art_40_deductions: float = 0.0,
        skip_transitional_floor: bool = False,
        crm_collateral_method: CRMCollateralMethod = CRMCollateralMethod.COMPREHENSIVE,
        airb_collateral_method: AIRBCollateralMethod = AIRBCollateralMethod.LGD_MODELLING,
        collect_engine: PolarsEngine = "cpu",
        spill_dir: Path | None = None,
        log_level: str = "INFO",
        log_format: Literal["text", "json"] = "text",
    ) -> CalculationConfig:
        """
        Create Basel 3.1 (PRA PS1/26) configuration.

        Basel 3.1 characteristics:
        - Differentiated PD floors by exposure class
        - LGD floors for A-IRB by collateral type
        - No supporting factors
        - Output floor (72.5%, transitional from 60% in 2027)
        - 1.06 scaling factor removed
        """
```

The full keyword list for each factory:

| Argument | `crr()` | `basel_3_1()` | Knob it controls |
|---|---|---|---|
| `reporting_date` | required | required | as-of date |
| `permission_mode` | yes | yes | SA-only vs IRB routing |
| `eur_gbp_rate` | yes | n/a (GBP-native) | CRR EUR-threshold FX |
| `enable_double_default` | yes | n/a (Art. 153(3) blanked) | CRR Art. 153(3) — see [`enable_double_default`](#enable_double_default) |
| `use_investment_grade_assessment` | n/a | yes | Art. 122(6)/(8) — see [`use_investment_grade_assessment`](#use_investment_grade_assessment) |
| `crm_collateral_method` | yes | yes | Art. 191A SA financial collateral — see [`crm_collateral_method`](#crm_collateral_method) |
| `airb_collateral_method` | n/a | yes | Art. 169A/169B A-IRB collateral — see [`airb_collateral_method`](#airb_collateral_method) |
| `post_model_adjustments` | n/a | yes | Art. 153(5A)/154(4A)/158(6A) PMAs |
| `institution_type` | n/a | yes | Art. 92 para 2A floor applicability |
| `reporting_basis` | n/a | yes | Art. 92 para 2A floor applicability |
| `gcra_amount` / `sa_t2_credit` / `art_40_deductions` | n/a | yes | OF-ADJ inputs (Art. 92 para 2A) |
| `skip_transitional_floor` | n/a | yes | Art. 92 para 5 — bypass 60/65/70% phase-in |
| `collect_engine` / `spill_dir` | yes | yes | Polars engine |
| `log_level` / `log_format` | yes | yes | observability |

#### Factory Overrides — Worked Examples

The factories return a fully-configured `CalculationConfig`; pass keyword
overrides to flip a knob on one factory call rather than constructing the
config by hand. For knobs that the factory does **not** expose (e.g. equity
transitionals, raw `output_floor` field swaps), use `dataclasses.replace`
on the returned config — see [Replace-based overrides](#replace-based-overrides)
below.

##### CRR — toggle double-default and the SA financial collateral method

```python
from datetime import date
from decimal import Decimal
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import CRMCollateralMethod, PermissionMode

# CRR baseline with Art. 153(3) double-default *and* the Art. 222 simple
# financial collateral method on the SA leg, plus a non-default EUR/GBP
# rate for retail / SME threshold conversion.
config = CalculationConfig.crr(
    reporting_date=date(2026, 12, 31),
    permission_mode=PermissionMode.IRB,
    eur_gbp_rate=Decimal("0.8800"),
    enable_double_default=True,                              # Art. 153(3)
    crm_collateral_method=CRMCollateralMethod.SIMPLE,        # Art. 222 (SA-only)
    log_format="json",                                       # audit-ready logs
)

assert config.is_crr
assert config.enable_double_default is True
assert config.crm_collateral_method is CRMCollateralMethod.SIMPLE
```

See the per-knob sections for regulatory derivation:
[`enable_double_default`](#enable_double_default),
[`crm_collateral_method`](#crm_collateral_method).

##### Basel 3.1 — Art. 122(6)/(8) IG assessment + Foundation A-IRB collateral + skip-transitional floor

```python
from datetime import date
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import (
    AIRBCollateralMethod,
    CRMCollateralMethod,
    InstitutionType,
    PermissionMode,
    ReportingBasis,
)

# Stand-alone UK IRB firm, individual basis, electing:
# - Art. 122(6)(b)/(8)(b) IG vs non-IG split for unrated corporates
# - Art. 191A Part 2 / Art. 169A election to use the Foundation
#   Collateral Method on the A-IRB book
# - Art. 222 Simple Method on the SA financial collateral book
# - Art. 92 para 5 voluntary skip of the 60/65/70% transitional → 72.5%
#   from day one
config = CalculationConfig.basel_3_1(
    reporting_date=date(2027, 6, 30),
    permission_mode=PermissionMode.IRB,
    use_investment_grade_assessment=True,                          # Art. 122(6)/(8)
    airb_collateral_method=AIRBCollateralMethod.FOUNDATION,        # Art. 169A
    crm_collateral_method=CRMCollateralMethod.SIMPLE,              # Art. 222
    institution_type=InstitutionType.STANDALONE_UK,                # Art. 92 para 2A(a)(i)
    reporting_basis=ReportingBasis.INDIVIDUAL,
    skip_transitional_floor=True,                                  # Art. 92 para 5
)

assert config.is_basel_3_1
assert config.use_investment_grade_assessment is True
assert config.airb_collateral_method is AIRBCollateralMethod.FOUNDATION
assert config.crm_collateral_method is CRMCollateralMethod.SIMPLE
assert config.output_floor.is_floor_applicable() is True
assert config.get_output_floor_percentage() == Decimal("0.725")    # phased-in from day one
```

See the per-knob sections for regulatory derivation:
[`use_investment_grade_assessment`](#use_investment_grade_assessment),
[`airb_collateral_method`](#airb_collateral_method),
[`crm_collateral_method`](#crm_collateral_method).

##### Replace-based overrides

A small number of fields are not exposed as factory keywords because they
are derived from other config (`pd_floors`, `lgd_floors`, `thresholds`,
`equity_transitional`, the raw `output_floor` dataclass, `scaling_factor`,
`apply_fx_conversion`, `sync_eur_gbp_rate_from_fx_table`). For test
harnesses or research workflows that need to swap one of these, build the
config from the factory and use `dataclasses.replace`:

```python
from dataclasses import replace
from datetime import date
from decimal import Decimal
from rwa_calc.contracts.config import CalculationConfig, PDFloors

config = CalculationConfig.basel_3_1(reporting_date=date(2027, 6, 30))

# Tighten the corporate PD floor for a stress scenario without
# disturbing any other framework defaults.
stressed_floors = replace(config.pd_floors, corporate=Decimal("0.0010"))
config = replace(config, pd_floors=stressed_floors)

assert config.pd_floors.corporate == Decimal("0.0010")
```

`replace(...)` returns a new frozen instance — the original config is
untouched, preserving the immutability contract.

### `PDFloors`

PD floor values by exposure class. All values expressed as decimals (e.g., 0.0003 = 0.03%).

```python
@dataclass(frozen=True)
class PDFloors:
    """
    Under CRR: Single floor of 0.03% for all exposures (Art. 163).
    Under Basel 3.1: Differentiated floors (CRE30.55, PS1/26 Ch.5).
    """

    corporate: Decimal = Decimal("0.0003")          # 0.03%
    corporate_sme: Decimal = Decimal("0.0003")       # 0.03%
    retail_mortgage: Decimal = Decimal("0.0003")     # 0.03%
    retail_other: Decimal = Decimal("0.0003")        # 0.03%
    retail_qrre_transactor: Decimal = Decimal("0.0003")  # 0.03%
    retail_qrre_revolver: Decimal = Decimal("0.0003")    # 0.03%

    def get_floor(
        self,
        exposure_class: ExposureClass,
        is_qrre_transactor: bool = False,
    ) -> Decimal:
        """Get the PD floor for a given exposure class.

        For RETAIL_QRRE, distinguish transactors vs revolvers via is_qrre_transactor.
        """

    @classmethod
    def crr(cls) -> PDFloors:
        """CRR PD floors: single 0.03% floor for all classes."""

    @classmethod
    def basel_3_1(cls) -> PDFloors:
        """Basel 3.1 PD floors: differentiated by class (CRE30.55).

        - Corporate/Corporate SME: 0.05%
        - Retail mortgage: 0.10%
        - Retail other: 0.05%
        - QRRE transactors: 0.05%
        - QRRE revolvers: 0.10%
        """
```

### `LGDFloors`

LGD floor values by collateral type for A-IRB. Per-exposure input floors are only applicable
under Basel 3.1 (CRE30.41, PS1/26 Ch.5). CRR Art. 164(4) has portfolio-level floors (10% RRE,
15% CRE exposure-weighted average) but no per-exposure input floors — the calculator's
`LGDFloors.crr()` returns all zeros (see D3.38).

```python
@dataclass(frozen=True)
class LGDFloors:
    unsecured: Decimal = Decimal("0.25")                  # 25% (Art. 161(5)(a))
    subordinated_unsecured: Decimal = Decimal("0.50")      # WRONG: should be 0.25 (see warning)
    financial_collateral: Decimal = Decimal("0.0")         # 0%
    receivables: Decimal = Decimal("0.10")                 # 10%
    commercial_real_estate: Decimal = Decimal("0.10")      # 10%
    residential_real_estate: Decimal = Decimal("0.10")     # 10% (corporate, Art. 161(5))
    other_physical: Decimal = Decimal("0.15")              # 15%

    def get_floor(self, collateral_type: CollateralType) -> Decimal:
        """Get the LGD floor for a given collateral type.
        Defaults to unsecured floor for unknown types."""

    @classmethod
    def crr(cls) -> LGDFloors:
        """CRR: No LGD floors (all zero)."""

    @classmethod
    def basel_3_1(cls) -> LGDFloors:
        """Basel 3.1 LGD floors (CRE30.41).
        Note: Values reflect PRA implementation."""
```

!!! warning "Code Divergence: subordinated_unsecured should be 0.25, not 0.50"
    Art. 161(5)(a) sets a flat 25% for **all** corporate unsecured exposures — no
    senior/subordinated distinction. The `subordinated_unsecured = 0.50` has **no regulatory
    basis** and overstates the LGD floor for subordinated corporate exposures in the fallback
    path (when `exposure_class` is unavailable but `seniority` is present). The correct value
    is `Decimal("0.25")`, matching the `unsecured` field.

    **Impact:** When input data includes a `seniority` column but no `exposure_class` column,
    subordinated exposures receive a 50% LGD floor instead of the correct 25%
    (`formulas.py:164,220`). When `exposure_class` IS present (the normal pipeline path),
    the code correctly applies 25% regardless of seniority.

    The 50% figure coincides with retail QRRE unsecured (Art. 164(4)(b)(i)) but that floor
    applies only to qualifying revolving retail exposures, not corporate subordinated debt.
    See [A-IRB LGD Floors](../specifications/crr/airb-calculation.md#lgd-floors-basel-31-only)
    for the regulatory basis.

### `SupportingFactors`

Supporting factors for CRR (SME and infrastructure). Basel 3.1 removes these.

```python
@dataclass(frozen=True)
class SupportingFactors:
    """
    SME Supporting Factor (CRR Art. 501):
        Factor 1: 0.7619 for exposure up to EUR 2.5m
        Factor 2: 0.85 for exposure above EUR 2.5m

    Infrastructure Supporting Factor (CRR Art. 501a):
        Factor: 0.75
    """

    sme_factor_under_threshold: Decimal = Decimal("0.7619")
    sme_factor_above_threshold: Decimal = Decimal("0.85")
    sme_exposure_threshold_eur: Decimal = Decimal("2500000")   # EUR 2.5m
    sme_turnover_threshold_eur: Decimal = Decimal("50000000")  # EUR 50m
    infrastructure_factor: Decimal = Decimal("0.75")
    enabled: bool = True

    @classmethod
    def crr(cls) -> SupportingFactors:
        """CRR supporting factors enabled."""

    @classmethod
    def basel_3_1(cls) -> SupportingFactors:
        """Basel 3.1: Supporting factors disabled (all 1.0)."""
```

### `OutputFloorConfig`

Output floor configuration for Basel 3.1. The output floor (CRE99.1-8, PS1/26 Ch.12)
requires IRB RWAs to be at least 72.5% of the equivalent SA RWAs.

```python
@dataclass(frozen=True)
class OutputFloorConfig:
    enabled: bool = False
    floor_percentage: Decimal = Decimal("0.725")  # 72.5%
    transitional_start_date: date | None = None
    transitional_end_date: date | None = None
    transitional_floor_schedule: dict[date, Decimal] = field(default_factory=dict)

    def get_floor_percentage(self, calculation_date: date) -> Decimal:
        """Get the applicable floor percentage for a given date.

        Returns 0% if floor is disabled or the calculation date precedes
        the transitional start date (PS1/26: 1 Jan 2027 for UK firms).

        Transitional schedule:
        PRA compressed schedule (4-year, not BCBS 6-year):
        - 2027: 60%
        - 2028: 65%
        - 2029: 70%
        - 2030+: 72.5%
        """

    @classmethod
    def crr(cls) -> OutputFloorConfig:
        """CRR: No output floor."""

    @classmethod
    def basel_3_1(cls) -> OutputFloorConfig:
        """Basel 3.1 output floor with PRA transitional schedule."""
```

### `RetailThresholds`

Thresholds for retail exposure classification. Different thresholds apply under
CRR vs Basel 3.1.

```python
@dataclass(frozen=True)
class RetailThresholds:
    # Maximum aggregated exposure to qualify as retail
    max_exposure_threshold: Decimal = Decimal("1000000")  # GBP 1m (CRR)

    # QRRE specific limits
    qrre_max_limit: Decimal = Decimal("100000")  # GBP 100k

    @classmethod
    def crr(cls, eur_gbp_rate: Decimal = Decimal("0.8732")) -> RetailThresholds:
        """CRR retail thresholds (converted from EUR dynamically).

        Args:
            eur_gbp_rate: EUR/GBP exchange rate for threshold conversion.

        CRR thresholds (EUR):
        - Max exposure: EUR 1m (converted to GBP)
        - QRRE max limit: EUR 100k (converted to GBP)
        """

    @classmethod
    def basel_3_1(cls) -> RetailThresholds:
        """Basel 3.1 retail thresholds (GBP).

        - Max exposure: GBP 880k
        - QRRE max limit: GBP 100k
        """
```

### `PermissionMode`

High-level permission mode controlling whether the firm uses SA for all
exposures or routes exposures to IRB based on model-level permissions.

```python
class PermissionMode(StrEnum):
    STANDARDISED = "standardised"
    IRB = "irb"
```

| Mode | Behaviour |
|------|-----------|
| `STANDARDISED` | All exposures use the Standardised Approach. No IRB routing. |
| `IRB` | Approach routing is driven by the `model_permissions` input table. Each model's approved approach (AIRB, FIRB, slotting) is resolved per-exposure. Exposures without a matching model permission fall back to SA. If no `model_permissions` file is provided, **all exposures fall back to SA** with a warning. |

!!! note "Model permissions required for IRB mode"
    When `permission_mode=PermissionMode.IRB`, the calculator requires
    `model_permissions` input data to determine which exposures use FIRB,
    AIRB, or slotting. Without it, the pipeline falls back to SA for all
    exposures and emits a warning. See
    [Input Schemas — Model Permissions](../data-model/input-schemas.md#model-permissions-schema).

### `enable_double_default`

| Field | Type | Default | Defined on |
|-------|------|---------|-----------|
| `enable_double_default` | `bool` | `False` | `CalculationConfig` (`contracts/config.py:832`) |

Enables the CRR Art. 153(3) double-default risk-weight formula for IRB
exposures covered by eligible unfunded credit protection. When `True`,
the protected portion of an IRB exposure attracts the scaled
double-default capital charge

```
K_dd = K_obligor × (0.15 + 160 × PD_guarantor)
```

instead of the standard guarantee-substitution treatment. Eligibility for
the protection provider follows CRR Art. 202 (institutions, investment
firms, insurance undertakings, export credit agencies meeting the CQS
threshold) and the operational requirements of Art. 217.

!!! warning "CRR-only — removed under Basel 3.1"
    PRA PS1/26 blanks Art. 153(3), Art. 202, and Art. 217. Setting
    `enable_double_default=True` only takes effect under the CRR
    framework; under `CalculationConfig.basel_3_1(...)` the flag is
    inert because the double-default treatment is removed. See the
    [A-IRB Specification — double-default removal](../specifications/basel31/airb-calculation.md#double-default-removal).

The factory method `CalculationConfig.crr()` accepts this knob directly:

```python
from datetime import date
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import PermissionMode

config = CalculationConfig.crr(
    reporting_date=date(2026, 12, 31),
    permission_mode=PermissionMode.IRB,
    enable_double_default=True,  # Art. 153(3) double-default treatment
)

assert config.enable_double_default is True
```

For the regulatory derivation of the formula, eligibility criteria, and a
worked example, see:

- [User guide — CRM Double Default](../user-guide/methodology/crm.md#double-default-crr-only)
- [CRR Specification — Credit Risk Mitigation](../specifications/crr/credit-risk-mitigation.md)

### `use_investment_grade_assessment`

| Field | Type | Default | Defined on |
|-------|------|---------|-----------|
| `use_investment_grade_assessment` | `bool` | `False` | `CalculationConfig` (`contracts/config.py:833`) |

Enables the PRA PS1/26 **Art. 122(6)** investment-grade / non-investment-grade
split for unrated non-SME corporate exposures under the Basel 3.1 SA. When
`True`, an unrated corporate that the firm has internally assessed as
investment grade (`cp_is_investment_grade = True` on the counterparty input
table) attracts a **65%** risk weight (Art. 122(6)(a)); an unrated corporate
assessed as non-investment grade attracts **135%** (Art. 122(6)(b)). When
`False` (default) every unrated non-SME corporate attracts the Art. 122(5)
default of **100%**.

Under **Art. 122(8)** the same election also drives the SA-equivalent risk
weight used in the *S-TREA leg* of the Art. 92(2A) output floor. An IRB
firm that has set `use_investment_grade_assessment=True` automatically uses
the 65%/135% split in S-TREA (Art. 122(8)(b)); an IRB firm that has left it
`False` uses the flat 100% S-TREA treatment (Art. 122(8)(a)). The Art. 122(11)
SME carve-out (85%) overrides both branches regardless of the flag.

!!! warning "Basel 3.1 only — flag absent from `CalculationConfig.crr()`"
    The factory `CalculationConfig.crr(...)` does **not** expose
    `use_investment_grade_assessment`; the Art. 122(6)/(8) sub-categories are
    Basel 3.1 additions that have no analogue in the CRR Art. 122 corporate
    table (CQS-only, with unrated = 100%). The field exists on the underlying
    `CalculationConfig` dataclass for both frameworks, but is silently inert
    under the CRR SA path — only the Basel 3.1 SA namespace consumes it
    (`engine/sa/namespace.py:907-920`).

!!! note "PRA permission and notification obligations"
    Branch (b) — i.e. setting this flag to `True` — requires **prior PRA
    permission** under Art. 122(6) plus the sound-processes obligation in
    Art. 122(7). For an IRB firm the additional Art. 122(8)(b) final sentence
    requires the firm to **give notice to the PRA** both when it starts and
    when it ceases applying the (b) treatment to S-TREA. The calculator does
    not enforce either obligation — it is the operator's responsibility to
    confirm permission before flipping the flag.

The factory method `CalculationConfig.basel_3_1()` accepts this knob directly:

```python
from datetime import date
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import PermissionMode

config = CalculationConfig.basel_3_1(
    reporting_date=date(2027, 6, 30),
    permission_mode=PermissionMode.IRB,
    use_investment_grade_assessment=True,  # Art. 122(6)/(8) IG=65% / non-IG=135%
)

assert config.use_investment_grade_assessment is True
```

For the regulatory derivation, S-TREA interaction, scope of the election,
and worked examples, see:

- [Basel 3.1 SA Risk Weights — Corporate Sub-Categories (Art. 122(4)–(11))](../specifications/basel31/sa-risk-weights.md#corporate-sub-categories-art-122411)
- [Basel 3.1 SA Risk Weights — Output-Floor Election for Unrated Corporates (Art. 122(7)–(8))](../specifications/basel31/sa-risk-weights.md#output-floor-election-for-unrated-corporates-art-12278)
- [Blog — The Output Floor and Why Basel 3.1 Bites](../blog/2026-06-23-the-output-floor-and-why-basel-31-bites.md#the-art-1228-election)

### `crm_collateral_method`

| Field | Type | Default | Defined on |
|-------|------|---------|-----------|
| `crm_collateral_method` | `CRMCollateralMethod` | `CRMCollateralMethod.COMPREHENSIVE` | `CalculationConfig` (`contracts/config.py:838`) |

Firm-wide election under **CRR Art. 191A / PRA PS1/26 Art. 191A** for how
financial collateral is recognised under the **Standardised Approach**. The
choice applies to all SA exposures and cannot be made on a per-exposure basis.
IRB exposures always use the Foundation Collateral Method regardless of this
flag.

The enum lives in `rwa_calc.domain.enums`:

```python
class CRMCollateralMethod(StrEnum):
    COMPREHENSIVE = "comprehensive"  # FCCM — Art. 223-224 (default)
    SIMPLE = "simple"                # FCSM — Art. 222 (SA-only, 20% RW floor)
```

| Member | String value | Treatment | Regulatory basis |
|--------|--------------|-----------|------------------|
| `COMPREHENSIVE` | `"comprehensive"` | **Financial Collateral Comprehensive Method (FCCM).** Reduces EAD via supervisory haircuts (`H_c`, `H_fx`, maturity-mismatch). Applicable to both SA and IRB. | CRR Art. 223 (volatility adjustments), Art. 224 (own-estimate haircuts) |
| `SIMPLE` | `"simple"` | **Financial Collateral Simple Method (FCSM).** SA-only. Substitutes the collateral's own SA risk weight on the secured portion, subject to a **20% floor**. EAD is **not** reduced. Special 0% RW for same-currency cash deposits and 0%-RW sovereign bonds. | CRR Art. 222 |

**Defaults by factory method:**

| Factory | Default value |
|---------|---------------|
| `CalculationConfig.crr(...)` | `CRMCollateralMethod.COMPREHENSIVE` (factory default) |
| `CalculationConfig.basel_3_1(...)` | `CRMCollateralMethod.COMPREHENSIVE` (factory default) |

Both factories expose this knob as a constructor keyword. Pass the enum
directly to elect the Simple Method:

```python
from datetime import date
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import CRMCollateralMethod

config = CalculationConfig.basel_3_1(
    reporting_date=date(2027, 6, 30),
    crm_collateral_method=CRMCollateralMethod.SIMPLE,  # Art. 222 (FCSM)
)

assert config.crm_collateral_method is CRMCollateralMethod.SIMPLE
```

!!! note "Election scope"
    Art. 191A makes this a **firm-wide** election. The calculator treats the
    config field accordingly: the same value is applied to every SA exposure
    in the run. Switching mid-run requires constructing a new config.

For the regulatory derivation and worked examples, see:

- [CRR Specification — Credit Risk Mitigation](../specifications/crr/credit-risk-mitigation.md)
- [User guide — CRM methodology](../user-guide/methodology/crm.md)

### `airb_collateral_method`

| Field | Type | Default | Defined on |
|-------|------|---------|-----------|
| `airb_collateral_method` | `AIRBCollateralMethod \| None` | `None` | `CalculationConfig` (`contracts/config.py:843`) |

Election for how A-IRB firms recognise collateral in their LGD estimates under
**Basel 3.1** (PRA PS1/26 Art. 169A / 169B). Under CRR, A-IRB collateral
recognition is free-form (no method constraint), so this field is `None` and
inert under `CalculationConfig.crr(...)`. Art. 191A Part 2 governs the choice
under Basel 3.1.

The enum lives in `rwa_calc.domain.enums`:

```python
class AIRBCollateralMethod(StrEnum):
    LGD_MODELLING = "lgd_modelling"  # Art. 169A (default under B31)
    FOUNDATION = "foundation"        # Art. 229-231 (supervisory LGDS/LGDU)
```

| Member | String value | Treatment | Regulatory basis |
|--------|--------------|-----------|------------------|
| `LGD_MODELLING` | `"lgd_modelling"` | **LGD Modelling Collateral Method.** Default for A-IRB under Basel 3.1. The firm models collateral effects directly in its own LGD estimates. Where data is sufficient (Art. 169A(1)(a)) the modelled LGD is kept; where data is insufficient (Art. 169B), the calculator falls back to the Foundation formula (Art. 230 / 231) using the firm's own unsecured LGD as `LGDU` instead of the supervisory value. | PRA PS1/26 Art. 169A, Art. 169B |
| `FOUNDATION` | `"foundation"` | **Foundation Collateral Method.** A-IRB firm elects to use the same Foundation Collateral Method as F-IRB, with supervisory `LGDS` and supervisory `LGDU`. Same formula and parameters as F-IRB collateral recognition. | CRR Art. 229, Art. 230, Art. 231; PRA PS1/26 Art. 191A Part 2 |
| `None` | — | Field unset. Used by `CalculationConfig.crr(...)` because A-IRB collateral recognition is free-form under CRR — no method constraint applies. | CRR (no equivalent of Art. 191A Part 2) |

**Defaults by factory method:**

| Factory | Default value |
|---------|---------------|
| `CalculationConfig.crr(...)` | `None` (dataclass default — A-IRB is free-form under CRR; not exposed as a `crr()` keyword) |
| `CalculationConfig.basel_3_1(...)` | `AIRBCollateralMethod.LGD_MODELLING` (factory default — Art. 169A) |

`CalculationConfig.basel_3_1(...)` exposes this knob as a constructor
keyword. To elect the Foundation Collateral Method instead of the Art. 169A
LGD-modelling default, pass it directly to the factory:

```python
from datetime import date
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import AIRBCollateralMethod, PermissionMode

config = CalculationConfig.basel_3_1(
    reporting_date=date(2027, 6, 30),
    permission_mode=PermissionMode.IRB,
    airb_collateral_method=AIRBCollateralMethod.FOUNDATION,  # Art. 169A election → Foundation
)

assert config.airb_collateral_method is AIRBCollateralMethod.FOUNDATION
```

!!! warning "Basel 3.1 only — inert under CRR"
    `airb_collateral_method` only takes effect under
    `CalculationConfig.basel_3_1(...)`. Under CRR, A-IRB collateral
    recognition has no statutory method constraint (Art. 181 / Art. 183
    govern own-estimate LGD with no Art. 191A Part 2 overlay), so the
    calculator ignores the field. Setting it on a CRR config is allowed
    for round-tripping but has no calculation effect.

For the regulatory derivation, fallback mechanics, and worked examples, see:

- [Basel 3.1 A-IRB Specification](../specifications/basel31/airb-calculation.md)
- [User guide — CRM methodology](../user-guide/methodology/crm.md)

## Usage Examples

### CRR Configuration

```python
from datetime import date
from decimal import Decimal
from rwa_calc.contracts.config import CalculationConfig
from rwa_calc.domain.enums import PermissionMode

# SA-only CRR configuration (default)
config = CalculationConfig.crr(
    reporting_date=date(2026, 12, 31),
)

# CRR with IRB routing (requires model_permissions input data)
config = CalculationConfig.crr(
    reporting_date=date(2026, 12, 31),
    permission_mode=PermissionMode.IRB,
)

# Access configuration
print(f"Framework: {config.framework}")          # RegulatoryFramework.CRR
print(f"Is CRR: {config.is_crr}")                # True
print(f"Scaling factor: {config.scaling_factor}") # 1.06
print(f"SME enabled: {config.supporting_factors.enabled}")  # True
```

### Basel 3.1 Configuration

```python
# Basel 3.1 with IRB routing (auto-calculates output floor from reporting_date)
config = CalculationConfig.basel_3_1(
    reporting_date=date(2027, 6, 30),
    permission_mode=PermissionMode.IRB,
)

# Check output floor percentage (transitional for 2027 = 60%)
floor = config.get_output_floor_percentage()
print(f"Output floor: {floor:.0%}")  # 60%

# Fully phased-in (2030+)
config = CalculationConfig.basel_3_1(
    reporting_date=date(2030, 1, 1),
    permission_mode=PermissionMode.IRB,
)
floor = config.get_output_floor_percentage()
print(f"Output floor: {floor:.1%}")  # 72.5%
```

### Accessing Floors

```python
from rwa_calc.domain.enums import ExposureClass, CollateralType

# PD floor lookup
pd_floor = config.pd_floors.get_floor(ExposureClass.CORPORATE)
print(f"Corporate PD floor: {pd_floor:.4%}")  # 0.0500% (Basel 3.1)

# PD floor for QRRE (distinguish transactor vs revolver)
qrre_floor = config.pd_floors.get_floor(
    ExposureClass.RETAIL_QRRE, is_qrre_transactor=True
)
print(f"QRRE transactor PD floor: {qrre_floor:.4%}")  # 0.0500%

# LGD floor lookup
lgd_floor = config.lgd_floors.get_floor(CollateralType.IMMOVABLE)
print(f"CRE LGD floor: {lgd_floor:.0%}")  # 10%
```

### Permission Mode

```python
from rwa_calc.domain.enums import PermissionMode

# SA-only — all exposures use standardised approach
config = CalculationConfig.crr(
    reporting_date=date(2026, 12, 31),
    permission_mode=PermissionMode.STANDARDISED,  # default
)

# IRB mode — model_permissions input data drives approach routing
# Each exposure is matched to its model's approved approach (AIRB, FIRB, slotting)
# Exposures without a model permission fall back to SA
config = CalculationConfig.basel_3_1(
    reporting_date=date(2027, 6, 30),
    permission_mode=PermissionMode.IRB,
)
```

## Related

- [Pipeline API](pipeline.md)
- [Contracts API](contracts.md)
- [Engine API](engine.md)
- [Framework Comparison](../framework-comparison/index.md)
