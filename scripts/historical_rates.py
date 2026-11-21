"""Compare modelled and historical earthquake rates in Switzerland (M2 check).

Usage: python scripts/historical_rates.py   (needs outputs/elt.csv from run.py)
Region: convex hull of the Swiss exposure points, clipped to ESHM20 completeness super-zone
SZ02 (CSZ_CH), so one completeness table applies. Writes outputs/historical_rates.csv.
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run import load_config  # noqa: E402

from chquake.catalogue import (  # noqa: E402
    exposure_region,
    load_catalogue,
    load_zone,
    modelled_rates,
    observed_rates,
)
from chquake.exposure import load_exposure  # noqa: E402

THRESHOLDS = (4.5, 5.0, 5.5, 6.0)


def main() -> None:
    cfg = load_config(ROOT / "config.yaml")
    raw, out = ROOT / cfg["data"]["raw_dir"], ROOT / cfg["run"]["output_dir"]
    v = cfg["validation"]
    zone, mc = load_zone(raw / v["completeness_zones"], raw / v["completeness_table"], v["zone"])
    region = exposure_region(load_exposure(raw / cfg["data"]["exposure"]), zone)
    cat = load_catalogue(raw / v["catalogue"])
    obs = observed_rates(cat, region, mc, THRESHOLDS, end_year=int(cat["year"].max()))
    events = pd.read_csv(out / "elt.csv", usecols=["mag", "lon", "lat"])
    model = modelled_rates(events, cfg["run"]["n_years"], region, THRESHOLDS)
    table = obs.join(model)
    table["model/obs"] = table["model_rate"] / table["rate"]
    table.to_csv(out / "historical_rates.csv")
    print(f"Region: {region.area:.2f} deg2; catalogue ends {cat['year'].max()}")
    print(table.round(4).to_string())


if __name__ == "__main__":
    main()
