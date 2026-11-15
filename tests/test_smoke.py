"""Smoke tests: package imports and config parses."""

from pathlib import Path

import yaml

import chquake

ROOT = Path(__file__).resolve().parents[1]


def test_package_imports() -> None:
    assert chquake.__version__


def test_config_has_run_section() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["run"]["n_years"] > 0
    assert isinstance(cfg["run"]["seed"], int)
