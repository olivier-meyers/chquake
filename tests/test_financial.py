"""Financial terms against hand-computed cases."""

import numpy as np
import pytest
from tests.test_losses import _toy_portfolio

from chquake.financial import cat_xl, deductible_ratio, layer_recoveries
from chquake.losses import asset_imt_index, event_losses


def test_deductible_ratio_percentage_vs_minimum() -> None:
    # Row A: 2 buildings worth 500k each -> 10 % = 50k = minimum -> d = 0.10.
    # Row B: 4 buildings worth 250k each -> 10 % = 25k < 50k minimum -> d = 50k / 250k = 0.20.
    d = deductible_ratio(np.array([1e6, 1e6]), np.array([2.0, 4.0]), 0.10, 50_000.0)
    np.testing.assert_allclose(d, [0.10, 0.20])


def test_row_deductible_equals_per_building_sum() -> None:
    # Row B above at loss ratio 0.3: each building loses 75k, minus 50k deductible = 25k,
    # times 4 buildings = 100k. Row formula: V * max(lr - d, 0) = 1e6 * 0.1 = 100k.
    value, n, lr = 1e6, 4.0, 0.3
    d = deductible_ratio(np.array([value]), np.array([n]), 0.10, 50_000.0)[0]
    per_building = n * max(lr * value / n - max(0.10 * value / n, 50_000.0), 0.0)
    assert value * max(lr - d, 0.0) == pytest.approx(per_building) == pytest.approx(100_000.0)


def test_gross_event_losses_hand_case() -> None:
    model, imts, func, site, value, gmf = _toy_portfolio()
    imt_idx = asset_imt_index(model, func, imts)
    # Event 0 loss ratios: asset0 0.4, asset1 0.9, asset2 0 (see test_losses).
    ded = np.array([0.1, 0.5, 0.1])
    out = event_losses(
        gmf, imt_idx, site, func, np.vstack([value, value]), model,
        deductible=np.vstack([np.zeros(3), ded]),
    )
    # Gross event 0: 100 * (0.4 - 0.1) + 200 * (0.9 - 0.5) = 30 + 80 = 110.
    np.testing.assert_allclose(out, [[220.0, 0.0], [110.0, 0.0]])


def test_layer_recoveries() -> None:
    # 100 xs 50: below, inside, above the layer.
    np.testing.assert_allclose(layer_recoveries(np.array([30, 80, 500]), 100, 50), [0, 30, 100])


def test_cat_xl_hand_case() -> None:
    # 100 xs 50, 1 reinstatement at 100 %, three years:
    #   year 0: events 80, 200 -> recoveries 30 + 100 = 130 (<= 200 aggregate) ; reinstated 1.0
    #   year 1: three events of 300 -> 3 x 100 = 300, capped at 200          ; reinstated 1.0
    #   year 2: no events                                                   ; 0
    # E[recovery] = 330 / 3 = 110; E[reinstated] = 2/3; P = 110 / (1 + 2/3) = 66.
    # Check: P + E[reinstatement premium] = 66 + 66 * 2/3 = 110 = E[recovery].
    loss = np.array([80.0, 200.0, 300.0, 300.0, 300.0])
    year = np.array([0, 0, 1, 1, 1])
    ylt, s = cat_xl(loss, year, 3, limit=100, attachment=50, reinstatements=1,
                    reinstatement_rate=1.0)
    np.testing.assert_allclose(ylt["recovery"], [130, 200, 0])
    np.testing.assert_allclose(ylt["reinstated"], [1.0, 1.0, 0.0])
    assert s["expected_recovery"] == pytest.approx(110)
    assert s["pure_premium"] == pytest.approx(66)
    assert s["rate_on_line"] == pytest.approx(0.66)
    assert s["p_attach"] == pytest.approx(2 / 3)
    assert s["p_exhaust"] == pytest.approx(1 / 3)


def test_cat_xl_without_reinstatement_is_one_limit_per_year() -> None:
    ylt, s = cat_xl(np.array([300.0, 300.0]), np.array([0, 0]), 1, 100, 50, 0, 1.0)
    assert ylt["recovery"].iloc[0] == 100
    assert s["pure_premium"] == pytest.approx(100)  # no reinstatement premium to offset
