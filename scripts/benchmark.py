"""M5 benchmark: compare the baseline run with published Swiss earthquake loss estimates.

Usage: python scripts/benchmark.py [--config config.yaml]   (after python run.py)

No model parameter is changed here: the script only re-expresses outputs/ylt.csv in the
units of each benchmark and writes outputs/benchmark.csv.

Like-for-like conversions (choices made in M5, see README "Benchmark"):
- Loss ratio (AAL / exposed value, in per mille) is the primary comparison. It is free of
  the value level and the currency. Our vulnerability functions apply one loss ratio to the
  total value, so the ratio is the same with or without contents.
- Absolute numbers: our loss x covered share (structure + non-structural, no contents)
  x EUR/CHF, once at ESRM20 values and once rescaled to the ERM-CH23 residential value.
- ERM-CH23 and BAFU numbers cover all occupancies. The "residential equivalent" multiplies
  them by the residential share of ERM-CH23 value (70 %). This assumes residential loss
  ratios equal the national average; it is an assumption, not a published number.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from chquake.exposure import load_exposure
from chquake.metrics import RETURN_PERIODS, bootstrap_ci, return_period_loss

# Papadopoulos et al. (2024), The Earthquake Risk Model of Switzerland, ERM-CH23,
# NHESS 24, 3561-3578, doi:10.5194/nhess-24-3561-2024.
# Sec. 4 and Table 4: structural-nonstructural AAL CHF 245 m = 0.084 per mille of value;
# "around CHF 10 billion" exceeded every 200 years, "around CHF 37 billion" at 1000 years.
# Sec. 3.3: total structure value CHF 2.9 trillion, "about 70 %" of it residential.
ERM_CH23 = {"aal": 245e6, 200: 10e9, 1000: 37e9}
ERM_CH23_AALR = 0.084e-3
ERM_CH23_VALUE_CHF = 2.9e12
RESIDENTIAL_SHARE = 0.70
# Same paper, Table 4: ESRM20 for Switzerland (all occupancies), AAL EUR 55 m,
# loss ratio 0.043 per mille.
ESRM20_AALR = 0.043e-3
# BAFU, Erdbebenvorsorge (published 15 Jan 2026), https://www.bafu.admin.ch/de/erdbebenvorsorge:
# "rund 22 Milliarden Franken" from the proposed 0.7 % levy, which "entspricht der
# Schadensumme, die bei einem alle 500 Jahre auftretenden Erdbeben zu erwarten ist".
# Loss basis (buildings only or with contents, model used) is not stated on the page.
BAFU = {500: 22e9}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args()
    root = args.config.parent
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    eur_chf = cfg["financial"]["eur_chf"]
    if cfg["exposure"]["value_scale"] != 1.0:
        raise ValueError("benchmark expects the baseline run (exposure.value_scale = 1.0)")

    exposure = load_exposure(root / cfg["data"]["raw_dir"] / cfg["data"]["exposure"])
    total = exposure["value"].sum()
    covered = exposure[cfg["financial"]["covered"]].sum(axis=1).sum()
    share = covered / total  # structure + non-structural share of our total value
    value_factor = RESIDENTIAL_SHARE * ERM_CH23_VALUE_CHF / (covered * eur_chf)
    annual = pd.read_csv(root / cfg["run"]["output_dir"] / "ylt.csv")["agg_loss"].to_numpy()
    rng = np.random.default_rng(0)

    rows = {}
    for key, bench in [("aal", ERM_CH23["aal"]), (200, ERM_CH23[200]), (500, BAFU[500]),
                       (1000, ERM_CH23[1000])]:
        rp = 200 if key == "aal" else key
        if rp not in RETURN_PERIODS:
            raise ValueError(f"return period {rp} not in metrics.RETURN_PERIODS")
        ci = bootstrap_ci(annual, rp, rng, n_boot=200)
        ours, lo_hi = (
            (annual.mean(), ci["aal"]) if key == "aal"
            else (return_period_loss(np.sort(annual)[::-1], rp), ci[f"loss_{rp}"])
        )
        chf = ours * share * eur_chf
        res_eq = RESIDENTIAL_SHARE * bench
        rows["AAL" if key == "aal" else f"{rp}-yr AEP"] = {
            "source": "BAFU 2026" if key == 500 else "ERM-CH23",
            "ours_EUR_total": ours,
            "ours_CHF_esrm20_values": chf,
            "ours_CHF_ermch23_values": chf * value_factor,
            "benchmark_CHF_all": bench,
            "benchmark_CHF_res_equiv": res_eq,
            "ratio_esrm20_values": chf / res_eq,
            "ratio_ermch23_values": chf * value_factor / res_eq,
            "ratio_mc_low": lo_hi[0] * share * eur_chf * value_factor / res_eq,
            "ratio_mc_high": lo_hi[1] * share * eur_chf * value_factor / res_eq,
        }
    table = pd.DataFrame.from_dict(rows, orient="index")
    out = root / cfg["run"]["output_dir"] / "benchmark.csv"
    table.to_csv(out)

    aal_ci = bootstrap_ci(annual, 200, rng, n_boot=200)["aal"]
    aalr = annual.mean() / total
    print(f"Covered share {share:.3f}; ESRM20 residential covered value CHF "
          f"{covered * eur_chf / 1e9:,.0f} bn; ERM-CH23 residential value / ours = {value_factor:.2f}")
    print(f"\nAAL ratio, ours: {aalr * 1e3:.4f} per mille "
          f"(90% MC {aal_ci[0] / total * 1e3:.4f}-{aal_ci[1] / total * 1e3:.4f})")
    print(f"  vs ERM-CH23 {ERM_CH23_AALR * 1e3:.3f}: x{aalr / ERM_CH23_AALR:.2f}")
    print(f"  vs ESRM20   {ESRM20_AALR * 1e3:.3f}: x{aalr / ESRM20_AALR:.2f}")
    print("\nAbsolute (CHF, structure + non-structural, residential equivalent):")
    fmt = table.copy()
    money = [c for c in fmt.columns if c.startswith(("ours", "benchmark"))]
    fmt[money] = fmt[money] / 1e9
    print(fmt.round(3).to_string())
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
