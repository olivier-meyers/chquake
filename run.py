"""Single entry point: python run.py --config config.yaml"""

import argparse
from pathlib import Path

import numpy as np
import yaml

from chquake.exposure import load_exposure
from chquake.vulnerability import assign_functions, load_vulnerability


def load_config(path: Path) -> dict:
    """Read the YAML run configuration."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the chquake loss model.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    print(f"Loaded config: seed={cfg['run']['seed']}, n_years={cfg['run']['n_years']}")

    raw = args.config.parent / cfg["data"]["raw_dir"]
    exposure = load_exposure(raw / cfg["data"]["exposure"])
    vuln = load_vulnerability(raw / cfg["data"]["vulnerability"])
    func = assign_functions(exposure["taxonomy"], raw / cfg["data"]["vulnerability_mapping"], vuln)

    print(
        f"Exposure: {len(exposure):,} assets, {exposure['buildings'].sum():,.0f} buildings, "
        f"{exposure['municipality_id'].nunique():,} municipalities, "
        f"total replacement value EUR {exposure['value'].sum() / 1e9:,.1f} bn"
    )
    print(f"Vulnerability: {len(vuln.ids)} functions, {np.unique(func).size} used by Swiss assets")
    share = exposure.groupby(vuln.imt[func])["value"].sum() / exposure["value"].sum()
    print(
        "Share of value by intensity measure: "
        + ", ".join(f"{k} {v:.0%}" for k, v in share.items())
    )
    # Next stages, added per milestone: hazard -> loss -> financial -> metrics.


if __name__ == "__main__":
    main()
