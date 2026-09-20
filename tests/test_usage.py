import numpy as np
import pandas as pd
import pytest

from aiindex import usage


def test_validate_usage_normalises_and_checks():
    table = pd.DataFrame({"platform": ["p", "p", "p"], "release": ["r", "r", "r"],
                          "task_id": ["1", "1", "2"], "usage_share": [1.0, 1.0, 2.0],
                          "automation_share": [0.5, 0.5, 0.2], "augmentation_share": [0.4, 0.4, 0.7]})
    out = usage.validate_usage(table)
    assert len(out) == 2 and abs(out["usage_share"].sum() - 1) < 1e-12
    bad = table.assign(automation_share=0.9, augmentation_share=0.9)
    with pytest.raises(Exception):
        usage.validate_usage(bad)


def test_readings_bound_reach_by_the_wage_bill():
    values = pd.DataFrame({"soc_code": ["a", "a", "b"], "task_id": ["1", "2", "3"],
                           "share": [0.5, 0.5, 1.0], "value": [50.0, 50.0, 100.0]})
    bundles = pd.DataFrame({"task_id": ["1", "2", "3"], "soc_code": ["a", "a", "b"],
                            "x": [1.0, 0.5, 0.0], "y": [0.0, 0.5, 1.0]})
    used = pd.DataFrame({"platform": ["p"] * 2, "release": ["r"] * 2, "task_id": ["1", "3"],
                         "usage_share": [0.25, 0.75], "automation_share": [1.0, 0.0], "augmentation_share": [0.0, 1.0]})
    out = usage.readings(usage.validate_usage(used), values, bundles, {"x": "X", "y": "Y"})
    reach = out["reach"].iloc[0]
    assert reach["reach_usd"] == 150.0 and reach["delegated_usd"] == 50.0 and reach["augmented_usd"] == 100.0
    landing = out["landing"].set_index("bundle_id")
    assert abs(landing["usage_share_on_bundle"].sum() - 1) < 1e-12
    assert abs(landing.loc["y", "usage_share_on_bundle"] - 0.75) < 1e-12
