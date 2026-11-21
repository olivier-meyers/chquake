"""Historical-rate check: completeness lookup and rate counting on hand cases."""

import pandas as pd
import pytest
import shapely

from chquake.catalogue import completeness_year, modelled_rates, observed_rates, poisson_ci

MC = pd.DataFrame({"mc": [3.7, 4.3, 4.9, 5.9], "year": [1852, 1812, 1685, 1295]})
BOX = shapely.box(0, 0, 1, 1)


def test_completeness_year() -> None:
    assert completeness_year(MC, 5.0) == 1685  # Mc 4.9 <= 5.0 since 1685
    assert completeness_year(MC, 4.3) == 1812  # equality counts
    assert completeness_year(MC, 6.5) == 1295
    with pytest.raises(ValueError):
        completeness_year(MC, 3.0)


def test_observed_rates_hand_case() -> None:
    cat = pd.DataFrame(
        {
            "lon": [0.5, 0.5, 0.5, 0.5, 2.0],
            "lat": [0.5] * 5,
            "year": [1600, 1700, 1800, 1900, 1900],
            "mag": [6.0, 5.2, 5.0, 5.5, 6.0],
            "mainshock": [True, True, False, True, True],
        }
    )
    obs = observed_rates(cat, BOX, MC, [5.0], end_year=1984)
    # From 1685: 1700 (M5.2) and 1900 (M5.5) count; 1600 is before completeness,
    # 1800 is an aftershock, the last event is outside the region. 300 years.
    assert obs.loc[5.0, "n_events"] == 2
    assert obs.loc[5.0, "years"] == 300
    assert obs.loc[5.0, "rate"] == pytest.approx(2 / 300)


def test_modelled_rates_bin_centres() -> None:
    ev = pd.DataFrame({"mag": [4.95, 5.05, 5.55], "lon": 0.5, "lat": 0.5})
    r = modelled_rates(ev, 10, BOX, [5.0, 5.5])
    assert r[5.0] == pytest.approx(0.2) and r[5.5] == pytest.approx(0.1)


def test_poisson_ci() -> None:
    lo, hi = poisson_ci(0)
    assert lo == 0 and hi == pytest.approx(2.9957, abs=1e-3)  # -ln(0.05)
    lo, hi = poisson_ci(22)
    assert lo < 22 < hi
