"""Shared fixtures for the API unit tests.

Provides the ``temp_valid_dir`` fixture used by both ``test_api_validation.py``
(file-presence checks) and ``test_service.py`` (full pipeline runs). The fixture
writes a single-row seed frame, which is harmless for the validation tests (they
only assert ``response.valid`` / ``files_missing``, never row counts) and gives
the service tests the non-empty input their pipeline runs require.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def temp_valid_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with all required parquet files."""
    # Create directory structure
    (tmp_path / "counterparty").mkdir()
    (tmp_path / "exposures").mkdir()
    (tmp_path / "collateral").mkdir()
    (tmp_path / "guarantee").mkdir()
    (tmp_path / "provision").mkdir()
    (tmp_path / "ratings").mkdir()
    (tmp_path / "mapping").mkdir()

    # Create minimal files with a single seed row
    seed_df = pl.DataFrame({"id": ["1"]})

    # Counterparty file (mandatory)
    seed_df.write_parquet(tmp_path / "counterparty" / "counterparties.parquet")

    # Exposure files
    seed_df.write_parquet(tmp_path / "exposures" / "facilities.parquet")
    seed_df.write_parquet(tmp_path / "exposures" / "loans.parquet")
    seed_df.write_parquet(tmp_path / "exposures" / "contingents.parquet")
    seed_df.write_parquet(tmp_path / "exposures" / "facility_mapping.parquet")

    # CRM files
    seed_df.write_parquet(tmp_path / "collateral" / "collateral.parquet")
    seed_df.write_parquet(tmp_path / "guarantee" / "guarantee.parquet")
    seed_df.write_parquet(tmp_path / "provision" / "provision.parquet")

    # Ratings and mappings
    seed_df.write_parquet(tmp_path / "ratings" / "ratings.parquet")
    seed_df.write_parquet(tmp_path / "mapping" / "org_mapping.parquet")
    seed_df.write_parquet(tmp_path / "mapping" / "lending_mapping.parquet")

    return tmp_path
