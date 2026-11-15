# chquake: an open earthquake loss model for Switzerland

> Work in progress. This is a portfolio project, not a production model.

A small, reproducible earthquake catastrophe model for Swiss residential buildings:

**hazard → site → exposure → vulnerability → financial terms → EP metrics**

The results are benchmarked against the published Swiss national earthquake risk model (ERM-CH23).
The aim is a transparent "own view of risk", not a calibrated replica.

## Status

| Milestone | Content | Status |
|---|---|---|
| M0 | Scaffold (packaging, lint, tests, licence) | done |
| M1 | Exposure + vulnerability (ESRM20) | done |
| M2 | Stochastic event set + ground motion | planned |
| M3 | Losses → ELT/YLT → AAL, OEP/AEP, convergence | planned |
| M4 | Financial module + cat XL layer | planned |
| M5 | Benchmark against ERM-CH23 | planned |
| M6 | Final README, figures, limitations | planned |

## Quick start

```bash
# OpenBLAS instead of MKL: MKL 2026.1 crashed numpy's linear algebra on the dev machine (Windows)
conda create -n chquake -c conda-forge python=3.11 git pip "libblas=*=*openblas" -y
conda activate chquake
pip install -e ".[dev]"
python scripts/download_data.py
pytest
python run.py --config config.yaml
```

## Data

All inputs are public. They are downloaded by `scripts/download_data.py` into `data/`, which is
not committed. Every external dataset and parameter is cited (with DOI) in the code and listed here.

| Input | Source | Version | Licence | Citation |
|---|---|---|---|---|
| Residential exposure (`Exposure_Model_Switzerland_Res.csv`) | [efehr/esrm20_exposure](https://gitlab.seismo.ethz.ch/efehr/esrm20_exposure) | v1.0 | CC BY 4.0 | Crowley et al. (2020), doi:[10.1177/8755293020919429](https://doi.org/10.1177/8755293020919429); data doi:[10.5281/zenodo.4062044](https://doi.org/10.5281/zenodo.4062044) |
| Vulnerability functions (`vulnerability_total-repl-cost_ESRM20_VariousIM.xml`) | [efehr/esrm20](https://gitlab.seismo.ethz.ch/efehr/esrm20) | v1.0 | CC BY 4.0 | Crowley et al. (2021), ESRM20, doi:[10.7414/EUC-EFEHR-TR002-ESRM20](https://doi.org/10.7414/EUC-EFEHR-TR002-ESRM20); data doi:[10.5281/zenodo.4062410](https://doi.org/10.5281/zenodo.4062410) |
| Taxonomy → vulnerability mapping (`esrm20_exposure_vulnerability_mapping.csv`) | [efehr/esrm20](https://gitlab.seismo.ethz.ch/efehr/esrm20) | v1.0 | CC BY 4.0 | as above |

Files are pinned to release tags and verified by SHA-256.

### Modelling choices

- **Value basis: total replacement cost** (structure 30 % + non-structural 50 % + contents 20 %),
  EUR 973.5 bn for 1.73 M residential buildings. This matches what ESRM20 applies its
  total-replacement-cost vulnerability functions to, so losses are like-for-like with ESRM20.
- **Currency: EUR at 2020 prices**, as published. Conversion to CHF happens only at the
  ERM-CH23 comparison (M5), with a cited exchange rate and year.

## Limitations

- **One location per municipality.** ESRM20 places all buildings of a municipality at a single
  point (2,224 points). Every building in a municipality feels the same shaking, which understates
  spatial diversification within large municipalities.
- **Residential only.** Commercial and industrial buildings are not modelled.
- **No contents/building split in the loss.** One total-replacement-cost loss ratio is applied to
  structure, non-structural elements and contents together, as in ESRM20.

## Licence

AGPL-3.0. See [LICENSE](LICENSE).
