"""Residential building exposure for Switzerland from the ESRM20 exposure model.

Source: ESRM20 exposure model v1.0, efehr/esrm20_exposure, file
`_exposure_models/Exposure_Model_Switzerland_Res.csv` (CC BY 4.0).
Crowley et al. (2020), Earthquake Spectra, doi:10.1177/8755293020919429;
data doi:10.5281/zenodo.4062044.

What one row is: one building class (GEM taxonomy string) in one municipality, with all
its buildings lumped at the municipality's single reference point (2,224 municipalities,
2016 census). Values are in EUR at 2020 prices. The total replacement cost includes
structure (30 %), non-structural elements (50 %) and contents (20 %); see
`sources/European_Exposure_Model_Data_Inputs_Sources.xlsx` in the same repo.
ESRM20 applies its total-replacement-cost vulnerability functions to this total.
"""

from pathlib import Path

import pandas as pd

# Source column -> name used in this package.
COLUMNS = {
    "LONGITUDE": "lon",
    "LATITUDE": "lat",
    "TAXONOMY": "taxonomy",
    "BUILDINGS": "buildings",
    "DWELLINGS": "dwellings",
    "SETTLEMENT_TYPE": "settlement",
    "TOTAL_REPL_COST_EUR": "value",
    "COST_STRUCTURAL_EUR": "value_structural",
    "COST_NONSTRUCTURAL_EUR": "value_nonstructural",
    "COST_CONTENTS_EUR": "value_contents",
    "NAME_1": "canton",
    "ID_3": "municipality_id",
    "NAME_3": "municipality",
}


def load_exposure(path: Path) -> pd.DataFrame:
    """Read the ESRM20 Swiss residential exposure CSV into one row per asset."""
    df = pd.read_csv(path, usecols=list(COLUMNS)).rename(columns=COLUMNS)
    if df.isna().any().any():
        raise ValueError(f"missing values in {path}")
    if (df["value"] <= 0).any():
        raise ValueError("non-positive replacement values")
    return df.reset_index(drop=True)


def value_by_canton(exposure: pd.DataFrame) -> pd.DataFrame:
    """Total buildings and replacement value per canton, largest value first."""
    return (
        exposure.groupby("canton")[["buildings", "value"]]
        .sum()
        .sort_values("value", ascending=False)
    )
