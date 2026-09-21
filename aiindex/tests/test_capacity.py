import numpy as np
import pandas as pd
import pytest

from aiindex import capacity, config


def _matrix():
    return capacity.validate_matrix(pd.read_csv(config.FIXTURE_DIR / "transition_matrix_fixture.csv",
                                                dtype={"origin": str, "destination": str}))


def test_schema_is_enforced():
    with pytest.raises(ValueError):
        capacity.validate_matrix(pd.DataFrame({"year": [2024], "origin": ["a"]}))


def test_exit_share_is_a_share_and_absorption_respects_caps():
    matrix = _matrix()
    occ = sorted(set(matrix["origin"]))
    exposure = pd.Series(np.linspace(0, 1, len(occ)), index=occ)
    stocks = pd.Series(1e6, index=occ)
    exit_share = capacity.exit_share(matrix, exposure, 0.5)
    assert exit_share["exit_share_low_exposure"].between(0, 1).all()
    absorbed = capacity.absorption(matrix, stocks, exposure, 0.5, 2025)
    history = matrix[matrix["age_band"] == "all"].groupby("origin")["flow"].max()
    assert (absorbed.set_index("origin")["absorbed"] <= history.reindex(absorbed["origin"]).values * len(occ)).all()


def test_education_channel_ratio():
    arrivals = capacity.validate_arrivals(pd.read_csv(config.FIXTURE_DIR / "arrivals_fixture.csv", dtype={"occupation": str}))
    out = capacity.education_channel(arrivals)
    assert (out["lateral_over_education"] > 1).all()
