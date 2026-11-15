"""Single entry point: python run.py --config config.yaml"""

import argparse
from pathlib import Path

import yaml


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
    # Pipeline stages are added per milestone: exposure -> hazard -> loss -> financial -> metrics.


if __name__ == "__main__":
    main()
