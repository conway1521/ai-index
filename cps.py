"""The young-worker gauge from the CPS basic monthly public-use files.

The quantity is the employment of workers aged 22 to 27 in occupations in
the top third of an exposure measure, relative to their employment in the
rest, indexed to a base period, alongside the same ratio for workers aged
35 to 54. The Stanford and ADP dashboard reports this on payroll data from
one provider; this version runs on the Census Bureau's representative
sample and publishes a detection threshold beside the reading.

Reading the files. The public-use file is fixed width and the Census
Bureau publishes a record layout for each year with the position of every
variable. The layout is parsed rather than hard coded, so a change in
positions between years is picked up from the document and not from
memory. The variables used: HRYEAR4 and HRMONTH for the date, HRMIS for
the month in sample, PRTAGE for age, PEMLR for labour force status,
PEIO1OCD for the four-digit Census occupation of the main job, GESTFIPS
for the state, and PWCMPWGT, the composited final weight, for weighting.

Occupation coding. Census codes are mapped to six-digit SOC through the
Census Bureau's 2018 occupation code list. Where a Census code spans
several SOC codes the exposure of the Census code is the employment-
weighted mean of the SOC exposures, with OEWS employment as the weight,
and the share of employment on codes that could be scored is reported.

Inference. The CPS rotation design returns each household in months one to
four and again in months thirteen to sixteen, so consecutive months share
three quarters of their sample and are not independent draws. The
reference distribution relabels which months count as post-2022 at the
level of rotation groups, not persons, so that the dependence between
adjacent months is preserved under the null.
"""

from __future__ import annotations

import gzip
import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import checks, config

LAYER = "cps"
CPS_DIR = config.RAW_DIR / "cps"
OFFICIAL = "https://www.census.gov/data/datasets/time-series/demo/cps/cps-basic.html"

VARIABLES = ["HRYEAR4", "HRMONTH", "HRMIS", "PRTAGE", "PEMLR", "PEIO1OCD",
             "GESTFIPS", "PWCMPWGT", "PWSSWGT"]
# The 2026 layout renamed the main-job occupation code; both names are read
# as the same variable so that a year boundary does not change the gauge.
ALIASES = {"PTIO1OCD": "PEIO1OCD"}
EMPLOYED_CODES = (1, 2)                  # PEMLR 1 at work, 2 with a job but absent
PRIME_AGE = (35, 54)
WEIGHT_SCALE = 10_000                    # CPS weights carry four implied decimals


def parse_layout(text: str) -> dict[str, tuple[int, int]]:
    """Variable name to (start, end) one-based inclusive positions.

    The Census layout lists each variable as NAME SIZE DESCRIPTION ...
    with a trailing "(start - end)" or "start-end" position on the same
    line or shortly after. Both forms are parsed; the first occurrence of a
    variable wins because the layout repeats names in its code lists.
    """
    positions: dict[str, tuple[int, int]] = {}
    pattern = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s+(\d+)\s+.*?\(?\s*(\d+)\s*-\s*(\d+)\s*\)?\s*$")
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        name, size, start, end = match.group(1), int(match.group(2)), int(match.group(3)), int(match.group(4))
        name = ALIASES.get(name, name)
        if end - start + 1 != size or name in positions:
            continue
        positions[name] = (start, end)
    missing = [v for v in VARIABLES if v not in positions]
    if missing:
        raise ValueError(f"layout lacks positions for {missing}")
    return positions


def _open_records(path: Path) -> bytes:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            member = max(archive.namelist(), key=lambda m: archive.getinfo(m).file_size)
            return archive.read(member)
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rb") as handle:
            return handle.read()
    return path.read_bytes()


def read_month(path: Path, positions: dict[str, tuple[int, int]]) -> pd.DataFrame:
    """One month's persons, the variables the gauge needs, weights in persons."""
    payload = _open_records(path)
    colspecs = [(positions[v][0] - 1, positions[v][1]) for v in VARIABLES]
    frame = pd.read_fwf(io.BytesIO(payload), colspecs=colspecs, names=VARIABLES,
                        dtype=str, header=None)
    for column in VARIABLES:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["weight"] = frame["PWCMPWGT"].fillna(frame["PWSSWGT"]) / WEIGHT_SCALE
    frame = frame[frame["weight"] > 0]
    year, month = int(frame["HRYEAR4"].mode().iloc[0]), int(frame["HRMONTH"].mode().iloc[0])
    frame["period"] = pd.Period(year=year, month=month, freq="M")
    checks.within(frame["HRMIS"].dropna(), 1, 8, LAYER, f"month in sample {year}-{month:02d}")
    checks.within(frame["PRTAGE"].dropna(), 0, 85, LAYER, f"age {year}-{month:02d}")
    population = float(frame.loc[frame["PRTAGE"] >= 16, "weight"].sum())
    checks.note(LAYER, f"weighted civilian population 16+ {year}-{month:02d}",
                f"{population / 1e6:.1f} million; the published figure is between 265 and 275 million",
                population)
    return frame


def census_to_soc(crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Census 2018 occupation code to the SOC codes it spans, one row per pair."""
    out = crosswalk.rename(columns=str.lower)
    census_col = next(c for c in out.columns if "census" in c and "code" in c)
    soc_col = next(c for c in out.columns if "soc" in c and "code" in c)
    pairs = pd.DataFrame({
        "census_code": pd.to_numeric(out[census_col], errors="coerce"),
        "soc_code": out[soc_col].astype(str).str.strip(),
    }).dropna()
    pairs["census_code"] = pairs["census_code"].astype(int)
    pairs = pairs[pairs["soc_code"].str.match(r"^\d{2}-\d{4}$")].drop_duplicates()
    checks.nonnegative(pairs["census_code"], LAYER, "census code")
    return pairs


def score_census_codes(pairs: pd.DataFrame, exposure: pd.Series,
                       employment: pd.Series) -> pd.Series:
    """Exposure per Census code, employment-weighted over the SOC codes it spans."""
    joined = pairs.assign(exposure=pairs["soc_code"].map(exposure),
                          employment=pairs["soc_code"].map(employment))
    joined = joined.dropna(subset=["exposure"])
    joined["employment"] = joined["employment"].fillna(joined["employment"].median())
    scored = joined.groupby("census_code").apply(
        lambda b: np.average(b["exposure"], weights=b["employment"]), include_groups=False)
    checks.coverage(len(scored), pairs["census_code"].nunique(), LAYER,
                    "census codes with an exposure score", 0.9)
    return scored.rename("exposure")


def _tercile_of(scored: pd.Series, employment_by_census: pd.Series) -> pd.Series:
    aligned = pd.concat([scored.rename("exposure"), employment_by_census.rename("w")], axis=1, join="inner")
    aligned = aligned.sort_values("exposure")
    cumulative = aligned["w"].cumsum() / aligned["w"].sum()
    tercile = pd.Series(1, index=aligned.index)
    tercile[cumulative > 1 / 3] = 2
    tercile[cumulative > 2 / 3] = 3
    return tercile


def monthly_cells(persons: pd.DataFrame, tercile: pd.Series) -> pd.DataFrame:
    """Weighted employment by period, rotation group, age group and tercile."""
    employed = persons[persons["PEMLR"].isin(EMPLOYED_CODES)].copy()
    employed["tercile"] = employed["PEIO1OCD"].map(tercile)
    scored = employed["tercile"].notna()
    checks.coverage(float(employed.loc[scored, "weight"].sum()), float(employed["weight"].sum()),
                    LAYER, "employed persons on a scored occupation", 0.9)
    employed = employed[scored]
    employed["age_group"] = np.select(
        [employed["PRTAGE"].between(*config.YOUNG_AGE), employed["PRTAGE"].between(*PRIME_AGE)],
        ["young", "prime"], default="other")
    employed = employed[employed["age_group"] != "other"]
    employed["top"] = employed["tercile"].eq(3)
    cells = (employed.groupby(["period", "HRMIS", "age_group", "top"])["weight"].sum()
             .rename("employment").reset_index())
    checks.nonnegative(cells["employment"], LAYER, "cell employment")
    return cells


def gauge(cells: pd.DataFrame, base: tuple[str, str] = ("2022-01", "2022-12"),
          pooling: int = 3) -> pd.DataFrame:
    """Top-tercile employment relative to the rest, young against prime, indexed.

    The ratio is pooled over three months to steady it. The reading is the
    young ratio divided by the prime ratio, indexed to the base year, so a
    value of 0.9 means young workers' relative employment in exposed
    occupations sits ten percent below where the prime-age ratio would put it.
    """
    wide = (cells.groupby(["period", "age_group", "top"])["employment"].sum()
            .unstack("top").rename(columns={True: "top", False: "rest"}))
    wide["ratio"] = wide["top"] / wide["rest"]
    ratio = wide["ratio"].unstack("age_group").sort_index()
    pooled = ratio.rolling(pooling, min_periods=pooling).mean()
    base_mask = (pooled.index >= pd.Period(base[0], "M")) & (pooled.index <= pd.Period(base[1], "M"))
    baseline = pooled[base_mask].mean()
    indexed = pooled / baseline
    out = pd.DataFrame({
        "young_ratio_indexed": indexed["young"],
        "prime_ratio_indexed": indexed["prime"],
    })
    out["young_relative_to_prime"] = out["young_ratio_indexed"] / out["prime_ratio_indexed"]
    out = out.dropna().reset_index()
    out["period"] = out["period"].astype(str)
    checks.nonnegative(out["young_relative_to_prime"], LAYER, "gauge")
    return out


def reference_distribution(cells: pd.DataFrame, treated_from: str, draws: int = 500,
                           seed: int = config.SEED) -> pd.DataFrame:
    """Relabel post-period months at the rotation-group level.

    Each rotation group's months are permuted as a block, so a person's
    consecutive months stay together; the statistic is the mean of the
    gauge over the treated months minus its mean over the rest.
    """
    rng = np.random.default_rng(seed)
    periods = sorted(cells["period"].unique())
    treated = [p for p in periods if p >= pd.Period(treated_from, "M")]
    n_treated = len(treated)
    if n_treated == 0 or n_treated >= len(periods):
        raise ValueError("treated period must fall inside the available months")

    def statistic(frame: pd.DataFrame, treated_periods: list) -> float:
        g = gauge(frame, base=(str(periods[0]), str(periods[min(11, len(periods) - 1)])))
        g["treated"] = g["period"].isin([str(p) for p in treated_periods])
        if g["treated"].sum() == 0 or (~g["treated"]).sum() == 0:
            return np.nan
        return float(g.loc[g["treated"], "young_relative_to_prime"].mean()
                     - g.loc[~g["treated"], "young_relative_to_prime"].mean())

    observed = statistic(cells, treated)
    null = []
    for _ in range(draws):
        shuffled = cells.copy()
        for group, block in cells.groupby("HRMIS"):
            order = rng.permutation(periods)
            mapping = dict(zip(periods, order))
            shuffled.loc[block.index, "period"] = block["period"].map(mapping)
        null.append(statistic(shuffled, treated))
    null = pd.Series(null).dropna()
    return pd.DataFrame([{
        "observed_shift": round(observed, 4),
        "threshold_95": round(float(null.abs().quantile(0.95)), 4),
        "p_two_sided": round(float((null.abs() >= abs(observed)).mean()), 3),
        "draws": int(len(null)),
    }])
