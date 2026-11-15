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
| M1 | Exposure + vulnerability (ESRM20) | planned |
| M2 | Stochastic event set + ground motion | planned |
| M3 | Losses → ELT/YLT → AAL, OEP/AEP, convergence | planned |
| M4 | Financial module + cat XL layer | planned |
| M5 | Benchmark against ERM-CH23 | planned |
| M6 | Final README, figures, limitations | planned |

## Quick start

```bash
conda create -n chquake -c conda-forge python=3.11 git pip -y
conda activate chquake
pip install -e ".[dev]"
pytest
python run.py --config config.yaml
```

## Data

All inputs are public. They are downloaded by `scripts/download_data.py` into `data/`, which is
not committed. Every external dataset and parameter is cited (with DOI) in the code and listed here.

*(Sources will be listed here from M1 onwards.)*

## Limitations

*(Every simplification will be listed here as it is introduced.)*

## Licence

AGPL-3.0. See [LICENSE](LICENSE).
