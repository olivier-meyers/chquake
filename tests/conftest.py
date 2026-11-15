"""Shared fixtures: paths to the downloaded ESRM20 files (tests skip if not downloaded)."""

from pathlib import Path

import pytest

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def _require(name: str) -> Path:
    path = RAW / name
    if not path.exists():
        pytest.skip(f"{name} not downloaded; run scripts/download_data.py")
    return path


@pytest.fixture(scope="session")
def exposure_path() -> Path:
    return _require("Exposure_Model_Switzerland_Res.csv")


@pytest.fixture(scope="session")
def vulnerability_path() -> Path:
    return _require("vulnerability_total-repl-cost_ESRM20_VariousIM.xml")


@pytest.fixture(scope="session")
def mapping_path() -> Path:
    return _require("esrm20_exposure_vulnerability_mapping.csv")
