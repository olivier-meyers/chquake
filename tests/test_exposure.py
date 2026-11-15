"""Exposure: the ESRM20 Swiss residential file is internally consistent."""

import numpy as np

from chquake.exposure import load_exposure, value_by_canton


def test_cost_components_add_up(exposure_path) -> None:
    e = load_exposure(exposure_path)
    parts = e["value_structural"] + e["value_nonstructural"] + e["value_contents"]
    np.testing.assert_allclose(parts, e["value"], rtol=1e-12)
    # documented ESRM20 residential split: 30 % structural, 50 % non-structural, 20 % contents
    np.testing.assert_allclose(e["value_structural"] / e["value"], 0.3, atol=1e-12)
    np.testing.assert_allclose(e["value_contents"] / e["value"], 0.2, atol=1e-12)


def test_canton_totals(exposure_path) -> None:
    e = load_exposure(exposure_path)
    by_canton = value_by_canton(e)
    assert len(by_canton) == 26
    assert by_canton["value"].sum() == np.float64(e["value"].sum())
    assert by_canton["value"].is_monotonic_decreasing
