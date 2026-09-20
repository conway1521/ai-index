"""What has moved: the annual outcome series with its detection threshold.

The paper runs one test: are the last three year-to-year changes in each
skill bundle's relative pay unusual against that bundle's own history,
with the reference distribution built by relabelling which three of the
thirteen transitions count as treated. The index runs the same test as a
series, once per release year, so that a reader sees the statistic move,
or fail to move, as each OEWS release arrives.

Two numbers are reported for every year. The observed statistic is the
largest standardised shift over the 25 bundles, using the three transitions
ending in that year. The threshold is the 95th percentile of the same
statistic under every consecutive relabelling of the transitions available
at that date, which is the value the observed statistic would have to
exceed to be called a detectable change at that release. The distance to
detection is their ratio. The same is run on employment-weighted skill
intensity, so quantities and prices carry separate readings.

Both the regression and the statistic are the paper's, imported from
``src.regime_test`` and ``src.permutation_test``, so a number here is the
number in the paper when the panel is the paper's.
"""

from __future__ import annotations

import sys
from itertools import combinations

import numpy as np
import pandas as pd

from . import checks, config

sys.path.insert(0, str(config.REPO_ROOT))
from src import permutation_test, regime_test  # noqa: E402

LAYER = "outcomes"
N_TREATED = 3
MIN_TRANSITIONS = 6      # fewer than six transitions cannot support a reference set
QUANTILE = 0.95


def pay_changes(panel: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Relative pay change per bundle for every year transition in the panel."""
    return permutation_test.annual_changes(panel, columns)


def intensity_changes(panel: pd.DataFrame, columns: list[str],
                      weight: str = "employment") -> pd.DataFrame:
    """Change in the weighted average skill intensity of employment, by year."""
    rows = {}
    for year, block in panel.groupby("vintage"):
        w = block[weight].to_numpy(float)
        rows[int(year)] = (w @ block[columns].to_numpy(float)) / w.sum()
    levels = pd.DataFrame(rows, index=columns).T.sort_index()
    return levels.diff().dropna()


def _null(changes: pd.DataFrame, n_treated: int) -> pd.DataFrame:
    draws = []
    for pick in combinations(list(changes.index), n_treated):
        consecutive = all(b - a == 1 for a, b in zip(pick[:-1], pick[1:]))
        count, largest = permutation_test._statistic(changes, list(pick))
        draws.append({"count": count, "largest": largest, "consecutive": consecutive})
    return pd.DataFrame(draws)


def series(changes: pd.DataFrame, label: str, n_treated: int = N_TREATED) -> pd.DataFrame:
    """The statistic, its threshold and the distance to detection, per year."""
    years = list(changes.index)
    rows = []
    for end in years:
        available = changes.loc[:end]
        if len(available) < MIN_TRANSITIONS:
            continue
        treated = list(available.index[-n_treated:])
        count, largest = permutation_test._statistic(available, treated)
        null = _null(available, n_treated)
        strict = null[null["consecutive"]]
        threshold = float(strict["largest"].quantile(QUANTILE))
        rows.append({
            "series": label,
            "year": int(end),
            "treated_transitions": ",".join(str(t) for t in treated),
            "transitions_available": len(available),
            "bundles_beyond_two": count,
            "largest_statistic": round(largest, 3),
            "threshold_95": round(threshold, 3),
            "distance_to_detection": round(largest / threshold, 3) if threshold else np.nan,
            "p_largest_consecutive": round(float((strict["largest"] >= largest).mean()), 3),
            "p_count_consecutive": round(float((strict["count"] >= count).mean()), 3),
            "consecutive_relabellings": int(len(strict)),
        })
    out = pd.DataFrame(rows)
    if len(out):
        checks.nonnegative(out["largest_statistic"], LAYER, f"{label} statistic")
        checks.nonnegative(out["threshold_95"], LAYER, f"{label} threshold")
        checks.within(out["p_largest_consecutive"], 0.0, 1.0, LAYER, f"{label} p-value")
    return out


def balanced(panel: pd.DataFrame) -> pd.DataFrame:
    """Occupations present in every year, the paper's panel construction."""
    counts = panel.groupby("soc_code")["vintage"].nunique()
    keep = counts[counts == panel["vintage"].nunique()].index
    checks.note(LAYER, "balanced panel", f"{len(keep)} occupations present in all {panel['vintage'].nunique()} years", len(keep))
    return panel[panel["soc_code"].isin(keep)]


def build(panel: pd.DataFrame, columns: list[str]) -> dict[str, pd.DataFrame]:
    """Both series, prices and quantities, from one national panel."""
    pay = pay_changes(panel, columns)
    quantity = intensity_changes(panel, columns)
    return {
        "pay": series(pay, "relative pay by skill bundle"),
        "quantity": series(quantity, "employment-weighted skill intensity"),
        "pay_changes": pay,
        "quantity_changes": quantity,
    }
