"""Stochastic event set and correlated ground-motion fields.

Sources and parameters (all verified, see README):
- ESHM20 area-source model as packaged for ESRM20 (efehr/esrm20 v1.0,
  `asm_ver12e_winGT_fs017_combined.xml`; ESHM20: Danciu et al. 2021, doi:10.12686/a15).
  Each area source has a polygon, one hypocentral depth, one nodal plane, point ruptures
  (PointMSR) and an incremental magnitude-frequency distribution: annual rates in 0.1-wide
  bins from Mw 4.55 (bin magnitudes as listed, OpenQuake convention).
- Ground-motion model: Kotha et al. (2020) ESHM20 backbone with slope/geology site term,
  doi:10.1007/s10518-020-00869-1, via openquake.hazardlib; 15-branch logic tree from
  `gmpe_logic_tree_5br_slope_geology.xml` (5 stress x 3 attenuation branches).
- Spatial correlation of within-event residuals: Jayaram & Baker (2009),
  doi:10.1002/eqe.922, rho(h) = exp(-3h/b(T)) (OpenQuake `jbcorrelation`).
- Correlation across IMTs: Baker & Jayaram (2008), doi:10.1193/1.2857544 (OpenQuake
  `BakerJayaram2008`).

Event generation: for every source and magnitude bin the number of events in N years is
Poisson(rate * N); each event gets a uniform random year and a uniform random epicentre in
the source polygon (the continuous limit of OpenQuake's area-source gridding).
Point ruptures: Rjb = epicentral distance.

Ground motion for event e, site s, IMT m (natural log, g):
    ln Y = mu(e,s,m) + tau(e,s,m) * eta(e,m) + phi(e,s,m) * eps(e,s,m)
eta: between-event, standard normal, correlated across IMTs (BJ08).
eps: within-event, standard normal, spatially correlated per IMT (JB09); with
`within_cross_im` also correlated across IMTs at the same underlying draw (our option C;
OpenQuake correlates only eta across IMTs). Construction: z ~ N(0, R_BJ08) per site, then
eps_m = L_m z_m with L_m the JB09 Cholesky factor of IMT m. This is a valid covariance;
the same-site cross-IMT correlation becomes rho_BJ08 * (L_k L_l^T)_ss, slightly below
rho_BJ08 where the two spatial ranges differ (an approximation of Loth & Baker 2013).

Truncation (optional, `truncation` = t): the total normalised residual
r = (tau*eta + phi*eps) / sqrt(tau^2 + phi^2) is standard normal at every site. It is mapped
through r -> Phi^-1(Phi(-t) + Phi(r) * (1 - 2 Phi(-t))), which makes each marginal exactly a
normal truncated at +-t (the distribution a truncated PSHA hazard integral uses) while keeping
the Gaussian-copula (rank) correlation between sites and IMTs. Clipping at +-t would instead
pile the 0.27 % tail mass onto the bound.
"""

import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from openquake.hazardlib import imt as oq_imt
from openquake.hazardlib import valid
from openquake.hazardlib.contexts import simple_cmaker
from openquake.hazardlib.correlation import jbcorrelation
from openquake.hazardlib.cross_correlation import BakerJayaram2008
from scipy.special import ndtr, ndtri

NRML04 = "{http://openquake.org/xmlns/nrml/0.4}"
NRML05 = "{http://openquake.org/xmlns/nrml/0.5}"
GML = "{http://www.opengis.net/gml}"
EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class AreaSources:
    """Area sources; row i of each array belongs to source ids[i]."""

    ids: np.ndarray  # (n_src,)
    polygons: list  # shapely Polygons in lon/lat
    hypo_depth: np.ndarray  # (n_src,) km
    mags: list  # per source: bin magnitudes
    rates: list  # per source: annual rate per bin


def load_area_sources(path: Path, trt: str = "Shallow Default") -> AreaSources:
    """Parse ESHM20 area sources of one tectonic region type."""
    ids, polys, depth, mags, rates = [], [], [], [], []
    for src in ET.parse(path).getroot().iter(NRML04 + "areaSource"):
        if src.get("tectonicRegion") != trt:
            continue
        if src.findtext(NRML04 + "magScaleRel").strip() != "PointMSR":
            raise NotImplementedError(f"{src.get('id')}: only point ruptures supported")
        hd = src.findall(f".//{NRML04}hypoDepth")
        if len(hd) != 1:
            raise NotImplementedError(f"{src.get('id')}: expected one hypocentral depth")
        pos = np.array(src.find(f".//{GML}posList").text.split(), float).reshape(-1, 2)
        mfd = src.find(NRML04 + "incrementalMFD")
        r = np.array(mfd.find(NRML04 + "occurRates").text.split(), float)
        m = float(mfd.get("minMag")) + float(mfd.get("binWidth")) * np.arange(len(r))
        ids.append(src.get("id"))
        polys.append(shapely.Polygon(pos))
        depth.append(float(hd[0].get("depth")))
        mags.append(np.round(m, 2))
        rates.append(r)
    return AreaSources(np.array(ids), polys, np.array(depth), mags, rates)


def _local_xy(lon: np.ndarray, lat: np.ndarray, lon0: float, lat0: float) -> np.ndarray:
    """Equirectangular km coordinates around (lon0, lat0); ~1 % accurate within 300 km."""
    kx = np.pi / 180 * EARTH_RADIUS_KM * np.cos(np.radians(lat0))
    ky = np.pi / 180 * EARTH_RADIUS_KM
    return np.c_[(np.asarray(lon) - lon0) * kx, (np.asarray(lat) - lat0) * ky]


def select_sources(sources: AreaSources, sites: pd.DataFrame, max_km: float) -> AreaSources:
    """Keep sources whose polygon comes within max_km of any site."""
    lon0, lat0 = sites["lon"].mean(), sites["lat"].mean()
    pts = shapely.MultiPoint(_local_xy(sites["lon"], sites["lat"], lon0, lat0))
    keep = []
    for i, p in enumerate(sources.polygons):
        xy = np.asarray(p.exterior.coords)
        poly = shapely.Polygon(_local_xy(xy[:, 0], xy[:, 1], lon0, lat0))
        if poly.distance(pts) <= max_km:
            keep.append(i)
    return AreaSources(
        sources.ids[keep],
        [sources.polygons[i] for i in keep],
        sources.hypo_depth[keep],
        [sources.mags[i] for i in keep],
        [sources.rates[i] for i in keep],
    )


def _uniform_in_polygon(poly, n: int, rng: np.random.Generator) -> np.ndarray:
    """n points uniform by area in a lon/lat polygon (rejection sampling, local projection)."""
    lon0, lat0 = poly.centroid.x, poly.centroid.y
    xy = np.asarray(poly.exterior.coords)
    local = shapely.Polygon(_local_xy(xy[:, 0], xy[:, 1], lon0, lat0))
    x0, y0, x1, y1 = local.bounds
    out = np.empty((0, 2))
    while len(out) < n:
        cand = rng.uniform([x0, y0], [x1, y1], size=(2 * (n - len(out)) + 16, 2))
        out = np.vstack([out, cand[shapely.contains_xy(local, cand[:, 0], cand[:, 1])]])
    out = out[:n]
    kx = np.pi / 180 * EARTH_RADIUS_KM * np.cos(np.radians(lat0))
    ky = np.pi / 180 * EARTH_RADIUS_KM
    return np.c_[out[:, 0] / kx + lon0, out[:, 1] / ky + lat0]


def sample_events(sources: AreaSources, n_years: int, seed: int) -> pd.DataFrame:
    """Stochastic event set: Poisson counts per source and bin, uniform year and epicentre.

    Each source draws from its own random stream, keyed by (seed, source id), so adding or
    removing other sources (e.g. a larger max distance) leaves its events unchanged
    (common random numbers for sensitivity tests).
    """
    parts = []
    for i, sid in enumerate(sources.ids):
        key = zlib.crc32(str(sid).encode())
        rng = np.random.default_rng([seed, key])
        counts = rng.poisson(sources.rates[i] * n_years)
        n = counts.sum()
        if n == 0:
            continue
        lonlat = _uniform_in_polygon(sources.polygons[i], n, rng)
        parts.append(
            pd.DataFrame(
                {
                    "source": sid,
                    "src_key": key,  # (src_key, src_idx) identifies the event across runs
                    "src_idx": np.arange(n),
                    "mag": np.repeat(sources.mags[i], counts),
                    "lon": lonlat[:, 0],
                    "lat": lonlat[:, 1],
                    "depth": sources.hypo_depth[i],
                    "year": rng.integers(0, n_years, n),
                }
            )
        )
    events = pd.concat(parts, ignore_index=True).sort_values(["year", "source"], kind="stable")
    events.insert(0, "event_id", np.arange(len(events)))
    return events.reset_index(drop=True)


def load_gmpe_branches(path: Path, trt: str = "Shallow Default") -> tuple[list, list, np.ndarray]:
    """Branch ids, GSIM objects and weights of one tectonic region type's GMPE logic tree."""
    for bs in ET.parse(path).getroot().iter(NRML05 + "logicTreeBranchSet"):
        if bs.get("applyToTectonicRegionType") != trt:
            continue
        ids, gsims, weights = [], [], []
        for br in bs.iter(NRML05 + "logicTreeBranch"):
            ids.append(br.get("branchID"))
            gsims.append(valid.gsim(br.findtext(NRML05 + "uncertaintyModel").strip()))
            weights.append(float(br.findtext(NRML05 + "uncertaintyWeight")))
        w = np.array(weights)
        if not np.isclose(w.sum(), 1.0):
            raise ValueError(f"{trt} branch weights sum to {w.sum()}")
        return ids, gsims, w / w.sum()
    raise KeyError(f"no GMPE branch set for {trt}")


def _haversine_km(lon1, lat1, lon2, lat2) -> np.ndarray:
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def correlation_factors(
    sites: pd.DataFrame, imts: list[str], vs30_clustering: bool = False
) -> tuple[np.ndarray, np.ndarray]:
    """Cholesky factors: spatial (n_imt, n_sites, n_sites) per IMT and cross-IMT (n_imt, n_imt)."""
    lon, lat = sites["lon"].to_numpy(), sites["lat"].to_numpy()
    dist = _haversine_km(lon[:, None], lat[:, None], lon[None, :], lat[None, :])
    objs = [oq_imt.from_string(s) for s in imts]
    jitter = 1e-10 * np.eye(len(sites))  # numerical guard only
    spatial = np.stack(
        [np.linalg.cholesky(jbcorrelation(dist, m, vs30_clustering) + jitter) for m in objs]
    )
    bj = BakerJayaram2008()
    cross = np.array([[bj.get_correlation(a, b) for b in objs] for a in objs])
    return spatial, np.linalg.cholesky(cross)


def truncate_normal(r: np.ndarray, level: float | None) -> np.ndarray:
    """Map standard-normal values to a normal truncated at +-level (monotone; None = no-op)."""
    if level is None:
        return r
    lo = ndtr(-level)
    return ndtri(lo + ndtr(r) * (1.0 - 2.0 * lo))


def ground_motion(
    events: pd.DataFrame,
    sites: pd.DataFrame,
    gsim,
    imts: list[str],
    spatial_chol: np.ndarray,
    cross_chol: np.ndarray,
    seed: int,
    max_km: float = 200.0,
    within_cross_im: bool = True,
    truncation: float | None = None,
) -> np.ndarray:
    """Sampled ground motion (n_imt, n_events, n_sites) in g; 0 beyond max_km.

    Each event's residuals come from its own stream keyed by (seed, src_key, src_idx), so
    an event's raw draws are the same in every run that contains it. `truncation` is the
    level (in total sigma) at which the residual distribution is truncated; None = none.
    """
    n_ev, n_s, n_m = len(events), len(sites), len(imts)
    rjb = _haversine_km(
        events["lon"].to_numpy()[:, None],
        events["lat"].to_numpy()[:, None],
        sites["lon"].to_numpy()[None, :],
        sites["lat"].to_numpy()[None, :],
    )  # point ruptures: Joyner-Boore distance = epicentral distance
    e_idx, s_idx = np.nonzero(rjb <= max_km)

    # Median and standard deviations from the GMPE, for the pairs within max_km only.
    ctx = simple_cmaker([gsim], imts).new_ctx(len(e_idx))
    ctx["mag"] = events["mag"].to_numpy()[e_idx]
    ctx["hypo_depth"] = events["depth"].to_numpy()[e_idx]
    ctx["rjb"] = ctx["rrup"] = rjb[e_idx, s_idx]
    ctx["slope"] = sites["slope"].to_numpy()[s_idx]
    ctx["geology"] = sites["geology"].to_numpy()[s_idx]
    ctx["region"] = sites["region"].to_numpy()[s_idx]
    ctx["sids"] = s_idx
    mean, sig, tau, phi = (np.zeros((n_m, len(e_idx))) for _ in range(4))
    gsim.compute(ctx, [oq_imt.from_string(s) for s in imts], mean, sig, tau, phi)

    # Residuals: between-event correlated across IMTs; within-event spatially correlated.
    eta, z = np.empty((n_ev, n_m)), np.empty((n_ev, n_s, n_m))
    for e, (k, i) in enumerate(zip(events["src_key"], events["src_idx"], strict=True)):
        g = np.random.default_rng([seed, 1, int(k), int(i)])
        eta[e], z[e] = g.standard_normal(n_m), g.standard_normal((n_s, n_m))
    eta = eta @ cross_chol.T  # (E, M)
    if within_cross_im:
        z = z @ cross_chol.T
    eps = np.stack([z[:, :, m] @ spatial_chol[m].T for m in range(n_m)])  # (M, E, S)

    sigma = np.sqrt(tau**2 + phi**2)
    r = (tau * eta[e_idx].T + phi * eps[:, e_idx, s_idx]) / sigma  # standard normal
    gmf = np.zeros((n_m, n_ev, n_s))
    gmf[:, e_idx, s_idx] = np.exp(mean + sigma * truncate_normal(r, truncation))
    return gmf
