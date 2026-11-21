"""Site conditions at the exposure points, from the ESRM20 site model for Switzerland.

Source: ESRM20 OpenQuake input files v1.0 (efehr/esrm20), `Vs30/Site_model_Switzerland.xml`
(CC BY 4.0); Crowley et al. (2021), doi:10.7414/EUC-EFEHR-TR002-ESRM20. Each of its 4,053
points carries topographic slope (m/m), a geological era class, the attenuation region used
by Kotha et al. (2020) and a slope-inferred Vs30. The ground-motion model uses slope,
geology and region (doi:10.1007/s10518-020-00869-1); Vs30 is kept for reference only.

Hazard is computed at the 2,224 unique exposure points (municipality reference points).
Each takes the attributes of its nearest site-model point: 2,183 coincide exactly, the rest
lie within about 2.5 km. A point farther than `max_km` from any site is an error rather
than a silent fallback.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EARTH_RADIUS_KM = 6371.0


def load_site_model(path: Path) -> pd.DataFrame:
    """Parse the NRML site model into one row per site."""
    rows = [s.attrib for s in ET.parse(path).getroot().iter() if s.tag.endswith("}site")]
    df = pd.DataFrame(rows)
    for col in ("lon", "lat", "vs30", "slope", "xvf"):
        df[col] = df[col].astype(float)
    df["region"] = df["region"].astype(int)
    return df[["lon", "lat", "slope", "geology", "region", "vs30"]]


def _unit_vectors(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lon, lat = np.radians(lon), np.radians(lat)
    return np.c_[np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]


def exposure_sites(
    exposure: pd.DataFrame, site_model: pd.DataFrame, max_km: float = 5.0
) -> tuple[pd.DataFrame, np.ndarray]:
    """Hazard sites (unique exposure points with site attributes) and each asset's site index."""
    points, site_of_asset = np.unique(
        exposure[["lon", "lat"]].to_numpy(), axis=0, return_inverse=True
    )
    tree = cKDTree(_unit_vectors(site_model["lon"].to_numpy(), site_model["lat"].to_numpy()))
    chord, idx = tree.query(_unit_vectors(points[:, 0], points[:, 1]))
    dist_km = 2 * EARTH_RADIUS_KM * np.arcsin(chord / 2)
    if dist_km.max() > max_km:
        raise ValueError(f"exposure point {dist_km.max():.1f} km from the nearest site")
    sites = site_model.iloc[idx].reset_index(drop=True).drop(columns=["lon", "lat"])
    sites.insert(0, "lat", points[:, 1])
    sites.insert(0, "lon", points[:, 0])
    sites["snap_km"] = dist_km
    return sites, site_of_asset.ravel()
