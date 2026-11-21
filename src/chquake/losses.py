"""Ground-motion fields -> ground-up event losses -> event and year loss tables (ELT, YLT).

Pipeline per event e and asset i:
    im[e, i]   = ground motion at the asset's site, for the IMT its vulnerability function uses
    lr[e, i]   = loss ratio: mean of the function at im (or a Beta draw around it, if
                 secondary uncertainty is on; see `vulnerability.sample_loss_ratio`)
    loss[e]    = sum_i lr[e, i] * value[i]           (ground-up, portfolio level, EUR 2020)

All assets of a municipality share one site (ESRM20 lumps them at one reference point), so
the ground-motion field is computed per site and looked up per asset.

ELT = one row per event (event id, year, loss). YLT = one row per simulated year, including
years with no loss, with the annual aggregate (sum, for AEP) and the annual maximum event
loss (for OEP).
"""

import numpy as np
import pandas as pd

from chquake.vulnerability import VulnerabilityModel, loss_ratio_moments, sample_loss_ratio


def asset_imt_index(model: VulnerabilityModel, func: np.ndarray, imts: list[str]) -> np.ndarray:
    """Position in `imts` of the intensity measure each asset's vulnerability function needs."""
    pos = {imt: k for k, imt in enumerate(imts)}
    needed = model.imt[func]
    missing = set(needed) - set(pos)
    if missing:
        raise KeyError(f"ground-motion field lacks IMTs {sorted(missing)}")
    return np.array([pos[m] for m in needed])


def event_losses(
    gmf: np.ndarray,
    imt_of_asset: np.ndarray,
    site_of_asset: np.ndarray,
    func: np.ndarray,
    value: np.ndarray,
    model: VulnerabilityModel,
    rng: np.random.Generator | None = None,
    chunk: int = 64,
) -> np.ndarray:
    """Ground-up portfolio loss per event.

    gmf: (n_imt, n_events, n_sites) intensities in g. imt_of_asset, site_of_asset, func and
    value: (n_assets,). rng=None uses mean loss ratios; otherwise one Beta draw per asset row
    per event, independent across rows and events (open choice, see README Limitations).

    Events are processed in chunks to bound memory, and only asset-event pairs with shaking
    above the lowest vulnerability grid point (loss ratio exactly 0 below it) are evaluated,
    which skips most pairs for the many small, distant events.
    """
    n_events = gmf.shape[1]
    out = np.zeros(n_events)
    for start in range(0, n_events, chunk):
        ev = np.arange(start, min(start + chunk, n_events))
        im = gmf[imt_of_asset[None, :], ev[:, None], site_of_asset[None, :]]  # (chunk, assets)
        e_idx, a_idx = np.nonzero(im >= model.iml[0])
        mean, cov = loss_ratio_moments(model, func[a_idx], im[e_idx, a_idx])
        lr = mean if rng is None else sample_loss_ratio(mean, cov, rng)
        out[start : start + len(ev)] = np.bincount(
            e_idx, weights=lr * value[a_idx], minlength=len(ev)
        )
    return out


def build_elt(event_id: np.ndarray, year: np.ndarray, loss: np.ndarray) -> pd.DataFrame:
    """Event loss table: one row per event with its simulated year and ground-up loss."""
    return pd.DataFrame({"event_id": event_id, "year": year, "loss": loss})


def build_ylt(elt: pd.DataFrame, n_years: int, loss_col: str = "loss") -> pd.DataFrame:
    """Year loss table over years 0..n_years-1, including years with no events or no loss.

    agg_loss = sum of event losses in the year (-> AEP); max_loss = largest single event
    loss in the year (-> OEP).
    """
    if len(elt) and (elt["year"].min() < 0 or elt["year"].max() >= n_years):
        raise ValueError("ELT years outside 0..n_years-1")
    g = elt.groupby("year")[loss_col]
    ylt = pd.DataFrame(index=pd.RangeIndex(n_years, name="year"))
    ylt["agg_loss"] = g.sum().reindex(ylt.index, fill_value=0.0)
    ylt["max_loss"] = g.max().reindex(ylt.index, fill_value=0.0)
    ylt["n_events"] = g.size().reindex(ylt.index, fill_value=0).astype(int)
    return ylt
