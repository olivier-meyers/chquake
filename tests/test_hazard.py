"""Hazard: GR sampling reproduces input rates, epicentres, correlation, ground-motion fields."""

import numpy as np
import pandas as pd
import pytest
import shapely

from chquake.hazard import (
    AreaSources,
    correlation_factors,
    ground_motion,
    load_area_sources,
    load_gmpe_branches,
    sample_events,
    select_sources,
)

IMTS = ["PGA", "SA(0.3)", "SA(0.6)", "SA(1.0)"]


def _toy_sources() -> AreaSources:
    """One ~1 deg square source near Bern with a 3-bin MFD."""
    sq = shapely.Polygon([(7.0, 46.5), (8.0, 46.5), (8.0, 47.0), (7.0, 47.0)])
    return AreaSources(
        np.array(["toy"]),
        [sq],
        np.array([10.0]),
        [np.array([4.55, 4.65, 4.75])],
        [np.array([0.05, 0.02, 0.01])],
    )


def _toy_sites(lons) -> pd.DataFrame:
    n = len(lons)
    return pd.DataFrame(
        {
            "lon": np.asarray(lons, float),
            "lat": np.full(n, 46.9),
            "slope": 0.05,
            "geology": "CENOZOIC",
            "region": 1,
        }
    )


def _tau_phi(gsim, mag: float) -> tuple[float, float]:
    """Between- and within-event sigma for PGA at one magnitude (site-independent here)."""
    from openquake.hazardlib import imt as oq_imt
    from openquake.hazardlib.contexts import simple_cmaker

    ctx = simple_cmaker([gsim], ["PGA"]).new_ctx(1)
    ctx["mag"], ctx["hypo_depth"], ctx["rjb"], ctx["rrup"] = mag, 10.0, 5.0, 5.0
    ctx["slope"], ctx["geology"], ctx["region"] = 0.05, "CENOZOIC", 1
    out = [np.zeros((1, 1)) for _ in range(4)]
    gsim.compute(ctx, [oq_imt.PGA()], *out)
    return float(out[2][0, 0]), float(out[3][0, 0])


def test_gr_sampling_reproduces_input_rates() -> None:
    src = _toy_sources()
    n_years = 200_000
    ev = sample_events(src, n_years, seed=0)
    for m, rate in zip(src.mags[0], src.rates[0], strict=True):
        count = (ev["mag"] == m).sum()
        sd = np.sqrt(rate * n_years)  # Poisson standard deviation of the count
        assert abs(count - rate * n_years) < 4 * sd
    assert ev["year"].between(0, n_years - 1).all()
    assert (np.diff(ev["year"]) >= 0).all()


def test_epicentres_uniform_inside_polygon() -> None:
    src = _toy_sources()
    ev = sample_events(src, 200_000, seed=1)
    assert shapely.contains_xy(src.polygons[0], ev["lon"], ev["lat"]).all()
    assert ev["lon"].mean() == pytest.approx(7.5, abs=0.01)
    assert ev["lat"].mean() == pytest.approx(46.75, abs=0.01)


def test_eshm20_sources_and_rates(area_sources_path) -> None:
    src = load_area_sources(area_sources_path)
    assert len(src.ids) == 363  # all Shallow Default area sources
    near = select_sources(src, _toy_sites([7.45]), max_km=0)
    assert len(near.ids) == 1  # Bern lies in exactly one source polygon
    ev = sample_events(near, 100_000, seed=2)
    rate = near.rates[0].sum()
    assert len(ev) / 1e5 == pytest.approx(rate, rel=4 / np.sqrt(rate * 1e5))


def test_gmpe_logic_tree(gmpe_logic_tree_path) -> None:
    ids, gsims, w = load_gmpe_branches(gmpe_logic_tree_path)
    assert len(gsims) == 15
    assert w.sum() == pytest.approx(1.0)
    assert ids[int(np.argmax(w))] == "Shallow_Default_MidStress_CentralAtt"


def test_spatial_and_cross_im_correlation(gmpe_logic_tree_path) -> None:
    """Empirical residual correlations match JB09 (case 1) and BJ08."""
    _, gsims, w = load_gmpe_branches(gmpe_logic_tree_path)
    sites = _toy_sites([7.5, 7.5 + 10 / 76.0])  # ~10 km apart
    spatial, cross = correlation_factors(sites, IMTS)
    ev = pd.DataFrame(
        {
            "mag": [6.0] * 4000,
            "lon": 7.55,
            "lat": 46.9,
            "depth": 10.0,
            "src_key": 0,
            "src_idx": np.arange(4000),
        }
    )
    gmf = ground_motion(ev, sites, gsims[int(np.argmax(w))], IMTS, spatial, cross, seed=3)
    ln = np.log(gmf)
    # Total residual correlation between the sites for PGA:
    # (tau^2 + phi^2 * rho_JB09(h)) / (tau^2 + phi^2), tau and phi from the GMPE itself.
    tau, phi = _tau_phi(gsims[int(np.argmax(w))], 6.0)
    rho_w = (spatial[0] @ spatial[0].T)[0, 1]
    expected = (tau**2 + phi**2 * rho_w) / (tau**2 + phi**2)
    r_sites = np.corrcoef(ln[0, :, 0], ln[0, :, 1])[0, 1]
    assert r_sites == pytest.approx(expected, abs=0.05)
    # PGA vs SA(1.0) at one site, BJ08 target
    r_imt = np.corrcoef(ln[0, :, 0], ln[3, :, 0])[0, 1]
    target = (cross @ cross.T)[0, 3]
    assert r_imt == pytest.approx(target, abs=0.06)


def test_ground_motion_zero_beyond_max_distance(gmpe_logic_tree_path) -> None:
    _, gsims, _ = load_gmpe_branches(gmpe_logic_tree_path)
    sites = _toy_sites([7.5, 10.5])  # second site ~230 km east
    spatial, cross = correlation_factors(sites, IMTS)
    ev = pd.DataFrame(
        {"mag": [6.5], "lon": 7.5, "lat": 46.9, "depth": 10.0, "src_key": 0, "src_idx": [0]}
    )
    gmf = ground_motion(ev, sites, gsims[0], IMTS, spatial, cross, seed=4)
    assert (gmf[:, 0, 0] > 0).all()
    assert (gmf[:, 0, 1] == 0).all()
