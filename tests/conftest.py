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


@pytest.fixture(scope="session")
def area_sources_path() -> Path:
    return _require("asm_ver12e_winGT_fs017_combined.xml")


@pytest.fixture(scope="session")
def gmpe_logic_tree_path() -> Path:
    return _require("gmpe_logic_tree_5br_slope_geology.xml")


@pytest.fixture(scope="session")
def site_model_path() -> Path:
    return _require("Site_model_Switzerland.xml")
