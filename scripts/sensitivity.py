"""One-at-a-time sensitivity of AAL and return-period losses to the modelling choices.

Usage: python scripts/sensitivity.py [case ...]   (about 5 minutes per case; default all)
Writes outputs/sensitivity.csv (all cases) or updates the named rows of an existing file.
Every case uses the same seed, so differences reflect the choice plus Monte Carlo noise.
"""

import copy
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run import load_config, simulate  # noqa: E402

from chquake.losses import build_ylt  # noqa: E402
from chquake.metrics import aal, ep_table  # noqa: E402

CASES = {
    "baseline": {},
    "max_distance_300km": {("hazard", "max_distance_km"): 300},
    "no_within_cross_im (OpenQuake)": {("hazard", "correlation", "within_cross_im"): False},
    "jb09_case2_clustered": {("hazard", "correlation", "vs30_clustering"): True},
    "no_secondary_uncertainty": {("vulnerability", "secondary_uncertainty"): False},
    "central_gmpe_branch": {("hazard", "gmpe_branch"): "central"},
    "untruncated": {("hazard", "truncation_level"): None},
    "values_x2.43 (ERM-CH23 total)": {("exposure", "value_scale"): 2.43},
}


def main() -> None:
    base = load_config(ROOT / "config.yaml")
    names = sys.argv[1:] or list(CASES)
    rows = {}
    for name in names:
        cfg = copy.deepcopy(base)
        for keys, value in CASES[name].items():
            d = cfg
            for k in keys[:-1]:
                d = d[k]
            d[keys[-1]] = value
        print(f"--- {name}", flush=True)
        events, ylt = simulate(cfg, ROOT / cfg["data"]["raw_dir"], cfg["run"]["seed"])
        gross = build_ylt(events, cfg["run"]["n_years"], "gross_loss")
        t, tg = ep_table(ylt), ep_table(gross)
        rows[name] = {
            "AAL": aal(ylt),
            **{f"OEP_{rp}": t.loc[rp, "OEP"] for rp in (100, 250, 1000)},
            "AEP_200": t.loc[200, "AEP"],
            "TVaR_AEP_100": t.loc[100, "TVaR_AEP"],
            "gross_AAL": aal(gross),
            **{f"gross_OEP_{rp}": tg.loc[rp, "OEP"] for rp in (100, 250, 1000)},
        }
    path = ROOT / base["run"]["output_dir"] / "sensitivity.csv"
    df = pd.DataFrame(rows).T
    if sys.argv[1:] and path.exists():  # update the named rows, keep the others
        old = pd.read_csv(path, index_col=0)
        df = df.combine_first(old.drop(index=df.index, errors="ignore")).loc[
            [n for n in CASES if n in set(old.index) | set(df.index)]
        ]
    df.to_csv(path)
    print((df / 1e6).round(0).to_string())
    if "baseline" in df.index:
        print("\nRelative to baseline:")
        print((df / df.loc["baseline"]).round(2).to_string())


if __name__ == "__main__":
    main()
