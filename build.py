"""Run every layer, write the tables, the checks and the manifest.

Each layer runs when its inputs are on disk and is skipped, with a note in
the manifest, when they are not. Nothing here computes; the layers do. The
order is the order of dependence: the spine and the wage bill first,
exposure next, then the usage, outcome, state, pipeline and capacity
layers, which read from those.

Run as:  python -m aiindex.build
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

from . import (acs, btos, capacity, checks, config, cps, exposure, ipeds, onet_release,
               outcomes, pipeline, spine, state, usage, wagebill)
from .manifest import MANIFEST

sys.path.insert(0, str(config.REPO_ROOT))

SKIPPED: dict[str, str] = {}


def _write(name: str, frame: pd.DataFrame) -> None:
    config.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(config.TABLE_DIR / f"{name}.csv", index=False)


def _step(label: str):
    def wrap(function):
        def run(*args, **kwargs):
            started = time.time()
            try:
                out = function(*args, **kwargs)
            except FileNotFoundError as error:
                SKIPPED[label] = str(error)
                print(f"  skipped {label}: {error}")
                return None
            print(f"  {label}: {time.time() - started:.0f}s")
            return out
        return run
    return wrap


@_step("spine")
def build_spine() -> dict:
    return {
        "onetsoc": spine.onetsoc_to_soc(),
        "census": spine.census_to_soc(),
        "cip": spine.cip_to_soc(),
        "soc2010": spine.soc_2010_to_2018(),
    }


@_step("wage bill")
def build_wagebill() -> dict:
    wagebill.ensure_files()
    panel = wagebill.harmonise(wagebill.load(grade="mirror"))
    national = wagebill.national(panel)
    states = wagebill.by_state(panel)
    _write("wagebill_national", national)
    _write("wagebill_state_latest", states[states["vintage"] == states["vintage"].max()])
    return {"panel": panel, "national": national, "state": states}


@_step("exposure")
def build_exposure(national: pd.DataFrame) -> pd.DataFrame:
    table = exposure.table()
    latest = national[national["vintage"] == national["vintage"].max()].set_index("soc_code")
    table["employment_latest"] = latest["employment"]
    table["wage_bill_latest"] = latest["bill"]
    _write("exposure_by_occupation", table.reset_index())
    return table


@_step("usage")
def build_usage(national: pd.DataFrame, names: dict[str, str]) -> dict | None:
    from . import aei
    tables = aei.usage_tables()
    if tables is None:
        raise FileNotFoundError("no Anthropic Economic Index release in data/raw/aei")
    from src import gamma as gamma_module
    build = gamma_module.build()
    latest = national[national["vintage"] == national["vintage"].max()].set_index("soc_code")["bill"]
    values = usage.task_values_table(latest)
    task_bundles = usage.task_bundle_matrix(build)
    validated = pd.concat([usage.validate_usage(t) for t in tables], ignore_index=True)
    out = usage.readings(validated, values, task_bundles, names)
    _write("usage_reach", out["reach"])
    _write("usage_landing", out["landing"])
    _write("usage_by_occupation", out["by_occupation"])
    return out


@_step("outcomes")
def build_outcomes(national: pd.DataFrame, bundles: pd.DataFrame) -> dict:
    panel = national.merge(bundles, left_on="soc_code", right_index=True, how="inner")
    out = outcomes.build(panel, list(bundles.columns))
    _write("outcomes_pay_series", out["pay"])
    _write("outcomes_quantity_series", out["quantity"])
    _write("outcomes_pay_changes", out["pay_changes"].reset_index().rename(columns={"index": "year"}))
    return out


@_step("state")
def build_state(states: pd.DataFrame, measures: pd.DataFrame) -> dict:
    panel = states[states["vintage"] >= 2019]
    ex = state.exposure_by_state(panel, measures[[c for c in measures.columns if c in config.EXPOSURE_MEASURES or c in ("eloundou_beta", "felten_aioe")]])
    _write("state_exposure", ex)
    changes = []
    for measure in ("eloundou_beta", "felten_aioe"):
        if measure in measures.columns:
            years = sorted(panel["vintage"].unique())
            changes.append(state.realised_change(panel, measures, int(years[-3]), int(years[-1]), measure))
    change = pd.concat(changes, ignore_index=True) if changes else pd.DataFrame()
    _write("state_realised_change", change)
    adoption = state.with_fips(btos.state_series()).dropna(subset=["share_using_ai", "state_fips"])
    annual = pd.concat([
        state.btos_annual(block.rename(columns={"ref_end": "period_end"})).assign(series=series)
        for series, block in adoption.groupby("series")], ignore_index=True)
    annual["state_abbr"] = annual["state_fips"].map({v: k for k, v in state.STATE_FIPS.items()})
    _write("state_adoption_btos", annual)
    _write("state_adoption_btos_biweekly", adoption)
    return {"exposure": ex, "change": change, "adoption": annual}


@_step("pipeline")
def build_pipeline(measures: pd.DataFrame, national: pd.DataFrame) -> dict:
    latest = national[national["vintage"] == national["vintage"].max()].set_index("soc_code")["employment"]
    scored = measures[["eloundou_beta", "felten_aioe"]]
    field_xw = pipeline.field_exposure_from_crosswalk(scored, latest)
    _write("pipeline_field_exposure_crosswalk", field_xw)
    persons = acs.person_file()
    link = acs.field_occupation_link(persons)
    field_acs = pipeline.field_exposure_from_acs(link.rename(columns={"weight": "weight"}), scored)
    _write("pipeline_field_exposure_acs_test_state", field_acs)
    inst = ipeds.institutions(2023)
    frames = []
    for year in (2023, 2024):
        frames.append(ipeds.completions(year))
    awards = pd.concat(frames, ignore_index=True)
    by_state = pipeline.completions_by_state(awards, inst, field_xw, "eloundou_beta")
    _write("pipeline_completions_by_state", by_state)
    nsc_path = config.RAW_DIR / "nsc" / "major_field_appendix.csv"
    grade = "real"
    if not nsc_path.exists():
        # The Clearinghouse host is unreachable from some networks and no copy
        # of the appendix is committed anywhere public. A fixture in its shape
        # stands in, graded as such, so the table exists in its final form.
        nsc_path, grade = config.FIXTURE_DIR / "nsc_major_field_fixture.csv", "fixture"
    MANIFEST.record("nsc_major_field", nsc_path, grade=grade, source_url=str(nsc_path),
                    official_url="https://nscresearchcenter.org/current-term-enrollment-estimates/")
    nsc = pd.read_csv(nsc_path)
    enrolment = pipeline.enrolment_by_exposure(nsc, field_xw, "eloundou_beta")
    _write("pipeline_enrolment_by_exposure", enrolment)
    return {"field_crosswalk": field_xw, "field_acs": field_acs, "completions": by_state, "enrolment": enrolment}


@_step("capacity")
def build_capacity(measures: pd.Series) -> dict | None:
    path = config.RAW_DIR / "flows" / "transition_matrix.csv"
    arrivals_path = config.RAW_DIR / "flows" / "arrivals.csv"
    grade = "real"
    if not path.exists():
        # The flows repository has not published the matrix. The layer runs on
        # the schema fixture so that its tables exist, and the manifest says so.
        path = config.FIXTURE_DIR / "transition_matrix_fixture.csv"
        arrivals_path = config.FIXTURE_DIR / "arrivals_fixture.csv"
        grade = "fixture"
    MANIFEST.record("flows_transition_matrix", path, official_url="flows repository, unpublished",
                    grade=grade, source_url=str(path), notes="year by age band by origin by destination")
    matrix = capacity.validate_matrix(pd.read_csv(path, dtype={"origin": str, "destination": str}))
    cut = float(measures.quantile(2 / 3))
    exit_share = capacity.exit_share(matrix, measures, cut)
    _write("capacity_exit_share", exit_share)
    if arrivals_path.exists():
        MANIFEST.record("flows_arrivals", arrivals_path, official_url="flows repository, unpublished",
                        grade=grade, source_url=str(arrivals_path))
        arrivals = capacity.validate_arrivals(pd.read_csv(arrivals_path, dtype={"occupation": str}))
        _write("capacity_education_channel", capacity.education_channel(arrivals))
    return {"exit_share": exit_share}


@_step("cps gauge")
def build_cps(measures: pd.Series, employment: pd.Series) -> pd.DataFrame | None:
    months = sorted(cps.CPS_DIR.glob("*pub.dat*")) + sorted(cps.CPS_DIR.glob("*.zip"))
    grade = "real"
    if not months:
        # The Census host is unreachable from some networks. The gauge then runs
        # on synthetic months written on the real 2025 layout, so the tables
        # exist in their final shape, and every one of them is graded fixture.
        months = sorted((config.FIXTURE_DIR / "cps").glob("*pub.dat"))
        grade = "fixture"
        if not months:
            raise FileNotFoundError(f"no CPS basic monthly files in {cps.CPS_DIR} and no fixture months")
    for path in months:
        MANIFEST.record(f"cps:{path.name}", path, official_url=cps.OFFICIAL, grade=grade,
                        source_url=None if grade == "real" else str(path))
    layouts = {int(p.name[:4]): p for p in (cps.CPS_DIR / "layouts").glob("*Record_Layout*.txt")}
    for year, path in layouts.items():
        sidecar = path.with_suffix(path.suffix + ".source")
        lg, src = sidecar.read_text().split("\n")[:2] if sidecar.exists() else ("real", cps.OFFICIAL)
        MANIFEST.record(f"cps_layout_{year}", path, official_url=cps.OFFICIAL, grade=lg, source_url=src)
    pairs = spine.census_to_soc()
    scored = cps.score_census_codes(pairs, measures, employment)
    emp_by_census = pairs.assign(e=pairs["soc_code"].map(employment)).groupby("census_code")["e"].sum()
    scored.index = scored.index.astype(str)
    tercile = cps._tercile_of(scored, emp_by_census)
    tercile.index = tercile.index.astype(int)
    frames = []
    for path in months:
        year = 2000 + int(path.name[3:5]) if path.name[3:5].isdigit() else max(layouts)
        layout = layouts.get(year) or layouts[max(layouts)]
        positions = cps.parse_layout(layout.read_text(errors="replace"))
        frames.append(cps.read_month(path, positions))
    persons = pd.concat(frames, ignore_index=True)
    cells = cps.monthly_cells(persons, tercile)
    periods = sorted(cells["period"].unique())
    base = ("2022-01", "2022-12") if grade == "real" else (str(periods[0]), str(periods[min(2, len(periods) - 1)]))
    gauge = cps.gauge(cells, base=base, pooling=3 if grade == "real" else 2)
    _write("cps_young_worker_gauge", gauge)
    _write("cps_cells", cells.assign(period=cells["period"].astype(str)))
    return gauge


def main() -> None:
    started = time.time()
    checks.reset()
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("aiindex build")
    release = onet_release.activate() if onet_release.available() else None
    if release is None:
        onet_release.ensure()
        release = onet_release.activate()
    print(f"  O*NET release {release}")
    from src import bundles as bundle_module

    build_spine()
    wages = build_wagebill()
    measures = build_exposure(wages["national"])
    names = bundle_module.names()
    occupation_bundles = bundle_module.occupation_bundles()
    build_outcomes(wages["national"], occupation_bundles)
    build_usage(wages["national"], names)
    build_state(wages["state"], measures)
    build_pipeline(measures, wages["national"])
    latest = wages["national"][wages["national"]["vintage"] == wages["national"]["vintage"].max()].set_index("soc_code")
    build_capacity(measures["eloundou_beta"].dropna())
    build_cps(measures["eloundou_beta"].dropna(), latest["employment"])

    checks.write()
    MANIFEST.write()
    report = {
        "seconds": round(time.time() - started),
        "onet_release": release,
        "grades": MANIFEST.grades(),
        "skipped": SKIPPED,
        "checks": {"passed": int(sum(r["ok"] for r in checks.ROWS)), "rows": len(checks.ROWS)},
    }
    (config.OUTPUT_DIR / "build_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "grades"}, indent=2))
    grades = pd.Series(report["grades"]).value_counts().to_dict()
    print(f"  input grades: {grades}")


if __name__ == "__main__":
    main()
