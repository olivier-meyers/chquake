"""Single entry point: python run.py --config config.yaml

Pipeline: exposure + vulnerability -> sites -> event set -> correlated ground motion ->
ground-up and gross event losses -> ELT / YLT -> EP metrics -> cat XL (if configured).
Writes to outputs/: elt.csv (ground-up `loss` and `gross_loss` per event), ylt.csv,
ylt_gross.csv, ep_table_ground-up.csv, ep_table_gross.csv and, with a layer,
ylt_cat_xl.csv and cat_xl_summary.csv.
"""

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from chquake.exposure import load_exposure
from chquake.financial import cat_xl, deductible_ratio
from chquake.hazard import (
    correlation_factors,
    ground_motion,
    load_area_sources,
    load_gmpe_branches,
    sample_events,
    select_sources,
)
from chquake.losses import asset_imt_index, build_elt, build_ylt, event_losses
from chquake.metrics import aal, bootstrap_ci, ep_table, expected_shortfall_99
from chquake.site import exposure_sites, load_site_model
from chquake.vulnerability import assign_functions, load_vulnerability


def load_config(path: Path) -> dict:
    """Read the YAML run configuration."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def simulate(cfg: dict, raw: Path, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run hazard and loss; return the event table (with losses) and the YLT."""
    n_years, hz = cfg["run"]["n_years"], cfg["hazard"]
    # Separate random streams per component (common random numbers across sensitivity runs).
    branch_rng, secondary_rng = (
        np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(2)
    )
    exposure = load_exposure(raw / cfg["data"]["exposure"])
    vuln = load_vulnerability(raw / cfg["data"]["vulnerability"])
    func = assign_functions(exposure["taxonomy"], raw / cfg["data"]["vulnerability_mapping"], vuln)
    sites, site_of_asset = exposure_sites(
        exposure, load_site_model(raw / cfg["data"]["site_model"])
    )
    imt_of_asset = asset_imt_index(vuln, func, hz["imts"])
    scale = cfg["exposure"]["value_scale"]
    fin = cfg["financial"]
    # Row 0: ground-up on the total replacement value. Row 1: gross, on the covered (building)
    # value after the per-building deductible (see chquake.financial).
    covered = scale * exposure[fin["covered"]].sum(axis=1).to_numpy()
    ded = deductible_ratio(
        covered,
        exposure["buildings"].to_numpy(),
        fin["deductible_fraction"],
        fin["deductible_min_chf"] / fin["eur_chf"],
    )
    value = np.vstack([scale * exposure["value"].to_numpy(), covered])
    deductible = np.vstack([np.zeros_like(ded), ded])
    print(
        f"Exposure: {len(exposure):,} assets at {len(sites):,} sites, "
        f"EUR {value[0].sum() / 1e9:,.1f} bn (covered {covered.sum() / 1e9:,.1f} bn, "
        f"mean deductible {np.average(ded, weights=covered):.1%} of covered value)"
    )

    sources = select_sources(
        load_area_sources(raw / cfg["data"]["area_sources"], hz["tectonic_region"]),
        sites,
        hz["max_distance_km"],
    )
    events = sample_events(sources, n_years, seed)
    print(
        f"Event set: {len(sources.ids)} area sources, {len(events):,} events in {n_years:,} years"
    )

    branch_ids, gsims, weights = load_gmpe_branches(
        raw / cfg["data"]["gmpe_logic_tree"], hz["tectonic_region"]
    )
    if hz["gmpe_branch"] == "sample_per_year":
        year_branch = branch_rng.choice(len(gsims), size=n_years, p=weights)
    elif hz["gmpe_branch"] == "central":
        year_branch = np.full(n_years, int(np.argmax(weights)))
    else:
        raise ValueError(f"unknown gmpe_branch {hz['gmpe_branch']!r}")
    events["gmpe_branch"] = year_branch[events["year"].to_numpy()]

    spatial, cross = correlation_factors(sites, hz["imts"], hz["correlation"]["vs30_clustering"])
    secondary = secondary_rng if cfg["vulnerability"]["secondary_uncertainty"] else None
    loss = np.zeros((2, len(events)))
    chunk = hz["chunk_events"]
    t0 = time.perf_counter()
    for b in np.unique(events["gmpe_branch"]):
        idx = np.flatnonzero(events["gmpe_branch"].to_numpy() == b)
        for start in range(0, len(idx), chunk):
            sel = idx[start : start + chunk]
            gmf = ground_motion(
                events.iloc[sel],
                sites,
                gsims[b],
                hz["imts"],
                spatial,
                cross,
                seed,
                hz["max_distance_km"],
                hz["correlation"]["within_cross_im"],
                hz["truncation_level"],
            )
            loss[:, sel] = event_losses(
                gmf, imt_of_asset, site_of_asset, func, value, vuln, secondary,
                deductible=deductible,
            )
    print(f"Ground motion + losses: {time.perf_counter() - t0:.0f} s")
    events["branch_id"] = np.array(branch_ids)[events["gmpe_branch"]]
    events["loss"], events["gross_loss"] = loss
    return events, build_ylt(build_elt(events["event_id"], events["year"], loss[0]), n_years)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the chquake loss model.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--years", type=int, help="override run.n_years (quick trials)")
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.years:
        cfg["run"]["n_years"] = args.years
    print(f"Config: seed={cfg['run']['seed']}, n_years={cfg['run']['n_years']:,}")

    raw = args.config.parent / cfg["data"]["raw_dir"]
    out = args.config.parent / cfg["run"]["output_dir"]
    out.mkdir(parents=True, exist_ok=True)

    events, ylt = simulate(cfg, raw, cfg["run"]["seed"])
    n_years = cfg["run"]["n_years"]
    gross = build_ylt(events, n_years, "gross_loss")
    events.to_csv(out / "elt.csv", index=False)
    ylt.to_csv(out / "ylt.csv")
    gross.to_csv(out / "ylt_gross.csv")

    for name, y in (("Ground-up", ylt), ("Gross", gross)):
        table = ep_table(y)
        table.to_csv(out / f"ep_table_{name.lower()}.csv")
        ci = bootstrap_ci(y["agg_loss"].to_numpy(), 200, np.random.default_rng(0))
        print(
            f"\n{name} AAL: EUR {aal(y) / 1e6:,.1f} m "
            f"(90% MC interval {ci['aal'][0] / 1e6:,.1f}-{ci['aal'][1] / 1e6:,.1f})"
        )
        print(f"{name} ES 99%: EUR {expected_shortfall_99(y) / 1e9:,.2f} bn")
        print(f"{name} return-period losses (EUR bn):")
        print((table / 1e9).round(2).to_string())

    xl = cfg["financial"]["cat_xl"]
    if xl:
        xl_ylt, summary = cat_xl(
            events["gross_loss"].to_numpy(), events["year"].to_numpy(), n_years,
            xl["limit"], xl["attachment"], xl["reinstatements"], xl["reinstatement_rate"],
        )
        net = gross["agg_loss"] - xl_ylt["recovery"]
        xl_ylt.assign(gross=gross["agg_loss"], net=net).to_csv(out / "ylt_cat_xl.csv")
        pd.Series(summary).to_csv(out / "cat_xl_summary.csv", header=["value"])
        print(
            f"\nCat XL EUR {xl['limit'] / 1e6:,.0f} m xs {xl['attachment'] / 1e6:,.0f} m, "
            f"{xl['reinstatements']} reinst. at {xl['reinstatement_rate']:.0%}:"
        )
        shares = {"rate_on_line", "p_attach", "p_exhaust"}
        for k, v in summary.items():
            print(f"  {k}: {v:.3%}" if k in shares else f"  {k}: EUR {v / 1e6:,.2f} m")


if __name__ == "__main__":
    main()
