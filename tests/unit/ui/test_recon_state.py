"""
Unit tests for the reconciliation last-run persistence helper.

Pipeline position:
    ui.app.recon_state (save_last_run / load_last_run) — exercised in isolation.

Key responsibilities tested:
- Round-tripping ``ReconciliationFormState`` through the JSON state file, including
  a multi-line TOML mapping with comments.
- Graceful degradation: a missing, corrupt or partial state file loads as ``None``
  and never raises.
- ``save_last_run`` swallows IO errors so a save failure can never break a run.
- The ``RWA_STATE_DIR`` env var redirects the state file (the test seam that keeps
  the real ``~/.rwa_calc`` untouched).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rwa_calc.ui.app.recon_state import (
    STATE_DIR_ENV_VAR,
    ReconciliationFormState,
    _state_file,
    clear_last_run,
    load_last_run,
    save_last_run,
)

_TOML_WITH_COMMENTS = """\
# my legacy mapping
legacy_file   = "./legacy_output.csv"
legacy_format = "csv"
legacy_keys   = ["exposure_reference"]
our_keys      = ["exposure_reference"]

[components.rwa]
legacy_column = "RWA"  # nudged
"""


def _sample_state() -> ReconciliationFormState:
    return ReconciliationFormState(
        data_path="/data/2025-q1",
        reporting_date="2025-03-31",
        framework="BASEL_3_1",
        permission_mode="irb",
        data_format="csv",
        mapping_toml=_TOML_WITH_COMMENTS,
    )


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the state file into tmp so the real home dir is never touched."""
    monkeypatch.setenv(STATE_DIR_ENV_VAR, str(tmp_path / "state"))


def test_round_trip_preserves_all_fields() -> None:
    # Arrange
    state = _sample_state()

    # Act
    save_last_run(state)
    loaded = load_last_run()

    # Assert
    assert loaded == state


def test_round_trip_preserves_multiline_toml_comments() -> None:
    # Arrange
    state = _sample_state()

    # Act
    save_last_run(state)
    loaded = load_last_run()

    # Assert
    assert loaded is not None
    assert loaded.mapping_toml == _TOML_WITH_COMMENTS


def test_missing_file_loads_as_none() -> None:
    # Act / Assert — nothing saved yet
    assert load_last_run() is None


def test_corrupt_json_loads_as_none() -> None:
    # Arrange
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    # Act / Assert — does not raise
    assert load_last_run() is None


def test_partial_json_loads_as_none() -> None:
    # Arrange — a dict missing the mapping_toml field
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"data_path": "/d", "reporting_date": "2025-01-01", "framework": "CRR", '
        '"permission_mode": "standardised", "data_format": "parquet"}',
        encoding="utf-8",
    )

    # Act / Assert
    assert load_last_run() is None


def test_save_creates_missing_nested_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — point at a dir that does not exist yet
    target = tmp_path / "deeper" / "nest"
    monkeypatch.setenv(STATE_DIR_ENV_VAR, str(target))

    # Act
    save_last_run(_sample_state())

    # Assert
    assert load_last_run() == _sample_state()


def test_save_swallows_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — point the state DIR at an existing *file* so mkdir() raises
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv(STATE_DIR_ENV_VAR, str(blocker))

    # Act / Assert — must not raise despite the unwritable path
    save_last_run(_sample_state())


def test_env_override_points_state_file_under_tmp(tmp_path: Path) -> None:
    # Assert — the resolved file lives under the env-var dir (set by the fixture)
    assert _state_file() == tmp_path / "state" / "reconciliation_last_run.json"


def test_clear_removes_saved_state() -> None:
    # Arrange
    save_last_run(_sample_state())
    assert load_last_run() is not None

    # Act
    clear_last_run()

    # Assert
    assert load_last_run() is None


def test_clear_is_safe_when_no_file() -> None:
    # Act / Assert — clearing a never-saved state must not raise
    clear_last_run()
    assert load_last_run() is None
