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
- ESHM20 main datasets (efehr/eshm20): Danciu et al. (2021),
  doi:10.12686/eshm20-main-datasets (catalogue and completeness, for validation only).
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

# efehr/eshm20 has no release tags, so it is pinned to a commit (equally immutable).
ESHM20_COMMIT = "fbd334de68f85d72669f73fc5a314a113db67317"

# (repo, tag or commit, path in repo, sha256) -- sha256 values as reported by GitLab.
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
    # ESHM20 area-source model as packaged for ESRM20 (branch "asm_collapsed", weight 0.5,
    # of source_model_logic_tree_eshm20_v12e_collapsed_risk_model.xml). ESHM20: Danciu et
    # al. (2021), doi:10.12686/a15.
    (
        "efehr/esrm20",
        "v1.0",
        "Hazard/source_models/asm_v12e/asm_ver12e_winGT_fs017_combined.xml",
        "32dfcefff8acbedabf4fa6d87ce8694ff2dd7b662f5d75c5ea06a2156a6b2aef",
    ),
    # Ground-motion logic tree: Kotha et al. (2020) ESHM20 backbone, slope/geology site term,
    # 5 stress x 3 attenuation branches. doi:10.1007/s10518-020-00869-1.
    (
        "efehr/esrm20",
        "v1.0",
        "Hazard/gmpe_logic_tree_5br_slope_geology.xml",
        "f3efd16d56189c7804824d94b20ed75d6ceefc879144d8bd697c1f9b47cf17b4",
    ),
    # Site model: slope, geology, attenuation region and inferred Vs30 per site.
    (
        "efehr/esrm20",
        "v1.0",
        "Vs30/Site_model_Switzerland.xml",
        "ebcbe810ca51778a45590b3182c98d0b4cfc35a08fe628af8b3b2fe3b85263ee",
    ),
    # ESHM20 unified earthquake catalogue, declustered (the mainshock catalogue the source
    # rates were fitted to), and the completeness super-zones with their Mc(t) table.
    # Danciu et al. (2021), Main Datasets of ESHM20, doi:10.12686/eshm20-main-datasets.
    # Used only for the historical-rate check, not by the loss model.
    *(
        (
            "efehr/eshm20",
            ESHM20_COMMIT,
            f"input_shapefiles/eshm20_input_a_unified_eq_catalogue/"
            f"eshm20_unified_catalogue_declustered_v02a.{ext}",
            sha,
        )
        for ext, sha in [
            ("dbf", "45ee685d9d7906d4e2df4f5a7132ae7941db1597ee715a86c1d4e0c67676d831"),
            ("shp", "6e560b3a3ac6ad0e41a904e0acfcc8b4743e27d513bf278a3b3c69e57e53e033"),
            ("shx", "1d2ac7784e7be8b27c7e54b589cec257b56bad31f9275dba6ab73ee991d9b60e"),
            ("prj", "a02a27b1d1982c8516d83398e85a3c8b1aef1713c13ef4d84d7bde17430c07c4"),
            ("cpg", "3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824"),
        ]
    ),
    *(
        (
            "efehr/eshm20",
            ESHM20_COMMIT,
            f"input_shapefiles/eshm20_input_b_completeness_superzones/{name}",
            sha,
        )
        for name, sha in [
            (
                "McTable_CSZ_ESHM20_ver_dec2020.xlsx",
                "bf06e93dec25d906e758dbee99fc3d1270b67bd7b77a9cec0789b359cbcab55d",
            ),
            (
                "eshm20_csz_v06b.shp",
                "f923bf17411d5e00c2a302aa60c3b9ef1795ab57334c3cab3113779ab81e61e2",
            ),
            (
                "eshm20_csz_v06b.shx",
                "c4329348cbe48d10a64103c9ca4944ecda852cb2b62a20b60cb893d8439dfe50",
            ),
            (
                "eshm20_csz_v06b.dbf",
                "e28d3cc8bd15f75c7f67ce86dac7cec282100d25af7c2c19070a909ca74cc195",
            ),
            (
                "eshm20_csz_v06b.prj",
                "98aaf3d1c0ecadf1a424a4536de261c3daf4e373697cb86c40c43b989daf52eb",
            ),
            (
                "eshm20_csz_v06b.cpg",
                "3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824",
            ),
        ]
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
