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
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import (acs, btos, capacity, checks, config, cps, exposure, ipeds, onet_release, postings,
               openai, outcomes, pipeline, spine, state, usage, wagebill, site_static)
from .manifest import MANIFEST

sys.path.insert(0, str(config.PAPER_ROOT))

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
    panel = wagebill.harmonise(wagebill.load())
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
    for rule in ("dollar", "equal"):
        try:
            tables.append(openai.usage_table(values, rule=rule))
        except ConnectionError as error:
            SKIPPED[f"openai {rule}"] = str(error)
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
    # The paper's construction: occupations present in every year.
    fixed = outcomes.build(outcomes.balanced(panel), list(bundles.columns))
    _write("outcomes_pay_series_balanced", fixed["pay"])
    _write("outcomes_quantity_series_balanced", fixed["quantity"])
    _write("outcomes_pay_changes", out["pay_changes"].reset_index().rename(columns={"index": "year"}))
    return out


@_step("state")
def build_state(states: pd.DataFrame, measures: pd.DataFrame) -> dict:
    panel = states[states["vintage"] >= 2019]
    ex = state.exposure_by_state(panel, measures[[c for c in ("eloundou_beta", "felten_aioe", "anthropic_observed") if c in measures.columns]])
    _write("state_exposure", ex)
    changes = []
    for measure in ("eloundou_beta", "felten_aioe", "anthropic_observed"):
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
    from . import aei
    usage_states = []
    for path in sorted(aei.AEI_DIR.rglob("aei_raw_claude_ai_*.csv")):
        table = aei.state_usage(path)
        if table is not None:
            usage_states.append(table)
    if usage_states:
        usage_state = state.with_fips(pd.concat(usage_states, ignore_index=True))
        latest = states[states["vintage"] == states["vintage"].max()]
        employment_share = latest.groupby("state_fips")["employment"].sum()
        employment_share = employment_share / employment_share.sum()
        usage_state["employment_share"] = usage_state["state_fips"].map(employment_share)
        usage_state["usage_per_worker_index"] = usage_state["usage_share"] / usage_state["employment_share"]
        _write("state_usage_anthropic", usage_state)
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
    _write("pipeline_field_exposure_acs", field_acs)
    inst = ipeds.institutions(2025)
    frames = []
    for year in (2023, 2024, 2025):
        frames.append(ipeds.completions(year))
    awards = pd.concat(frames, ignore_index=True)
    by_state = pipeline.completions_by_state(awards, inst, field_xw, "eloundou_beta")
    _write("pipeline_completions_by_state", by_state)
    nsc_path = config.RAW_DIR / "nsc" / "major_field_appendix.csv"
    grade = "real"
    ctee = sorted((config.RAW_DIR / "nsc").glob("CTEE*CIPGroupEnrollment*.xlsx"))
    if ctee:
        nsc_path = config.OUTPUT_DIR / "tables" / "nsc_cip_family_enrolment.csv"
        pipeline.clearinghouse_cip_families(ctee[-1]).to_csv(nsc_path, index=False)
        MANIFEST.record("nsc_cip_group_enrolment", ctee[-1], grade="real",
                        official_url="https://nscresearchcenter.org/current-term-enrollment-estimates/")
    elif not nsc_path.exists():
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
    months = sorted(cps.CPS_DIR.glob("*pub.dat*")) + sorted(cps.CPS_DIR.glob("*.zip")) + sorted(cps.CPS_DIR.glob("*pub.csv"))
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
        if path.suffix.lower() == ".csv":
            frames.append(cps.read_month(path))
            continue
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
    if grade == "real" and len(periods) > 24:
        # the last twelve months of data against the months before them, with months relabelled within rotation groups
        treated_from = str(periods[-12])
        # the relabelled draws recompute the gauge a thousand times; their own unit checks are not part of the record
        kept = len(checks.ROWS)
        test = cps.reference_distribution(cells, treated_from, draws=1000)
        del checks.ROWS[kept:]
        test.insert(0, "treated_from", treated_from)
        test.insert(1, "last_period", str(periods[-1]))
        checks.note("cps", "young-worker gauge, last twelve months against the rest",
                    f"{test.iloc[0]['observed_shift']:+.4f} against a threshold of {test.iloc[0]['threshold_95']:.4f}",
                    float(test.iloc[0]["observed_shift"]))
        _write("cps_young_worker_test", test)
    return gauge


@_step("postings")
def build_postings() -> dict:
    out = postings.build()
    _write("postings_step_at_release", out["reading"])
    _write("postings_release_bound", out["step"])
    _write("postings_gradient_quarterly", out["quarterly"])
    _write("postings_specified_test", out["specified"])
    # the average exposure of tasks named in ads moves with which tasks are named as well as with their shares;
    # it is written for inspection and kept off the page until the difference from the gradient is understood
    _write("postings_asked_exposure_monthly", out["asked"])
    return out


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
    build_postings()

    checks.write()
    MANIFEST.write()
    try:
        print(f"  site readings: {export_site(release)}")
    except FileNotFoundError as error:
        SKIPPED["site"] = str(error)
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


_SMALL = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
          "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def _words(n: int) -> str:
    """Small counts in words, as they read in a sentence; larger ones as numerals."""
    return _SMALL[n] if 0 <= n < len(_SMALL) else str(n)


def _published(label: str) -> str:
    """A release label such as '2026-06-26 (2026-05)' as the month it was published, 'June 2026'."""
    return datetime.strptime(str(label).split(" ")[0][:7], "%Y-%m").strftime("%B %Y")


def _fraction(x: float) -> str:
    """A share as the plain fraction nearest to it, for a sentence that should not read like a table."""
    names = [(0.1, "a tenth"), (0.125, "an eighth"), (1 / 6, "a sixth"), (0.2, "a fifth"), (0.25, "a quarter"),
             (1 / 3, "a third"), (0.4, "two fifths"), (0.5, "half")]
    return min(names, key=lambda n: abs(n[0] - x))[1]


def _joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def export_site(release: str) -> Path:
    """Write the readings the front page shows, from the built tables.

    The page reads ``site/data/readings.json`` and shows what it carries: the
    opening sentence, the paragraphs under "What does this mean", each view's
    numbers with the sentence each one begins, the line on the drawing, and the
    notices the banner plane tows. Every number in them is a cell of a table in
    ``output/tables``, and every sentence is assembled here from those cells, so
    the page cannot say a number, or a claim about one, that the build did not
    write. The Pages workflow publishes the tables beside the page, under
    ``data/tables``, which is where the page's links point.
    """
    from src import bundles as bundle_module

    tables = config.TABLE_DIR
    names = {k: v for k, v in bundle_module.names().items()}
    name = lambda code: names.get(code, code).lower()
    reach = pd.read_csv(tables / "usage_reach.csv")
    anthropic = reach[reach["platform"] == "anthropic"].sort_values("release")
    # reach counts every published task, so the headline comes from the latest release that publishes
    # all of its use; a release with a reporting threshold is in the table and not in the headline
    complete = anthropic[anthropic["published_use"] >= 0.99]
    latest, first = complete.iloc[-1], complete.iloc[0]
    newest = anthropic.iloc[-1]
    # the monthly slices carry no collaboration split, so the delegated share comes from the last release that does
    split = anthropic[anthropic["delegated_share"] > 0].iloc[-1]
    landing = pd.read_csv(tables / "usage_landing.csv")
    here = landing[(landing["platform"] == "anthropic") & (landing["release"] == latest["release"])].sort_values("concentration")
    top, low = here.iloc[-1], here.iloc[0]
    pay_all = pd.read_csv(tables / "outcomes_pay_series_balanced.csv")
    qty_all = pd.read_csv(tables / "outcomes_quantity_series_balanced.csv")
    pay, qty = pay_all.iloc[-1], qty_all.iloc[-1]
    completions = pd.read_csv(tables / "pipeline_completions_by_state.csv")
    bach = completions[completions["award_level"] == 5].groupby("year")[["awards_exposed", "awards_unexposed"]].sum()
    share = bach["awards_exposed"] / bach.sum(axis=1)
    year = int(share.index.max())
    degrees, before = float(share.loc[year]) * 100, float(share.loc[year - 1]) * 100 if year - 1 in share.index else None

    # the valley: enrolment by the exposure of the field family, and young workers' place in exposed jobs
    enrol = pd.read_csv(tables / "pipeline_enrolment_by_exposure.csv")
    e_last, e_first = enrol.iloc[-1], enrol.iloc[0]
    enrolled, enrolled_first = float(e_last["share_exposed"]) * 100, float(e_first["share_exposed"]) * 100
    gauge = pd.read_csv(tables / "cps_young_worker_gauge.csv")
    g_last = gauge.iloc[-1]
    young = (1 - float(g_last["young_relative_to_prime"])) * 100
    g_when = datetime.strptime(str(g_last["period"]), "%Y-%m").strftime("%B %Y")
    test_path = tables / "cps_young_worker_test.csv"
    gtest = pd.read_csv(test_path).iloc[0] if test_path.exists() else None

    # what employers ask for: the step at the release in the job-ad gradient, and when the fall came
    asks = pd.read_csv(tables / "postings_step_at_release.csv").iloc[0]
    grad = pd.read_csv(tables / "postings_gradient_quarterly.csv").set_index("quarter")["all_coef"]
    pre_release = grad[[q for q in grad.index if q < "2022Q4"]]
    post_release = grad[[q for q in grad.index if q >= "2022Q4"]]
    low_q = pre_release.idxmin()
    ordinal = {"1": "first", "2": "second", "3": "third", "4": "fourth"}
    low_when = f"the {ordinal[low_q[-1]]} quarter of {low_q[:4]}"
    fell_before = float(pre_release.min()) <= float(post_release.mean())
    asks_out = asks["statistic"] >= asks["threshold_95"]
    # how much of the fall the latest quarter has made up, measured from the lowest quarter after the release
    low_after = float(post_release.min())
    made_up = (float(grad.iloc[-1]) - low_after) / -low_after if low_after < 0 else 0.0
    last_when = f"the {ordinal[grad.index[-1][-1]]} quarter of {grad.index[-1][:4]}"

    wages = round(float(latest["reach_share"]) * 100)
    core = float(newest["reach_share_three_quarters"]) * 100
    core_first = float(anthropic.iloc[0]["reach_share_three_quarters"]) * 100
    since = int(pay["first_transition"])
    pay_out = pay["largest_statistic"] >= pay["threshold_95"]
    qty_out = qty["largest_statistic"] >= qty["threshold_95"]
    qty_record = qty_out and int(qty["earlier_windows_at_least"]) == 0
    flagged = [int(y) for y, s_, t_ in zip(qty_all["year"], qty_all["largest_statistic"], qty_all["threshold_95"])
               if s_ > t_ and int(y) != int(qty["year"])]
    others = int(qty["consecutive_relabellings"]) - 1
    odds = round(1 / float(qty["p_largest_consecutive"])) if qty["p_largest_consecutive"] > 0 else None
    toward = "toward" if int(qty["largest_direction"]) > 0 else "away from"

    # The words on the page. Every sentence is written for a reader who has not seen the method: what moved, by how much,
    # and the one thing that limits it. The tests behind the city are described by what they compare, never by their units.
    def series(x, y, fmt, threshold=None, unit=""):
        return {"x": [str(v) for v in x], "y": [round(float(v), 4) for v in y], "fmt": fmt, "unit": unit,
                "threshold": None if threshold is None else [round(float(v), 4) for v in threshold]}
    def label(release):
        tag = str(release)
        return _published(tag) + (f" ({datetime.strptime(tag.split('(')[1][:7], '%Y-%m').strftime('%b')})"
                                   if "(" in tag and len(tag.split("(")[1].rstrip(")")) == 7 else "")
    def pct(x, digits=0):
        return f"{x * 100:.{digits}f}%"

    first_share = round(float(first["reach_share"]) * 100)
    top_name, low_name = top["bundle"].lower(), low["bundle"].lower()
    top_path = landing[(landing["platform"] == "anthropic") & (landing["bundle"] == top["bundle"])
                       & landing["release"].isin(complete["release"])].sort_values("release")
    young_series = gauge.assign(v=(gauge["young_relative_to_prime"] - 1) * 100)
    start, end = int(pay["year"]) - 3, int(pay["year"])
    earlier = int(pay["consecutive_relabellings"]) - 1
    pay_moved = "rise" if int(pay["largest_direction"]) > 0 else "fall"
    mix_field = name(qty["largest_bundle"])
    shift_word = "toward" if int(qty["largest_direction"]) > 0 else "away from"
    tasks_core = int(newest["tasks_three_quarters"])
    shift_pts = abs(float(gtest["observed_shift"])) * 100 if gtest is not None else None
    draws = int(gtest["draws"]) if gtest is not None else 0
    as_large = round(float(gtest["p_two_sided"]) * draws) if gtest is not None else 0
    rinz = "Rinz (2026), Federal Reserve Bank of Cleveland Working Paper 26-24"
    pay_big = "Unusual change" if pay_out else "No unusual change"
    mix_big = (f"Largest shift since {since}" if qty_record else "Unusual shift" if qty_out else "No unusual shift")
    ads_big = "Fell before ChatGPT" if fell_before and not asks_out else "Changed at ChatGPT's release" if asks_out else "No change at ChatGPT's release"

    views = {
        "bridge": {
            "index": "Use", "index_line": "How much of the country's paid work people use AI for",
            "capline": f"{wages}% of US wages are in tasks people use AI for; {_published(latest['release'])}",
            "mark": f"{wages}% of US wages are in tasks people use AI for",
            "headline": (f"Tasks people use AI for make up {wages}% of US wages, and the heaviest use, relative to pay, "
                         f"is on {top_name}."),
            "items": [
                {"title": "Share of US wages in tasks people use AI for", "big": f"{wages}%",
                 "note": (f"Up from {first_share}% in {_published(first['release'])}. A task counts once people use Claude for it at all, "
                          f"so this shows how widely AI use has spread across paid work, but not how much of that work AI does."),
                 "more": (f"The Anthropic Economic Index sorts conversations with Claude into the job tasks the Labor Department lists for "
                          f"each occupation (O*NET). We add up what US workers earn on the tasks that appear, using the BLS wage tables. "
                          f"The June 2026 file leaves out rarely used tasks, so this figure uses {_published(latest['release'])}, the most "
                          f"recent file that lists them all. Tasks people hand to Claude to do entirely account for "
                          f"{round(float(split['delegated_share']) * 100)}% of US wages."),
                 "src": f"Anthropic Economic Index, {_published(latest['release'])}; OEWS wages, May {int(pay['year'])}",
                 "series": series([label(r) for r in complete["release"]], complete["reach_share"] * 100, "pct0", unit="% of US wages"),
                 "tables": ["usage_reach.csv"]},
                {"title": "Where AI use is heaviest", "big": f"{top['concentration']:.1f}×",
                 "note": (f"{top_name.capitalize()} account for {pct(top['usage_share_on_bundle'], 1)} of AI use but only "
                          f"{pct(top['wage_bill_share_on_bundle'], 1)} of US wages, {top['concentration']:.1f} times as much use as "
                          f"their share of pay. {low_name.capitalize()} get the least, {low['concentration']:.1f} times."),
                 "more": (f"We sort job tasks into 25 skill groups and compare each group's share of AI use with its share of US wages. "
                          f"A value above 1 means people use AI on that group's tasks more than its share of pay alone would lead you to expect."),
                 "src": f"Anthropic Economic Index, {_published(latest['release'])}; O*NET {release}",
                 "series": series([label(r) for r in top_path["release"]], top_path["concentration"], "x1", unit="AI use relative to share of pay"),
                 "tables": ["usage_landing.csv"]},
                {"title": "Wages in the most-used tasks", "big": f"{core:.1f}%",
                 "note": (f"Three quarters of all AI use comes from just {tasks_core} tasks. Those tasks account for {core:.1f}% of US wages, "
                          f"up from {core_first:.1f}% in {_published(anthropic.iloc[0]['release'])}."),
                 "more": (f"Because no release leaves the most-used tasks out, this figure can be compared across every release, the June "
                          f"2026 file included. Its rise means the work people use AI for most is moving toward tasks that make up "
                          + ("more" if core > core_first else "less") + " of total US pay."),
                 "src": f"Anthropic Economic Index, {_published(newest['release'])}; OEWS wages, May {int(pay['year'])}",
                 "series": series([label(r) for r in anthropic["release"]], anthropic["reach_share_three_quarters"] * 100, "pct1", unit="% of US wages"),
                 "tables": ["usage_reach.csv"]},
            ],
            "how": ("The Anthropic Economic Index sorts conversations with Claude into the job tasks that O*NET lists for each occupation. "
                    "We weight each task by what US workers earn doing it, from the latest BLS wage tables, and update the figures with "
                    "each new release of the index, every few months. Only one platform's data are used so far."),
        },
        "city": {
            "index": "Jobs", "index_line": "Whether pay, jobs and hiring have changed",
            "capline": (f"Pay: {pay_big.lower()}. Job mix: {mix_big.lower()}. Job ads: {ads_big[0].lower() + ads_big[1:]}."),
            "mark": f"Pay: {pay_big.lower()}. Job mix: {mix_big.lower()}.",
            "headline": (("Pay has changed more than usual" if pay_out else "Pay hasn't changed more than usual")
                         + (f", the mix of jobs has shifted more than at any time since {since}" if qty_record else
                            ", the mix of jobs has shifted more than usual" if qty_out else "")
                         + (", and job ads turned away from tasks AI can do before ChatGPT came out." if fell_before else
                            ", and job ads show no change at ChatGPT's release.")),
            "items": [
                {"title": "Pay across skill groups", "big": pay_big,
                 "note": (f"The largest pay change in any skill group between {start} and {end}, a {pay_moved} for jobs that rely heavily on "
                          f"{name(pay['largest_bundle'])}, was smaller than the largest change in {_words(int(pay['earlier_windows_at_least']))} "
                          f"of the {_words(earlier)} earlier three-year periods since {since}."
                          if not pay_out else
                          f"Pay for jobs that rely heavily on {name(pay['largest_bundle'])} changed more between {start} and {end} than in almost "
                          f"any earlier three-year period since {since}."),
                 "more": (f"For each of 25 skill groups, we compare the pay change over the last three years with that group's own "
                          f"changes since {since}. We count a change as unusual only if it is larger than 95% of the changes we get by "
                          f"reshuffling the years at random. The figures use average pay across whole occupations, so a raise for new "
                          f"hires and a cut for people already in the job would cancel out."),
                 "related": (f"{rinz}, finds that from the second half of 2024, workers who stayed in more exposed jobs saw a small fall "
                             f"in real earnings, under 1%. That is after the last year of these wage tables."),
                 "src": f"OEWS, May {since - 1} to May {int(pay['year'])}, occupations present in every year",
                 "series": series(pay_all["year"], pay_all["largest_statistic"], "num1", pay_all["threshold_95"], "size of the largest change"),
                 "tables": ["outcomes_pay_series_balanced.csv", "outcomes_pay_changes.csv"]},
                {"title": "Mix of jobs", "big": mix_big,
                 "note": ((f"Between {start} and {end}, employment moved {shift_word} jobs that rely heavily on {mix_field}, more than in any "
                           f"three-year period since {since}." if qty_record else
                           f"Between {start} and {end}, employment moved {shift_word} jobs that rely heavily on {mix_field} more than usual." if qty_out else
                           f"Between {start} and {end}, the largest shift was {shift_word} jobs that rely heavily on {mix_field}, within the usual range.")
                          + (f" With only {_words(int(qty['transitions_available']))} years of data, there is about a 1 in {odds} chance "
                             f"of a shift this large even if nothing has changed" if qty_out and odds else "")
                          + (f", and the pandemic also caused an unusual shift, in {_joined([str(y) for y in flagged])}." if qty_out and odds and flagged else
                             "." if qty_out and odds else "")
                          + (f" The spring {int(pay['year']) + 2} wage tables will show whether it lasts." if qty_out else "")),
                 "more": ("The mix of jobs is each skill group's share of total employment, so it changes when people move between "
                          "occupations, which can happen before pay changes at all. It is tested the same way as pay, against each "
                          "group's own history."),
                 "src": f"OEWS, May {since - 1} to May {int(qty['year'])}, occupations present in every year",
                 "series": series(qty_all["year"], qty_all["largest_statistic"], "num1", qty_all["threshold_95"], "size of the largest shift"),
                 "tables": ["outcomes_quantity_series_balanced.csv"]},
                {"title": "Job ads for tasks AI can do", "big": ads_big,
                 "note": ((f"From 2020 to {low_when}, job ads in the same occupation asked less and less often for tasks AI can do. "
                           f"ChatGPT's release in November 2022 brought no further drop" if fell_before and not asks_out else
                           f"Job ads changed at ChatGPT's release in November 2022 more than at almost any earlier month" if asks_out else
                           "Job ads show no change at ChatGPT's release in November 2022")
                          + (f", and by {last_when} ads had recovered {made_up * 100:.0f}% of the decline." if made_up >= 0.25 else ".")),
                 "more": (f"The National Labor Exchange (NLx) data count how often ads in each occupation name each O*NET task. We check "
                          f"whether tasks AI can do lost ground to other tasks in the same occupation, and whether anything changed at "
                          f"ChatGPT's release. In {_words(int(asks['earlier_at_least']))} of the {_words(int(asks['earlier_windows']))} "
                          f"earlier months, the same comparison showed a change at least as large as the one at the release."),
                 "related": (f"{rinz}, finds the same timing in commercial job-ad data: ads in more exposed occupations were declining "
                             f"before ChatGPT and leveled off after it."),
                 "src": "NLx job ads, September 2015 to September 2025, in the aggregates of Meisenbacher, Nestorov and Norlander; Eloundou task measure",
                 "series": series(list(grad.index), grad.to_numpy() * 100, "pp2", unit="share of ads, change since 2019 (points)"),
                 "tables": ["postings_step_at_release.csv", "postings_gradient_quarterly.csv", "postings_release_bound.csv"]},
            ],
            "how": (f"For each of 25 skill groups, we compare the change in pay, and in the share of employment, over the last three "
                    f"years with that group's own history since {since}. A change counts as unusual only if it is larger than 95% of the "
                    f"changes we get by reshuffling the years at random. Both are recalculated each spring, when BLS publishes new wage "
                    f"tables. For job ads, we measure how often ads in each occupation name each task, and check whether tasks AI can "
                    f"do lost ground at ChatGPT's release more than at earlier months."),
        },
        "valley": {
            "index": "Training", "index_line": "What students choose, and whether young workers still get exposed jobs",
            "capline": (f"{degrees:.1f}% of new degrees and {enrolled:.1f}% of enrollment are in exposed fields; "
                        f"young workers down {young:.0f}% in exposed jobs since 2022"),
            "mark": f"{degrees:.1f}% of new degrees are in exposed fields",
            "headline": (f"{degrees:.0f}% of new degrees and {enrolled:.0f}% of four-year enrollment are in the fields most exposed "
                         f"to AI, and young workers have lost ground in exposed jobs since 2022."),
            "items": [
                {"title": "New degrees in exposed fields", "big": f"{degrees:.1f}%",
                 "note": (f"{degrees:.1f}% of {year} bachelor's degrees went to the third of fields whose graduates hold the most "
                          f"AI-exposed jobs" + (f", up from {before:.1f}% in {year - 1}." if before is not None else ".")),
                 "more": ("Degrees by field come from the Education Department's IPEDS completions files. We score each field by the AI "
                          "exposure of the jobs its graduates actually hold, using the Census Bureau's American Community Survey and the "
                          "exposure measure of Eloundou, Manning, Mishkin and Rock (2023)."),
                 "src": f"IPEDS completions, {year}; field exposure from ACS and the Eloundou task measure",
                 "series": series(list(share.index), share.to_numpy() * 100, "pct1", unit="% of bachelor's degrees"),
                 "tables": ["pipeline_completions_by_state.csv", "pipeline_field_exposure_crosswalk.csv"]},
                {"title": "Enrollment in exposed fields", "big": f"{enrolled:.1f}%",
                 "note": (f"{enrolled:.1f}% of four-year undergraduates in {str(e_last['term']).lower()} were in those fields, "
                          f"{'up' if enrolled >= enrolled_first else 'down'} from {enrolled_first:.1f}% in {str(e_first['term']).lower()}. "
                          f"Students choose fields years before they graduate, so a turn away from exposed fields would show up here first."),
                 "more": "Enrollment by field comes from the National Student Clearinghouse and is scored the same way as degrees.",
                 "src": f"National Student Clearinghouse, {e_first['term']} to {e_last['term']}; field exposure from ACS and the Eloundou task measure",
                 "series": series(enrol["term"].str.replace("Fall ", ""), enrol["share_exposed"] * 100, "pct1", unit="% of four-year undergraduates"),
                 "tables": ["pipeline_enrolment_by_exposure.csv", "nsc_cip_family_enrolment.csv"]},
                {"title": "Young workers in exposed jobs", "big": f"−{young:.0f}%",
                 "note": (f"Since 2022, workers aged 22 to 27 have lost ground in the jobs most exposed to AI, by {young:.0f}% compared "
                          f"with workers aged 35 to 54."
                          + (" It is the strongest signal on this page." if gtest is not None and as_large == 0 else "")),
                 "more": ("From the Census Bureau's monthly Current Population Survey. For each age group we divide employment in the most "
                          "exposed third of jobs by employment in all other jobs, then compare the young group's ratio with the older "
                          "group's. "
                          + (f"Over the last 12 months the gap was {shift_pts:.1f} points wider than in the months before. "
                             + (f"In {draws:,} random reorderings of the months, none produced a gap that large. " if as_large == 0 else
                                f"In {draws:,} random reorderings of the months, {as_large} produced a gap that large. ")
                             if gtest is not None else "")
                          + "The data start in January 2022, so they can't show whether the decline began before ChatGPT."),
                 "related": ("Brynjolfsson, Chandar and Chen (2025), Stanford Digital Economy Lab, find a 13% relative decline in "
                             "employment for workers aged 22 to 25 in the most AI-exposed occupations, using payroll data."),
                 "src": f"Current Population Survey, January 2022 to {g_when}",
                 "series": series(young_series["period"], young_series["v"], "pct0s", unit="% change since 2022, against ages 35 to 54"),
                 "tables": ["cps_young_worker_gauge.csv"] + (["cps_young_worker_test.csv"] if gtest is not None else [])},
            ],
            "how": ("We score each field of study by the AI exposure of the jobs its graduates hold, using the Census Bureau's American "
                    "Community Survey and the exposure measure of Eloundou and coauthors. Degrees come from IPEDS and enrollment from "
                    "the National Student Clearinghouse. Young workers come from the monthly Current Population Survey, with jobs "
                    "scored the same way."),
        },
    }
    for view in views.values():
        for entry in view["items"]:
            entry["view"] = next(k for k, v in views.items() if v is view)

    # the opening paragraph: one sentence per index, each linked to its view
    lede = (f'Tasks people use AI for make up <a href="#bridge" data-view="bridge">{wages}% of US wages</a>. '
            + ('<a href="#city" data-view="city">Pay has changed more than usual</a>' if pay_out else
               '<a href="#city" data-view="city">Pay hasn\'t changed more than usual</a>')
            + (f", but the mix of jobs has shifted more than at any time since {since}. " if qty_record else
               ", but the mix of jobs has shifted more than usual. " if qty_out else ". ")
            + f'And <a href="#binoculars" data-view="valley">{degrees:.0f}% of new degrees</a> are in fields that lead to the jobs most exposed to AI.')

    meaning = [
        f"Use: AI use already covers tasks worth {wages}% of US pay, but most of it comes from a few hundred tasks.",
        ("Jobs: " + ("AI hasn't shown up in pay. " if not pay_out else "Pay has changed more than usual. ")
         + ("The mix of jobs has shifted more than usual, though chance can't yet be ruled out, " if qty_out and odds and odds < 20 else
            "The mix of jobs has shifted, " if qty_out else "The mix of jobs is within its usual range, ")
         + ("and job ads moved away from tasks AI can do before ChatGPT came out." if fell_before else
            "and job ads show no change at ChatGPT's release.")),
        ("Training: Students haven't turned away from exposed fields. "
         + ("Young workers losing ground in exposed jobs is the clearest signal on the page." if gtest is not None and as_large == 0 else
            "Young workers have lost ground in exposed jobs since 2022.")),
    ]
    notes = [f"the next BLS wage tables are due in spring {int(pay['year']) + 2}"]

    # the page reads as prose: lists inside a line are separated by semicolons, never by middle dots
    for view in views.values():
        for key in ("capline", "mark"):
            view[key] = view[key].replace(" · ", "; ")
        for entry in view["items"]:
            entry["src"] = entry["src"].replace(" · ", "; ")

    readings = {
        "built": datetime.now(timezone.utc).strftime("%-d %B %Y"),
        "lede": lede,
        "meaning": meaning,
        "notes": notes,
        "views": views,
        "releases": [{"date": str(r), "reach": round(float(x), 3), "published_use": round(float(p), 3)}
                 for r, x, p in zip(anthropic["release"], anthropic["reach_share"], anthropic["published_use"])],
    }
    out = config.REPO_ROOT / "site" / "data" / "readings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(readings, indent=2, ensure_ascii=False))
    site_static.write(readings=out)
    return out


if __name__ == "__main__":
    main()
