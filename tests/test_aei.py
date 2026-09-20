import pandas as pd
import pytest

from aiindex import aei, onet_release


@pytest.mark.skipif(onet_release.available() is None, reason="no O*NET release on disk")
def test_long_table_joins_statements_to_task_ids(tmp_path):
    onet_release.activate()
    from src import onet
    tasks = onet.task_statements().head(40)
    rows = []
    for _, task in tasks.iterrows():
        for variable, value in (("onet_task_pct", 2.5), ("onet_task_automation_pct", 40.0),
                                ("onet_task_augmentation_pct", 55.0)):
            rows.append({"geo_id": "GLOBAL", "geography": "global", "date_start": "2026-05-01",
                         "date_end": "2026-05-31", "platform_and_product": "Claude AI (Free and Pro)",
                         "facet": "onet_task", "level": 0, "variable": variable,
                         "cluster_name": task["task_statement"], "value": value})
    rows.append({**rows[0], "cluster_name": "A statement that is not in O*NET", "value": 1.0})
    path = tmp_path / "release_2026_06_26" / "aei_claude_ai_2026-05.csv"
    path.parent.mkdir()
    pd.DataFrame(rows).to_csv(path, index=False)
    table = aei.read_release_file(path)
    assert table is not None and len(table) == 40
    assert set(table["task_id"]) == set(tasks["task_id"].astype(str))
    assert (table["automation_share"] == 0.4).all() and (table["augmentation_share"] == 0.55).all()
    assert table["release"].iloc[0].startswith("2026-06-26")


def test_task_table_shape_is_recognised(tmp_path):
    frame = pd.DataFrame({"onet_task_id": [8823, 8831], "usage_pct": [1.2, 0.8],
                          "automation_pct": [30.0, 60.0], "augmentation_pct": [65.0, 35.0]})
    path = tmp_path / "release_2025_03_27" / "onet_task_statements.csv"
    path.parent.mkdir()
    frame.to_csv(path, index=False)
    table = aei.read_release_file(path)
    assert list(table["task_id"]) == ["8823", "8831"]
    assert abs(table["automation_share"].iloc[1] - 0.6) < 1e-12
