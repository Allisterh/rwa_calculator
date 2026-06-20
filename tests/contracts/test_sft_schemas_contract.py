"""Contract tests for the dedicated SFT (FCCM) input schemas.

Phase 2 of the SFT / FCCM separation (docs/plans/sft-fccm-separation.md):
``SFT_TRADE_SCHEMA`` and ``SFT_COLLATERAL_SCHEMA`` declare the Financial
Collateral Comprehensive Method (FCCM, CRR Art. 220-223) input contract
first-class, replacing the columns previously tunnelled undeclared through
the SA-CCR ``TRADE_SCHEMA`` / ``CCR_COLLATERAL_SCHEMA``.

These are pure structural checks — they do NOT test calculation behaviour or
loader/bundle wiring (those land in later phases). Each schema object is a
``dict[str, ColumnSpec]`` following the same conventions as the other
``rwa_calc.data.schemas`` declarations.

References:
    - CRR Art. 220(1)(a) — single-counterparty SFT / master-netting-set scope
    - CRR Art. 223(5) — E* = max(0, E·(1+HE) − CVA·(1−HC−HFX))
    - CRR Art. 224 Table 1 — supervisory haircuts (HE / HC inputs)
    - CRR Art. 271(2) — SFT EAD via FCCM, not SA-CCR Art. 274
"""

from __future__ import annotations

import polars as pl

import rwa_calc.data.schemas as schemas
from rwa_calc.data.column_spec import ColumnSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_schema(name: str) -> dict[str, ColumnSpec]:
    """Fetch a schema by name, asserting it exists."""
    obj = getattr(schemas, name, None)
    assert obj is not None, (
        f"rwa_calc.data.schemas does not expose '{name}'. "
        f"Add the schema to src/rwa_calc/data/schemas.py (SFT/FCCM separation Phase 2)."
    )
    return obj  # type: ignore[return-value]


def _spec(schema: dict[str, ColumnSpec], col: str) -> ColumnSpec:
    """Return the ColumnSpec for *col*, asserting it exists and is a ColumnSpec."""
    spec = schema.get(col)
    assert spec is not None, f"Column '{col}' not found in schema"
    assert isinstance(spec, ColumnSpec), f"Schema entry for '{col}' must be a ColumnSpec"
    return spec


# ===========================================================================
# SFT_TRADE_SCHEMA
# ===========================================================================

_SFT_TRADE_COLUMNS = {
    "trade_id",
    "netting_set_id",
    "counterparty_reference",
    "notional",
    "currency",
    "maturity_date",
    "start_date",
    "exposure_collateral_type",
    "exposure_security_cqs",
    "exposure_security_residual_maturity_years",
}


def test_sft_trade_schema_exists() -> None:
    """SFT_TRADE_SCHEMA must be importable from rwa_calc.data.schemas."""
    schema = _get_schema("SFT_TRADE_SCHEMA")
    assert isinstance(schema, dict) and schema, "SFT_TRADE_SCHEMA must be a non-empty dict"


def test_sft_trade_schema_has_exact_column_set() -> None:
    """SFT_TRADE_SCHEMA is a lean, dedicated schema with a fixed column set."""
    schema = _get_schema("SFT_TRADE_SCHEMA")
    assert set(schema.keys()) == _SFT_TRADE_COLUMNS, (
        f"SFT_TRADE_SCHEMA column set drift: got {sorted(schema.keys())}, "
        f"expected {sorted(_SFT_TRADE_COLUMNS)}"
    )


def test_sft_trade_schema_carries_no_derivative_only_columns() -> None:
    """The lean SFT trade schema must NOT inherit SA-CCR-only columns.

    The whole point of the separation is that an SFT row stops carrying ~25
    derivative-only columns (delta, option_*, cdo_*, commodity_type, ...).
    """
    schema = _get_schema("SFT_TRADE_SCHEMA")
    forbidden = {"delta", "mtm_value", "option_strike", "cdo_attachment", "commodity_type"}
    leaked = forbidden & set(schema.keys())
    assert not leaked, f"SFT_TRADE_SCHEMA must not carry SA-CCR-only columns: {sorted(leaked)}"


def test_sft_trade_schema_required_core_columns() -> None:
    """trade_id / netting_set_id / counterparty_reference / notional are required."""
    schema = _get_schema("SFT_TRADE_SCHEMA")
    for col in ("trade_id", "netting_set_id", "counterparty_reference", "notional"):
        assert _spec(schema, col).required is True, f"SFT_TRADE_SCHEMA.{col} must be required=True"


def test_sft_trade_schema_counterparty_reference_is_denormalised_string() -> None:
    """counterparty_reference is a required string (denormalised from the netting set)."""
    spec = _spec(_get_schema("SFT_TRADE_SCHEMA"), "counterparty_reference")
    assert spec.dtype == pl.String, f"counterparty_reference must be pl.String, got {spec.dtype}"
    assert spec.required is True


def test_sft_trade_schema_notional_is_float64() -> None:
    """notional (E in the E* formula) must be pl.Float64."""
    assert _spec(_get_schema("SFT_TRADE_SCHEMA"), "notional").dtype == pl.Float64


def test_sft_trade_schema_dates_are_date_dtype() -> None:
    """maturity_date and start_date must be pl.Date."""
    schema = _get_schema("SFT_TRADE_SCHEMA")
    for col in ("maturity_date", "start_date"):
        assert _spec(schema, col).dtype == pl.Date, f"SFT_TRADE_SCHEMA.{col} must be pl.Date"


def test_sft_trade_schema_he_inputs_are_first_class_nullable() -> None:
    """The three Art. 223(5) HE inputs are declared first-class, nullable.

    Dtypes match the identically named LOAN_SCHEMA / CONTINGENTS_SCHEMA columns:
    String / Int8 / Float64, all required=False (null => HE = 0).
    """
    schema = _get_schema("SFT_TRADE_SCHEMA")
    expected = {
        "exposure_collateral_type": pl.String,
        "exposure_security_cqs": pl.Int8,
        "exposure_security_residual_maturity_years": pl.Float64,
    }
    for col, dtype in expected.items():
        spec = _spec(schema, col)
        assert spec.dtype == dtype, f"SFT_TRADE_SCHEMA.{col} must be {dtype}, got {spec.dtype}"
        assert spec.required is False, f"SFT_TRADE_SCHEMA.{col} must be required=False (nullable)"
        assert spec.default is None, f"SFT_TRADE_SCHEMA.{col} must default to None"


# ===========================================================================
# SFT_COLLATERAL_SCHEMA
# ===========================================================================

_SFT_COLLATERAL_COLUMNS = {
    "sft_collateral_reference",
    "netting_set_id",
    "collateral_type",
    "market_value",
    "currency",
    "issuer_cqs",
    "residual_maturity_years",
}


def test_sft_collateral_schema_exists() -> None:
    """SFT_COLLATERAL_SCHEMA must be importable from rwa_calc.data.schemas."""
    schema = _get_schema("SFT_COLLATERAL_SCHEMA")
    assert isinstance(schema, dict) and schema, "SFT_COLLATERAL_SCHEMA must be a non-empty dict"


def test_sft_collateral_schema_has_exact_column_set() -> None:
    """SFT_COLLATERAL_SCHEMA is a lean subset of CCR_COLLATERAL_SCHEMA."""
    schema = _get_schema("SFT_COLLATERAL_SCHEMA")
    assert set(schema.keys()) == _SFT_COLLATERAL_COLUMNS, (
        f"SFT_COLLATERAL_SCHEMA column set drift: got {sorted(schema.keys())}, "
        f"expected {sorted(_SFT_COLLATERAL_COLUMNS)}"
    )


def test_sft_collateral_schema_drops_sa_ccr_only_columns() -> None:
    """The lean collateral schema must drop the SA-CCR-only collateral columns."""
    schema = _get_schema("SFT_COLLATERAL_SCHEMA")
    dropped = {"is_posted_by_firm", "is_segregated", "issuer_type", "haircut_override"}
    leaked = dropped & set(schema.keys())
    assert not leaked, f"SFT_COLLATERAL_SCHEMA must drop SA-CCR-only columns: {sorted(leaked)}"


def test_sft_collateral_schema_market_value_default_is_zero() -> None:
    """market_value (CVA in the E* formula) must default to 0.0 (no collateral credit)."""
    spec = _spec(_get_schema("SFT_COLLATERAL_SCHEMA"), "market_value")
    assert spec.dtype == pl.Float64
    assert spec.required is False
    assert spec.default == 0.0, f"market_value must default to 0.0, got {spec.default!r}"


# ===========================================================================
# VALID_TRANSACTION_TYPES + COLUMN_VALUE_CONSTRAINTS wiring
# ===========================================================================


def test_valid_transaction_types_is_derivative_and_sft() -> None:
    """VALID_TRANSACTION_TYPES must be exactly {'derivative', 'sft'}."""
    valid = getattr(schemas, "VALID_TRANSACTION_TYPES", None)
    assert valid is not None, "rwa_calc.data.schemas does not expose 'VALID_TRANSACTION_TYPES'"
    assert valid == {"derivative", "sft"}, f"VALID_TRANSACTION_TYPES drift: {valid}"


def test_transaction_type_constraint_references_valid_transaction_types() -> None:
    """COLUMN_VALUE_CONSTRAINTS['trades']['transaction_type'] must be VALID_TRANSACTION_TYPES."""
    constraints = getattr(schemas, "COLUMN_VALUE_CONSTRAINTS", None)
    assert constraints is not None, (
        "rwa_calc.data.schemas does not expose 'COLUMN_VALUE_CONSTRAINTS'"
    )
    trades = constraints.get("trades")
    assert trades is not None, "COLUMN_VALUE_CONSTRAINTS must have a 'trades' entry"
    assert trades.get("transaction_type") == schemas.VALID_TRANSACTION_TYPES, (
        "COLUMN_VALUE_CONSTRAINTS['trades']['transaction_type'] must equal VALID_TRANSACTION_TYPES"
    )
