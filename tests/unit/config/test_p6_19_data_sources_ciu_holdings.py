"""Unit tests for P6.19 — DataSourceRegistry missing ciu_holdings entry.

Asserts that the registry contains a DataSourceFile for CIU holdings and that
DataSourceConfig.from_registry() populates the ciu_holdings_file field.

References:
- P6.19: DataSourceRegistry missing ciu_holdings entry
"""

from __future__ import annotations

from pathlib import Path

from rwa_calc.config.data_sources import DataSourceFile, DataSourceRegistry, RequirementLevel
from rwa_calc.engine.loader import DataSourceConfig


class TestDataSourceRegistryCiuHoldings:
    """Tests for ciu_holdings entry in DataSourceRegistry (P6.19)."""

    def test_registry_contains_ciu_holdings_entry(self) -> None:
        """DataSourceRegistry should contain an entry with id 'ciu_holdings'."""
        # Arrange
        registry = DataSourceRegistry()

        # Act
        source = registry.get_by_id("ciu_holdings")

        # Assert
        assert source is not None, "Expected 'ciu_holdings' entry in DataSourceRegistry, got None"
        assert isinstance(source, DataSourceFile)

    def test_ciu_holdings_relative_path(self) -> None:
        """ciu_holdings entry should have relative_path of 'equity/ciu_holdings'."""
        # Arrange
        registry = DataSourceRegistry()

        # Act
        source = registry.get_by_id("ciu_holdings")

        # Assert
        assert source is not None
        assert source.relative_path == Path("equity/ciu_holdings"), (
            f"Expected relative_path=Path('equity/ciu_holdings'), got {source.relative_path!r}"
        )

    def test_ciu_holdings_requirement_is_optional(self) -> None:
        """ciu_holdings entry should have requirement level OPTIONAL."""
        # Arrange
        registry = DataSourceRegistry()

        # Act
        source = registry.get_by_id("ciu_holdings")

        # Assert
        assert source is not None
        assert source.requirement is RequirementLevel.OPTIONAL, (
            f"Expected RequirementLevel.OPTIONAL, got {source.requirement!r}"
        )

    def test_ciu_holdings_parquet_path_in_optional_list(self) -> None:
        """equity/ciu_holdings.parquet should appear in DataSourceRegistry.get_optional('parquet')."""
        # Arrange
        registry = DataSourceRegistry()

        # Act
        optional_paths = registry.get_optional("parquet")

        # Assert
        assert Path("equity/ciu_holdings.parquet") in optional_paths, (
            f"Expected Path('equity/ciu_holdings.parquet') in optional parquet paths, "
            f"got: {optional_paths}"
        )

    def test_from_registry_parquet_populates_ciu_holdings_file(self) -> None:
        """DataSourceConfig.from_registry() should set ciu_holdings_file to equity/ciu_holdings.parquet."""
        # Arrange / Act
        config = DataSourceConfig.from_registry()

        # Assert
        assert config.ciu_holdings_file == Path("equity/ciu_holdings.parquet"), (
            f"Expected ciu_holdings_file=Path('equity/ciu_holdings.parquet'), "
            f"got {config.ciu_holdings_file!r}"
        )

    def test_from_registry_csv_populates_ciu_holdings_file(self) -> None:
        """DataSourceConfig.from_registry(extension='csv') should set ciu_holdings_file to equity/ciu_holdings.csv."""
        # Arrange / Act
        config = DataSourceConfig.from_registry(extension="csv")

        # Assert
        assert config.ciu_holdings_file == Path("equity/ciu_holdings.csv"), (
            f"Expected ciu_holdings_file=Path('equity/ciu_holdings.csv'), "
            f"got {config.ciu_holdings_file!r}"
        )

    def test_ciu_holdings_description_contains_ciu(self) -> None:
        """ciu_holdings entry should have a non-None description mentioning 'ciu'."""
        # Arrange
        registry = DataSourceRegistry()

        # Act
        source = registry.get_by_id("ciu_holdings")

        # Assert
        assert source is not None
        assert source.description is not None, "Expected a non-None description for ciu_holdings"
        assert "ciu" in source.description.lower(), (
            f"Expected 'ciu' in description (case-insensitive), got {source.description!r}"
        )
