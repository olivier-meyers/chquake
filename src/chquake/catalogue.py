"""Historical earthquake rates, to check the event set against the observed catalogue.

Data: ESHM20 unified earthquake catalogue (declustered flags) and completeness super-zones
with their Mc(t) table. Danciu et al. (2021), Main Datasets of ESHM20,
doi:10.12686/eshm20-main-datasets (efehr/eshm20, CC BY 4.0). Magnitudes are Mw.

Declustering: the shapefile carries one TRUE/FALSE column per declustering variant. We use
`winGT_fs01`, which we read as the 10-character DBF truncation of `winGT_fs017`, the
variant our area-source file is named after (asm_ver12e_winGT_fs017); TRUE = kept as a
mainshock. Both readings are inferred, not documented in the file (e.g. the 30 May 1946
Sierre aftershocks are FALSE).

Completeness: the table gives (Mc, year) pairs per zone: events with M >= Mc are complete
from that year on. So magnitude m is complete from min{year : Mc <= m}.
"""

from pathlib import Path

import fiona
import numpy as np
import pandas as pd
import shapely
from scipy.stats import chi2

MAINSHOCK_FLAG = "winGT_fs01"


def load_catalogue(path: Path) -> pd.DataFrame:
    """Catalogue as lon, lat, year, mag, mainshock (bool)."""
    with fiona.open(path) as c:
        cols = ["longitude", "latitude", "year", "magnitude", MAINSHOCK_FLAG]
        rows = [[f["properties"][k] for k in cols] for f in c]
    df = pd.DataFrame(rows, columns=["lon", "lat", "year", "mag", "mainshock"])
    df["mainshock"] = df["mainshock"].map({"TRUE": True, "FALSE": False})
    if df["mainshock"].isna().any():
        raise ValueError(f"unexpected values in {MAINSHOCK_FLAG}")
    return df


def load_zone(shp: Path, mc_xlsx: Path, zone_id: str) -> tuple:
    """Polygon of one completeness super-zone and its Mc(t) table (columns mc, year)."""
    with fiona.open(shp) as c:
        geoms = [
            shapely.geometry.shape(f["geometry"]) for f in c if f["properties"]["CSZ_ID"] == zone_id
        ]
    if len(geoms) != 1:
        raise KeyError(f"zone {zone_id}: found {len(geoms)} polygons")
    t = pd.read_excel(mc_xlsx, sheet_name="McTable_CSZ_branch01_shallow")
    t = t[t["CSZ_ID"] == zone_id]
    # Mc is stored as e.g. 4.300000000000001; round so that Mc <= 4.3 behaves as intended.
    return geoms[0], pd.DataFrame({"mc": t["Mc"].round(2), "year": t["Time"].astype(int)})


def completeness_year(mc_table: pd.DataFrame, m: float) -> int:
    """First year from which magnitudes >= m are complete."""
    ok = mc_table["year"][mc_table["mc"] <= m + 1e-9]
    if ok.empty:
        raise ValueError(f"M{m} is below every Mc in the table")
    return int(ok.min())


def poisson_ci(n: int, level: float = 0.90) -> tuple[float, float]:
    """Exact (Garwood) confidence interval for a Poisson count."""
    a = 1 - level
    lo = 0.0 if n == 0 else chi2.ppf(a / 2, 2 * n) / 2
    return lo, chi2.ppf(1 - a / 2, 2 * n + 2) / 2


def observed_rates(
    cat: pd.DataFrame, region, mc_table: pd.DataFrame, thresholds, end_year: int
) -> pd.DataFrame:
    """Annual rate of declustered events with M >= m in region, over each m's complete period."""
    inside = shapely.contains_xy(region, cat["lon"], cat["lat"]) & cat["mainshock"]
    rows = []
    for m in thresholds:
        start = completeness_year(mc_table, m)
        n_yr = end_year - start + 1
        sel = inside & (cat["mag"] >= m) & cat["year"].between(start, end_year)
        n = int(sel.sum())
        lo, hi = poisson_ci(n)
        rows.append(
            {
                "m_min": m,
                "from_year": start,
                "years": n_yr,
                "n_events": n,
                "rate": n / n_yr,
                "rate_lo90": lo / n_yr,
                "rate_hi90": hi / n_yr,
            }
        )
    return pd.DataFrame(rows).set_index("m_min")


def modelled_rates(events: pd.DataFrame, n_years: int, region, thresholds) -> pd.Series:
    """Annual rate of simulated events with M >= m and epicentre in region.

    Simulated magnitudes are bin centres (4.55, 4.65, ...), so M >= 5.0 selects the bins
    from [5.0, 5.1) up, the same events a catalogue M >= 5.0 cut selects.
    """
    inside = shapely.contains_xy(region, events["lon"], events["lat"])
    mag = events["mag"].to_numpy()
    return pd.Series(
        {m: (inside & (mag >= m)).sum() / n_years for m in thresholds}, name="model_rate"
    )


def exposure_region(exposure: pd.DataFrame, zone) -> shapely.Geometry:
    """Convex hull of the exposure points, clipped to one completeness zone."""
    hull = shapely.MultiPoint(np.c_[exposure["lon"], exposure["lat"]]).convex_hull
    return hull.intersection(zone)
