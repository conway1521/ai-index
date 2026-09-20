import numpy as np
import pandas as pd

from aiindex import config, pipeline, spine


def test_field_exposure_and_enrolment_split():
    pairs = spine.cip_to_soc(config.FIXTURE_DIR / "cip_2020_soc_2018.csv")
    socs = sorted(set(pairs["soc_code"]))
    rng = np.random.default_rng(2)
    measures = pd.DataFrame({"eloundou_beta": rng.uniform(0, 1, len(socs))}, index=pd.Index(socs, name="soc_code"))
    employment = pd.Series(rng.integers(1000, 100000, len(socs)).astype(float), index=socs)
    fx = pipeline.field_exposure_from_crosswalk(measures, employment, pairs)
    assert fx["eloundou_beta"].between(0, 1).all()
    nsc = pd.read_csv(config.FIXTURE_DIR / "nsc_major_field_fixture.csv")
    # give every two-digit family a score so the fixture's fields resolve
    fx2 = pd.DataFrame({"cip_code": [f"{c}.0101" for c in sorted({v[0] for v in pipeline.NSC_FIELD_TO_CIP2.values()})]})
    fx2["eloundou_beta"] = rng.uniform(0, 1, len(fx2))
    out = pipeline.enrolment_by_exposure(nsc, fx2, "eloundou_beta")
    assert set(out["term"]) == {"Spring 2025", "Spring 2026"}
    assert out["share_exposed"].between(0, 1).all()
