"""Completions by field and state from the IPEDS completions component.

The completions file has one row per institution, six-digit CIP, major
number and award level, with counts by sex and race and a total. Only
first majors and the total column enter, six-digit CIP rows only, so that
the two-digit and four-digit subtotal rows some exports include are not
counted again. The institution's state comes from the header file of the
nearest year in hand. Award levels are kept as IPEDS codes and named.
"""

from __future__ import annotations

import pandas as pd

from . import checks, config, fetch, sources

LAYER = "ipeds"

AWARD_LEVELS = {
    1: "certificate under 1 year", 2: "certificate 1 to 2 years", 3: "associate",
    4: "certificate 2 to 4 years", 5: "bachelor", 6: "postbaccalaureate certificate",
    7: "master", 8: "post-master certificate", 17: "doctor research", 18: "doctor professional",
    19: "doctor other", 20: "certificate under 12 weeks", 21: "certificate 12 weeks to 1 year",
}


def completions(year: int) -> pd.DataFrame:
    name = f"C{year}_A.csv"
    official, mirrors = sources.IPEDS[name]
    path, _ = fetch.get(f"ipeds_{name}", f"ipeds/{name}", official, mirrors=mirrors)
    raw = pd.read_csv(path, dtype=str, encoding="latin-1")
    raw.columns = [c.strip().upper() for c in raw.columns]
    frame = pd.DataFrame({
        "unitid": raw["UNITID"].str.strip(),
        "cip_code": raw["CIPCODE"].str.strip(),
        "major_number": pd.to_numeric(raw["MAJORNUM"], errors="coerce"),
        "award_level": pd.to_numeric(raw["AWLEVEL"], errors="coerce"),
        "awards": pd.to_numeric(raw["CTOTALT"], errors="coerce"),
    })
    six_digit = frame["cip_code"].str.fullmatch(r"\d{2}\.\d{4}")
    frame = frame[six_digit & frame["major_number"].eq(1)].copy()
    frame["year"] = year
    frame["award_level_name"] = frame["award_level"].map(AWARD_LEVELS)
    checks.nonnegative(frame["awards"].dropna(), LAYER, f"awards {year}")
    checks.unique_key(frame, ["unitid", "cip_code", "award_level"], LAYER)
    total = float(frame["awards"].sum())
    checks.note(LAYER, f"first-major awards {year}", f"{total:,.0f} awards over {frame['unitid'].nunique()} institutions", total)
    return frame[["year", "unitid", "cip_code", "award_level", "award_level_name", "awards"]]


def institutions(year: int = 2023) -> pd.DataFrame:
    name = f"HD{year}.csv"
    official, mirrors = sources.IPEDS[name]
    path, _ = fetch.get(f"ipeds_{name}", f"ipeds/{name}", official, mirrors=mirrors)
    raw = pd.read_csv(path, dtype=str, encoding="latin-1")
    raw.columns = [c.strip().upper() for c in raw.columns]
    out = pd.DataFrame({"unitid": raw["UNITID"].str.strip(), "state": raw["STABBR"].str.strip(),
                        "state_fips": raw["FIPS"].str.strip().str.zfill(2) if "FIPS" in raw else None,
                        "name": raw["INSTNM"]})
    checks.unique_key(out, ["unitid"], LAYER)
    return out
