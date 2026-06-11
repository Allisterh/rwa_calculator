"""
Integration test: the server-rendered reconciliation page.

Pipeline position:
    TestClient -> FastAPI /reconciliation routes -> CreditRiskCalc.reconcile()
        -> ui.views.reconciliation -> Jinja + SVG

Key responsibilities tested:
- GET /reconciliation renders the form pre-filled with the default TOML mapping.
- POST /reconciliation runs a real reconciliation against a generated legacy file
  and (after the 303) renders the four tiers with an inline SVG chart.
- A bad mapping re-renders the form with an error and a 400.
- GET /reconciliation/{id}?bucket=… reads the cached result; unknown ids 404.

The legacy output is generated from our own SA results (renamed + one RWA nudged
to force a break) so the reconciliation has comparable components and a worklist.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from rwa_calc.api.service import CreditRiskCalc
from rwa_calc.ui.app.main import create_app
from rwa_calc.ui.app.recon_state import STATE_DIR_ENV_VAR
from rwa_calc.ui.views.reconciliation import DEFAULT_MAPPING_TOML
from tests.fixtures.api_validation.build_mandatory_only import write_mandatory_minimum


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the last-run state file into tmp so the real ~/.rwa_calc is untouched.

    Without this, the form-prefill feature could read a developer's real saved run
    and flake the default-mapping assertion below.
    """
    monkeypatch.setenv(STATE_DIR_ENV_VAR, str(tmp_path / "state"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def recon_dir(tmp_path: Path) -> str:
    """Mandatory-minimum dataset plus a legacy_output.csv derived from our results."""
    write_mandatory_minimum(tmp_path)
    ours = (
        CreditRiskCalc(
            data_path=str(tmp_path),
            framework="CRR",
            reporting_date=date(2025, 1, 1),
            permission_mode="standardised",
            data_format="parquet",
        )
        .calculate()
        .scan_results()
        .select("exposure_reference", "ead_final", "rwa_final")
        .collect()
    )
    legacy = (
        ours.rename({"ead_final": "EAD", "rwa_final": "RWA"})
        .with_row_index("_i")
        .with_columns(
            pl.when(pl.col("_i") == 0)
            .then(pl.col("RWA") * 1.5)  # nudge the first row's RWA -> a break
            .otherwise(pl.col("RWA"))
            .alias("RWA")
        )
        .drop("_i")
    )
    legacy.write_csv(tmp_path / "legacy_output.csv")
    return str(tmp_path)


def _form_data(data_path: str, mapping_toml: str = DEFAULT_MAPPING_TOML) -> dict:
    return {
        "data_path": data_path,
        "reporting_date": "2025-01-01",
        "framework": "CRR",
        "permission_mode": "standardised",
        "data_format": "parquet",
        "mapping_toml": mapping_toml,
    }


def test_reconciliation_form_renders_with_default_mapping(client: TestClient) -> None:
    resp = client.get("/reconciliation")
    assert resp.status_code == 200
    assert "<textarea" in resp.text
    assert "legacy_file" in resp.text  # the default TOML is pre-filled


def test_reconciliation_post_renders_four_tiers(client: TestClient, recon_dir: str) -> None:
    # TestClient follows the 303 to /reconciliation/{id}
    resp = client.post("/reconciliation", data=_form_data(recon_dir))
    assert resp.status_code == 200
    assert "Headline" in resp.text
    assert "Worklist" in resp.text
    assert "Forensic" in resp.text
    assert '<svg class="chart"' in resp.text


def test_reconciliation_renders_asset_class_allocation(client: TestClient, tmp_path: Path) -> None:
    # Arrange: a legacy file that carries an asset-class column per line (the
    # default mapping maps exposure_class -> Asset_Class), so the allocation tier
    # is populated and rendered.
    write_mandatory_minimum(tmp_path)
    ours = (
        CreditRiskCalc(
            data_path=str(tmp_path),
            framework="CRR",
            reporting_date=date(2025, 1, 1),
            permission_mode="standardised",
            data_format="parquet",
        )
        .calculate()
        .scan_results()
        .select("exposure_reference", "ead_final", "rwa_final", "exposure_class")
        .collect()
    )
    ours.rename(
        {"ead_final": "EAD", "rwa_final": "RWA", "exposure_class": "Asset_Class"}
    ).write_csv(tmp_path / "legacy_output.csv")

    # Act
    resp = client.post("/reconciliation", data=_form_data(str(tmp_path)))

    # Assert: the asset-class allocation view is present.
    assert resp.status_code == 200
    assert "Asset-class allocation" in resp.text


def test_reconciliation_bucket_filter_reads_cached_result(
    client: TestClient, recon_dir: str
) -> None:
    posted = client.post("/reconciliation", data=_form_data(recon_dir), follow_redirects=False)
    assert posted.status_code == 303
    location = posted.headers["location"]
    assert location.startswith("/reconciliation/")

    got = client.get(location, params={"bucket": "break"})
    assert got.status_code == 200
    assert "Forensic" in got.text


def test_reconciliation_bad_mapping_rerenders_with_error(
    client: TestClient, recon_dir: str
) -> None:
    resp = client.post("/reconciliation", data=_form_data(recon_dir, mapping_toml="not valid ["))
    assert resp.status_code == 400
    assert "Reconciliation failed" in resp.text


def test_reconciliation_unknown_id_is_404(client: TestClient) -> None:
    assert client.get("/reconciliation/does-not-exist").status_code == 404


def test_reconciliation_prefills_from_last_run(client: TestClient, recon_dir: str) -> None:
    # Arrange — a non-default combo so the prefilled values are unambiguous.
    marked_toml = DEFAULT_MAPPING_TOML + "\n# MY-CUSTOM-MARKER\n"
    submitted = {
        "data_path": recon_dir,
        "reporting_date": "2026-06-30",
        "framework": "BASEL_3_1",
        "permission_mode": "irb",
        "data_format": "parquet",
        "mapping_toml": marked_toml,
    }

    # Act — run it (saves on success), then re-open the blank form.
    posted = client.post("/reconciliation", data=submitted)
    assert posted.status_code == 200
    form = client.get("/reconciliation")

    # Assert — every field comes back from the saved run.
    assert form.status_code == 200
    assert recon_dir in form.text
    assert "2026-06-30" in form.text
    assert "# MY-CUSTOM-MARKER" in form.text
    assert 'value="BASEL_3_1" selected' in form.text
    assert 'value="irb" selected' in form.text


def _non_default_form(data_path: str) -> dict:
    return {
        "data_path": data_path,
        "reporting_date": "2026-06-30",
        "framework": "BASEL_3_1",
        "permission_mode": "irb",
        "data_format": "parquet",
        "mapping_toml": DEFAULT_MAPPING_TOML + "\n# MY-CUSTOM-MARKER\n",
    }


def test_reset_button_hidden_until_a_run_is_saved(client: TestClient, recon_dir: str) -> None:
    # Arrange — a fresh form has nothing to reset.
    fresh = client.get("/reconciliation")
    assert "/reconciliation/reset" not in fresh.text

    # Act — a completed run saves state.
    client.post("/reconciliation", data=_non_default_form(recon_dir))

    # Assert — the reset control now appears.
    assert "/reconciliation/reset" in client.get("/reconciliation").text


def test_reset_restores_defaults_and_clears_saved_run(client: TestClient, recon_dir: str) -> None:
    # Arrange — save a non-default run, confirm it is pre-filled.
    client.post("/reconciliation", data=_non_default_form(recon_dir))
    assert "# MY-CUSTOM-MARKER" in client.get("/reconciliation").text

    # Act — reset (303 -> /reconciliation).
    reset = client.get("/reconciliation/reset", follow_redirects=False)
    assert reset.status_code == 303
    assert reset.headers["location"] == "/reconciliation"

    # Assert — the form is back to defaults and the saved run is gone.
    form = client.get("/reconciliation")
    assert "# MY-CUSTOM-MARKER" not in form.text
    assert "./legacy_output.csv" in form.text  # the default mapping TOML
    assert "/reconciliation/reset" not in form.text  # nothing left to reset
