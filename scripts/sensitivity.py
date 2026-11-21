"""One-at-a-time sensitivity of AAL and return-period losses to the modelling choices.

Usage: python scripts/sensitivity.py   (about 1 minute per case; writes outputs/sensitivity.csv)
Every case uses the same seed, so differences reflect the choice plus Monte Carlo noise.
"""

import copy
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run import load_config, simulate  # noqa: E402

from chquake.metrics import aal, ep_table  # noqa: E402

CASES = {
    "baseline": {},
    "max_distance_300km": {("hazard", "max_distance_km"): 300},
    "no_within_cross_im (OpenQuake)": {("hazard", "correlation", "within_cross_im"): False},
    "jb09_case2_clustered": {("hazard", "correlation", "vs30_clustering"): True},
    "no_secondary_uncertainty": {("vulnerability", "secondary_uncertainty"): False},
    "central_gmpe_branch": {("hazard", "gmpe_branch"): "central"},
}


def main() -> None:
    base = load_config(ROOT / "config.yaml")
    rows = {}
    for name, overrides in CASES.items():
        cfg = copy.deepcopy(base)
        for keys, value in overrides.items():
            d = cfg
            for k in keys[:-1]:
                d = d[k]
            d[keys[-1]] = value
        print(f"--- {name}", flush=True)
        _, ylt = simulate(cfg, ROOT / cfg["data"]["raw_dir"], cfg["run"]["seed"])
        t = ep_table(ylt)
        rows[name] = {
            "AAL": aal(ylt),
            **{f"OEP_{rp}": t.loc[rp, "OEP"] for rp in (100, 250, 1000)},
            "AEP_200": t.loc[200, "AEP"],
            "TVaR_AEP_100": t.loc[100, "TVaR_AEP"],
        }
    df = pd.DataFrame(rows).T
    df.to_csv(ROOT / base["run"]["output_dir"] / "sensitivity.csv")
    print((df / 1e6).round(0).to_string())
    print("\nRelative to baseline:")
    print((df / df.loc["baseline"]).round(2).to_string())


if __name__ == "__main__":
    main()
