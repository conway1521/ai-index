from pathlib import Path

import numpy as np
import pandas as pd

from aiindex import config, cps

LAYOUT = config.RAW_DIR / "cps" / "layouts" / "2025_Basic_CPS_Public_Use_Record_Layout_plus_IO_Code_list.txt"
LAYOUT_TEXT = LAYOUT.read_text(errors="replace") if LAYOUT.exists() else """
HRMONTH			 2		MONTH OF INTERVIEW									16-17
HRYEAR4			 4		YEAR OF INTERVIEW									18-21
HRMIS			2		MONTH-IN-SAMPLE										63 - 64
GESTFIPS		2		FEDERAL INFORMATION 									93 - 94
PRTAGE			2		PERSONS AGE  										122 - 123
PEMLR			2		MONTHLY LABOR FORCE RECODE								180 - 181
PWSSWGT			10		FINAL WEIGHT (4 IMPLIED DECIMALS)						613 - 622
PWCMPWGT		10		COMPOSITED FINAL WEIGHT.  (4 IMPLIED DECIMALS)				846 - 855
PTIO1OCD		4		OCCUPATION CODE FOR PRIMARY JOB							860 - 863
"""


def _month(positions, year, month, n, rng, codes):
    width = max(e for _, e in positions.values())
    lines = []
    for _ in range(n):
        rec = bytearray(b" " * width)

        def put(name, value):
            s, e = positions[name]
            rec[s - 1:e] = str(value).rjust(e - s + 1)[: e - s + 1].encode()

        put("HRYEAR4", year); put("HRMONTH", month); put("HRMIS", rng.integers(1, 9))
        put("PRTAGE", int(rng.integers(16, 80)))
        employed = rng.random() < 0.6
        put("PEMLR", 1 if employed else 7)
        put("PEIO1OCD", int(rng.choice(codes)) if employed else -1)
        put("GESTFIPS", 6)
        w = int(rng.integers(5000, 30000)) * 10000
        put("PWCMPWGT", w); put("PWSSWGT", w)
        lines.append(bytes(rec))
    return b"\n".join(lines) + b"\n"


def test_layout_parses_and_aliases_the_2026_occupation_name():
    positions = cps.parse_layout(LAYOUT_TEXT)
    assert positions["PEIO1OCD"] == (860, 863)
    assert positions["PWCMPWGT"] == (846, 855)


def test_reader_cells_and_gauge_on_synthetic_month(tmp_path: Path):
    rng = np.random.default_rng(11)
    positions = cps.parse_layout(LAYOUT_TEXT)
    codes = [10, 20, 1005, 1010, 1021, 2310, 4110, 4700, 5120, 5240]
    for i, (y, m) in enumerate([(2025, 1), (2025, 2), (2025, 3)]):
        (tmp_path / f"m{i}pub.dat").write_bytes(_month(positions, y, m, 2000, rng, codes))
    persons = pd.concat([cps.read_month(p, positions) for p in sorted(tmp_path.glob("*.dat"))])
    assert set(persons["HRMONTH"]) == {1, 2, 3}
    assert (persons["weight"] > 0).all()
    scored = pd.Series(np.linspace(0, 1, len(codes)), index=codes)
    tercile = cps._tercile_of(scored, pd.Series(1.0, index=codes))
    cells = cps.monthly_cells(persons, tercile)
    assert set(cells["age_group"]) == {"young", "prime"}
    gauge = cps.gauge(cells, base=("2025-01", "2025-03"), pooling=2)
    assert len(gauge) == 2 and (gauge["young_relative_to_prime"] > 0).all()
