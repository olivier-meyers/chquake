"""Download the public input data into data/raw/, pinned to release tags and SHA-256.

Usage: python scripts/download_data.py

Files come from the EFEHR GitLab (gitlab.seismo.ethz.ch) through its API v4, because
the plain raw-file URLs sit behind a browser bot-check. Every file is pinned to a release
tag and its SHA-256; if upstream ever changes, the check fails instead of silently
changing the model.

Sources (all CC BY 4.0):
- ESRM20 exposure v1.0 (efehr/esrm20_exposure): Crowley et al. (2020), Earthquake Spectra,
  doi:10.1177/8755293020919429; data doi:10.5281/zenodo.4062044.
- ESRM20 OpenQuake input files v1.0 (efehr/esrm20): Crowley et al. (2021), EFEHR Technical
  Report 002, doi:10.7414/EUC-EFEHR-TR002-ESRM20. Vulnerability data also published as
  doi:10.5281/zenodo.4062410.
"""

import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = (
    "https://gitlab.seismo.ethz.ch/api/v4/projects/{project}/repository/files/{path}/raw?ref={ref}"
)
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# (repo, tag, path in repo, sha256) -- sha256 values as reported by GitLab for these tags.
FILES: list[tuple[str, str, str, str]] = [
    # Exposure: one row per building class per municipality, costs in EUR (2020).
    (
        "efehr/esrm20_exposure",
        "v1.0",
        "_exposure_models/Exposure_Model_Switzerland_Res.csv",
        "4e9c33f7d421135d84465a4cde4958e35bd516d3c8cbb9e865d3750f55963713",
    ),
    # Provenance only (not read by code): reconstruction costs per m2 and cost shares.
    (
        "efehr/esrm20_exposure",
        "v1.0",
        "sources/European_Exposure_Model_Data_Inputs_Sources.xlsx",
        "052218c6c253d5fa9db7f4e5005678aef6f85e329c3b64e89d67abd2074f4c50",
    ),
    # Vulnerability functions (intensity measure, mean loss ratio, CoV per function).
    (
        "efehr/esrm20",
        "v1.0",
        "Vulnerability/vulnerability_total-repl-cost_ESRM20_VariousIM.xml",
        "22f699ef9b649f388f850551066847ff02f36c72606dc9c615f05d454f1f918e",
    ),
    # Official exposure-taxonomy -> vulnerability-function mapping.
    (
        "efehr/esrm20",
        "v1.0",
        "Vulnerability/esrm20_exposure_vulnerability_mapping.csv",
        "94b9ee800e9435a346ca200ecf34d0d46c8d8b895cc56e3be85c323006b4ee4c",
    ),
]


def sha256(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(repo: str, tag: str, path: str, expected: str) -> Path:
    """Download one file (unless already present and valid) and verify its hash."""
    target = RAW_DIR / Path(path).name
    if target.exists() and sha256(target) == expected:
        print(f"ok (cached)  {target.name}")
        return target
    url = API.format(
        project=urllib.parse.quote(repo, safe=""),
        path=urllib.parse.quote(path, safe=""),
        ref=tag,
    )
    tmp = target.with_suffix(target.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    got = sha256(tmp)
    if got != expected:
        tmp.unlink()
        sys.exit(f"SHA-256 mismatch for {path}: expected {expected}, got {got}")
    tmp.replace(target)
    print(f"ok (fetched) {target.name}")
    return target


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for repo, tag, path, expected in FILES:
        fetch(repo, tag, path, expected)


if __name__ == "__main__":
    main()
