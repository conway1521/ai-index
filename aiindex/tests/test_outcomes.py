import numpy as np
import pandas as pd

from aiindex import outcomes


def _panel(seed=1, n=200, k=6, years=range(2012, 2024)):
    rng = np.random.default_rng(seed)
    cols = [f"b{i}" for i in range(k)]
    content = pd.DataFrame(rng.uniform(1, 5, (n, k)), columns=cols)
    content["soc_code"] = [f"{i:02d}-{i:04d}" for i in range(n)]
    base = rng.lognormal(10.8, 0.4, n)
    emp = rng.lognormal(10, 1.0, n)
    rows = []
    for j, y in enumerate(years):
        rows.append(pd.DataFrame({"vintage": y, "soc_code": content["soc_code"],
                                  "employment": emp, "wage": base * np.exp(0.03 * j + rng.normal(0, 0.02, n))}))
    return pd.concat(rows).merge(content, on="soc_code"), cols


def test_series_has_threshold_and_bounded_pvalues():
    panel, cols = _panel()
    out = outcomes.build(panel, cols)
    pay = out["pay"]
    assert len(pay) == len(out["pay_changes"]) - outcomes.MIN_TRANSITIONS + 1
    assert (pay["threshold_95"] > 0).all()
    assert pay["p_largest_consecutive"].between(0, 1).all()
    assert ((pay["distance_to_detection"] - pay["largest_statistic"] / pay["threshold_95"]).abs() < 2e-3).all()


def test_quantity_changes_are_first_differences_of_weighted_intensity():
    panel, cols = _panel()
    changes = outcomes.intensity_changes(panel, cols)
    first = panel[panel["vintage"] == 2012]
    second = panel[panel["vintage"] == 2013]
    expected = (np.average(second[cols[0]], weights=second["employment"])
                - np.average(first[cols[0]], weights=first["employment"]))
    assert abs(changes.loc[2013, cols[0]] - expected) < 1e-12
