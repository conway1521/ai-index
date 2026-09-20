import pandas as pd
import pytest

from aiindex import checks


def test_shares_sum_to_one_passes_and_records():
    frame = pd.DataFrame({"g": ["a", "a", "b"], "s": [0.4, 0.6, 1.0]})
    row = checks.shares_sum_to_one(frame, ["g"], "s", "t")
    assert row["ok"] and checks.ROWS[-1]["check"].startswith("s sums to one")


def test_shares_sum_to_one_fails_loudly():
    frame = pd.DataFrame({"g": ["a", "a"], "s": [0.4, 0.5]})
    with pytest.raises(checks.CheckFailed):
        checks.shares_sum_to_one(frame, ["g"], "s", "t")
    assert checks.ROWS[-1]["ok"] is False


def test_bounded_by_and_coverage():
    part, whole = pd.Series([1.0, 2.0]), pd.Series([1.0, 3.0])
    assert checks.bounded_by(part, whole, "t", "x")["ok"]
    with pytest.raises(checks.CheckFailed):
        checks.bounded_by(pd.Series([2.0]), pd.Series([1.0]), "t", "x")
    assert checks.coverage(9, 10, "t", "y", 0.85)["ok"]
    with pytest.raises(checks.CheckFailed):
        checks.coverage(8, 10, "t", "y", 0.85)
