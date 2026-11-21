"""Event losses: hand-computed toy portfolio, and secondary uncertainty preserving the mean."""

import numpy as np
import pytest

from chquake.losses import asset_imt_index, event_losses
from chquake.vulnerability import VulnerabilityModel


def _toy_model() -> VulnerabilityModel:
    """Same toy functions as test_vulnerability: 'a' uses PGA, 'b' uses SA(1.0)."""
    return VulnerabilityModel(
        ids=np.array(["a", "b"]),
        imt=np.array(["PGA", "SA(1.0)"]),
        iml=np.array([0.1, 0.2, 0.4]),
        mean=np.array([[0.0, 0.2, 0.6], [0.1, 0.1, 0.9]]),
        cov=np.array([[0.0, 1.0, 0.5], [0.4, 0.4, 0.2]]),
    )


def _toy_portfolio():
    model = _toy_model()
    imts = ["PGA", "SA(1.0)"]
    func = np.array([0, 1, 0])  # asset 0: 'a', asset 1: 'b', asset 2: 'a'
    site = np.array([0, 0, 1])  # assets 0, 1 at site 0; asset 2 at site 1
    value = np.array([100.0, 200.0, 1000.0])
    # gmf[imt, event, site]; event 0 strong at site 0, event 1 weak everywhere
    gmf = np.array(
        [
            [[0.3, 0.05], [0.01, 0.01]],  # PGA
            [[0.4, 0.2], [0.01, 0.01]],  # SA(1.0)
        ]
    )
    return model, imts, func, site, value, gmf


def test_event_losses_hand_case() -> None:
    model, imts, func, site, value, gmf = _toy_portfolio()
    imt_idx = asset_imt_index(model, func, imts)
    np.testing.assert_array_equal(imt_idx, [0, 1, 0])
    loss = event_losses(gmf, imt_idx, site, func, value, model)
    # event 0: asset0 PGA 0.3 -> LR 0.4 -> 40; asset1 SA 0.4 -> 0.9 -> 180;
    #          asset2 PGA 0.05 (below grid) -> 0.  Total 220.
    # event 1: everything below 0.1 g -> 0.
    np.testing.assert_allclose(loss, [220.0, 0.0])


def test_chunking_does_not_change_result() -> None:
    model, imts, func, site, value, gmf = _toy_portfolio()
    imt_idx = asset_imt_index(model, func, imts)
    a = event_losses(gmf, imt_idx, site, func, value, model, chunk=1)
    b = event_losses(gmf, imt_idx, site, func, value, model, chunk=64)
    np.testing.assert_array_equal(a, b)


def test_missing_imt_raises() -> None:
    model, _, func, *_ = _toy_portfolio()
    with pytest.raises(KeyError):
        asset_imt_index(model, func, ["PGA"])


def test_secondary_uncertainty_preserves_mean_loss() -> None:
    model, imts, func, site, value, gmf = _toy_portfolio()
    imt_idx = asset_imt_index(model, func, imts)
    many = np.repeat(gmf[:, :1, :], 20_000, axis=1)  # event 0 repeated
    loss = event_losses(many, imt_idx, site, func, value, model, np.random.default_rng(2))
    assert loss.mean() == pytest.approx(220.0, rel=0.01)  # E[Beta draw] = mean loss ratio
    assert loss.std() > 0  # but individual events now scatter
