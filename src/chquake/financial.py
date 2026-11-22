"""Financial terms: per-building policy deductible (ground-up -> gross) and a cat XL layer.

Policy terms follow the Statuten des Schweizerischen Pools für Erdbebendeckung (SPE),
14 Dec 1993, in force 1 Jan 1994; published as BGS 618.115, https://www.lexfind.ch/tol/16207/de
- Art. 5: the unit is one building.
- Art. 6(2): buildings only; no clean-up costs, no contents -> covered value is structure +
  non-structural, contents excluded.
- Art. 14(2): payout capped at the insured value (sum insured).
- Art. 15(1): deductible 10 % of the sum insured at replacement value, at least CHF 50,000,
  per building.
Applied here to all Swiss residential buildings as a stylised portfolio, not the pool's real
footprint (see README). The pool's intensity trigger (Art. 6(1)) and event cap (Art. 16) are
not modelled.

Per-building terms on lumped asset rows: an ESRM20 row holds n buildings of total value V.
Assuming they share the row's value and loss ratio equally, each building has value V/n and
deductible D_b = max(f * V/n, D_min), so the row's gross loss is
    n * max(lr * V/n - D_b, 0) = V * max(lr - d, 0),   d = max(f, D_min * n / V).
The deductible becomes a per-row ratio d, and the limit (sum insured) needs no extra cap
because lr <= 1.

Cat XL "X xs Y" per occurrence, with n reinstatements at rate r (pro rata capita):
    recovery per event   R_e = min(max(G_e - Y, 0), X)
    annual recovery          = min(sum_e R_e, (n + 1) X)
    reinstatement premium    = r * P * min(sum_e R_e, n X) / X
Neither depends on the order of events within a year, which the event set does not have.
Pure premium P (no loading): E[recovery] = P + E[reinstatement premium], so
    P = E[recovery] / (1 + r * E[min(sum_e R_e, n X)] / X).
"""

import numpy as np
import pandas as pd


def deductible_ratio(
    value: np.ndarray, buildings: np.ndarray, fraction: float, minimum: float
) -> np.ndarray:
    """Per-row deductible as a fraction of covered value: max(fraction, minimum * n / V)."""
    if np.any(value <= 0) or np.any(buildings <= 0):
        raise ValueError("values and building counts must be positive")
    return np.maximum(fraction, minimum * buildings / value)


def layer_recoveries(event_loss: np.ndarray, limit: float, attachment: float) -> np.ndarray:
    """Per-occurrence recovery of an X xs Y layer: min(max(G - Y, 0), X)."""
    return np.clip(np.asarray(event_loss, float) - attachment, 0.0, limit)


def cat_xl(
    event_loss: np.ndarray,
    year: np.ndarray,
    n_years: int,
    limit: float,
    attachment: float,
    reinstatements: int,
    reinstatement_rate: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Apply an X xs Y cat XL with reinstatements; return per-year table and summary.

    Year table: recovery (after the annual aggregate limit) and reinstated (fraction of the
    limit reinstated, which drives the reinstatement premium). Summary: expected recovery,
    pure premium, rate on line, attachment and exhaustion probabilities, std of recovery.
    """
    limit, attachment = float(limit), float(attachment)
    r_e = layer_recoveries(event_loss, limit, attachment)
    total = np.bincount(np.asarray(year), weights=r_e, minlength=n_years)
    if len(total) > n_years:
        raise ValueError("event years outside 0..n_years-1")
    recovery = np.minimum(total, (reinstatements + 1) * limit)
    reinstated = np.minimum(total, reinstatements * limit) / limit
    ylt = pd.DataFrame(
        {"recovery": recovery, "reinstated": reinstated},
        index=pd.RangeIndex(n_years, name="year"),
    )
    expected = recovery.mean()
    premium = expected / (1.0 + reinstatement_rate * reinstated.mean())
    summary = {
        "expected_recovery": float(expected),
        "pure_premium": float(premium),
        "rate_on_line": float(premium / limit),
        "p_attach": float((total > 0).mean()),
        "p_exhaust": float((recovery >= (reinstatements + 1) * limit).mean()),
        "std_recovery": float(recovery.std()),
    }
    return ylt, summary
