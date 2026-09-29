"""Put the files of a data release where the build reads them.

The inputs that the publishers will not serve to a script are attached to
dated releases of the paper repository, and each release has a manifest in
that repository's data/raw recording every file's asset id, size, sha256,
source and licence. This module fetches each file through the paper's
release reader, which refuses a file whose hash differs from the manifest,
and links it under aiindex/data/raw at the name the loaders expect, removing
the sidecar of any copy it replaces so that the next build grades the file
as the publisher's release.

Run as:  python -m aiindex.place_release

GITHUB_TOKEN must carry read access to the paper repository when the files
are not already on disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import config

sys.path.insert(0, str(config.PAPER_ROOT))
from src import release  # noqa: E402

RAW = config.RAW_DIR
MAIN, CPS_A, CPS_B = "data-2026-10-01", "data-2026-10-01-addendum", "data-2026-10-01-addendum2"

# release file -> where the index reads it; a None target keeps the file out of the index
PLACES = {
    MAIN: {
        "national_M2025_dl.xlsx": "oews/national_M2025_dl.xlsx",
        "state_M2025_dl.xlsx": "oews/state_M2025_dl.xlsx",
        "aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv": "aei/release_2026_03_24/aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv",
        "aei_claude_ai_2026-06-26.csv": "aei/release_2026_06_26/aei_claude_ai_2026-06-26.csv",
        "job_exposure.csv": "aei_labor_market/job_exposure.csv",
        "task_penetration.csv": "aei_labor_market/task_penetration.csv",
        "usa_share_of_work_related_messages_by_onet_iwa_month.csv": "openai/usa_share_of_work_related_messages_by_onet_iwa_month.csv",
        "usa_share_of_messages_by_onet_iwa_month.csv": "openai/usa_share_of_messages_by_onet_iwa_month.csv",
        "State.xlsx": "btos/State.xlsx", "National.xlsx": "btos/National.xlsx", "Sector.xlsx": "btos/Sector.xlsx",
        "c2023_a_RV.csv": "ipeds/C2023_A.csv", "c2024_a_rv.csv": "ipeds/C2024_A.csv", "c2025_a.csv": "ipeds/C2025_A.csv",
        "hd2023.csv": "ipeds/HD2023.csv", "hd2024.csv": "ipeds/HD2024.csv", "hd2025.csv": "ipeds/HD2025.csv",
        "CIP2020_SOC2018_Crosswalk.xlsx": "crosswalks/cip_2020_soc_2018.xlsx",
        "2018-occupation-code-list-and-crosswalk.xlsx": "crosswalks/census_2018_occupation_crosswalk.xlsx",
        "2019_to_SOC_Crosswalk.csv": "crosswalks/onetsoc_2019_to_soc_2018.csv",
        "oes_2019_hybrid_structure.xlsx": "crosswalks/oews_hybrid_2019_2020.xlsx",
        "psam_pusa_2024.csv": "acs/psam_pusa_2024.csv", "psam_pusb_2024.csv": "acs/psam_pusb_2024.csv",
        "job_tasks_Occ8.tsv": "nlx/job_tasks_Occ8.tsv", "job_info_Occ8.tsv": "nlx/job_info_Occ8.tsv",
        "job_tasks.tsv": "nlx/job_tasks.tsv", "job_info.tsv": "nlx/job_info.tsv", "job_info_State.tsv": "nlx/job_info_State.tsv",
    },
    CPS_B: {"CTEEFall2024-CIPGroupEnrollment-UG4yr.xlsx": "nsc/CTEEFall2024-CIPGroupEnrollment-UG4yr.xlsx"},
}
# copies the release supersedes, removed with their sidecars
SUPERSEDED = ["oews/oesm25nat.zip", "onet/onet_db_30_2_text.zip", "acs/psam_p27_2022_1yr.csv",
              "aei/release_2026_06_26/task_pct_2026-04.csv", "aei/release_2026_06_26/task_pct_2026-05.csv"]


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    for stale in (target, target.with_suffix(target.suffix + ".source")):
        if stale.is_symlink() or stale.exists():
            stale.unlink()
    target.symlink_to(source.resolve())


def main() -> None:
    for relative in SUPERSEDED:
        for stale in (RAW / relative, RAW / (relative + ".source")):
            if stale.is_symlink() or stale.exists():
                stale.unlink()
    placed = 0
    for tag, files in PLACES.items():
        for name, relative in files.items():
            _link(release.path(name, tag), RAW / relative)
            placed += 1
    # every CPS month in both CPS releases
    for tag in (CPS_A, CPS_B):
        for name in release.manifest(tag)["files"]:
            if name.endswith("pub.csv"):
                _link(release.path(name, tag), RAW / "cps" / name)
                placed += 1
    # O*NET 30.3 is assembled from its loose text files by the paper's reader
    onet_zip = RAW / "onet" / "onet_db_30_3_text.zip"
    if not onet_zip.exists():
        release.assemble_onet(onet_zip, "db_30_3_text/", MAIN)
        placed += 1
    print(f"placed {placed} files under {RAW}")


if __name__ == "__main__":
    main()
