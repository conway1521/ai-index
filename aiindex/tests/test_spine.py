import pandas as pd

from aiindex import config, spine


def test_census_to_soc_expands_wildcards_from_fixture():
    fixture = pd.read_csv(config.FIXTURE_DIR / "census_2018_occupation_crosswalk.csv", dtype=str)
    codes = []
    for entry in fixture["soc_entry"].dropna():
        for token in entry.replace(";", ",").split(","):
            token = token.strip().upper()
            if "X" in token:
                codes += [token.split("X")[0] + "1", token.split("X")[0] + "2"]
            elif len(token) == 7:
                codes.append(token)
    universe = pd.Series(sorted(set(codes)))
    pairs = spine.census_to_soc(config.FIXTURE_DIR / "census_2018_occupation_crosswalk.csv", soc_universe=universe)
    assert set(pairs.loc[pairs["census_code"] == "0010", "soc_code"]) == {"11-1011"}
    wildcard = fixture.loc[fixture["soc_entry"].str.contains("X", na=False), "census_code"].iloc[0]
    assert (pairs["census_code"] == wildcard).sum() >= 2          # an XX entry expands to its members
    assert pairs.duplicated(["census_code", "soc_code"]).sum() == 0


def test_cip_to_soc_fixture_has_six_digit_cips():
    pairs = spine.cip_to_soc(config.FIXTURE_DIR / "cip_2020_soc_2018.csv")
    assert pairs["cip_code"].str.fullmatch(r"\d{2}\.\d{4}").all()
    assert pairs["soc_code"].str.fullmatch(r"\d{2}-\d{4}").all()
    assert spine.cip_two_digit(pairs["cip_code"]).str.len().eq(2).all()
