"""Every input file the index reads: its official URL and the copies that serve it.

The official host is always tried first. BLS, the Census Bureau, NCES and
O*NET all refuse automated requests from some networks, and the copies
listed here are files that other researchers committed to public GitHub
repositories, checked against the official layout, row counts and, where
a second copy existed, byte identity. A build records which copy it used;
the file names and the grade travel into the manifest, and a rerun on a
network that reaches the official host replaces the copy with the release.
"""

from __future__ import annotations

RAW = "https://raw.githubusercontent.com"
LFS = "https://media.githubusercontent.com/media"

# OEWS national files: BLS name, official URL, mirrors. State 2025 is not yet
# mirrored anywhere and national 2013, 2014, 2017 and 2018 were not found.
OEWS_NATIONAL = {
    2025: ("oesm25nat.zip", "https://www.bls.gov/oes/special-requests/oesm25nat.zip",
           (f"{RAW}/arieldklein/ai-employment-paper/main/data_raw/bls/oesm25nat.zip",)),
    2024: ("national_M2024_dl.xlsx", "https://www.bls.gov/oes/special-requests/oesm24nat.zip",
           (f"{RAW}/germanr/occ-exposure/main/rawdata/bls/national_M2024_dl.xlsx",
            f"{RAW}/victoriano/future-of-work-data/main/data/raw/OEWS/national_M2024_dl.xlsx")),
    2023: ("national_M2023_dl.xlsx", "https://www.bls.gov/oes/special-requests/oesm23nat.zip",
           (f"{RAW}/augw999/ai-labor-market-impact_analysis/main/national_M2023_dl.xlsx",)),
    2022: ("national_M2022_dl.xlsx", "https://www.bls.gov/oes/special-requests/oesm22nat.zip",
           (f"{RAW}/augw999/ai-labor-market-impact_analysis/main/national_M2022_dl.xlsx",)),
    2021: ("national_M2021_dl.xlsx", "https://www.bls.gov/oes/special-requests/oesm21nat.zip",
           (f"{RAW}/augw999/ai-labor-market-impact_analysis/main/national_M2021_dl.xlsx",)),
    2019: ("national_M2019_dl.xlsx", "https://www.bls.gov/oes/special-requests/oesm19nat.zip",
           (f"{RAW}/burnssa/ai-labor-research/master/data/oes/oesm19nat/national_M2019_dl.xlsx",)),
}

OEWS_STATE = {
    year: (f"state_M{year}_dl.xlsx", f"https://www.bls.gov/oes/special-requests/oesm{year % 100:02d}st.zip",
           (f"{RAW}/Soorej30/wage_analysis/main/data/oesm{year % 100:02d}st/state_M{year}_dl.xlsx",))
    for year in range(2020, 2025)
}
OEWS_STATE.update({
    year: (f"state_M{year}_dl.xlsx", f"https://www.bls.gov/oes/special-requests/oesm{year % 100:02d}st.zip",
           (f"{RAW}/KHALEDRABBAH/US-Unemployment-Dashboard/main/Data/state_M{year}_dl.xlsx",))
    for year in range(2012, 2020)
})

ONET_FILES_BASE = f"{RAW}/pythonski/bottlenecks/master/db_30_2_text"
ONET_RELEASE = "30_2"
ONET_FILES = [
    "Abilities to Work Activities.txt", "Abilities.txt", "Content Model Reference.txt",
    "DWA Reference.txt", "IWA Reference.txt", "Job Zones.txt", "Knowledge.txt",
    "Occupation Data.txt", "Read Me.txt", "Scales Reference.txt", "Skills to Work Activities.txt",
    "Skills.txt", "Task Ratings.txt", "Task Statements.txt", "Tasks to DWAs.txt",
    "Work Activities.txt",
]

BTOS = {
    "State.xlsx": ("https://www.census.gov/hfp/btos/data_downloads",
                   (f"{RAW}/EIG-Research/ai-btos/main/data/raw/20251208/State.xlsx",)),
    "National.xlsx": ("https://www.census.gov/hfp/btos/data_downloads",
                      (f"{RAW}/EIG-Research/ai-btos/main/data/raw/20251208/National.xlsx",)),
    "Sector.xlsx": ("https://www.census.gov/hfp/btos/data_downloads",
                    (f"{RAW}/EIG-Research/ai-btos/main/data/raw/20251208/Sector.xlsx",)),
}

CIP_SOC = ("https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx",
           (f"{RAW}/lrussell-research/CIP-NAICS-Crosswalk/main/CIP2020_SOC2018_Crosswalk.xlsx",))

IPEDS = {
    "C2024_A.csv": ("https://nces.ed.gov/ipeds/datacenter/data/C2024_A.zip",
                    (f"{LFS}/arijacob/chicago_majors/main/data/ipeds/raw/major_numbers/C2024_A/c2024_a_RV.csv",)),
    "C2023_A.csv": ("https://nces.ed.gov/ipeds/datacenter/data/C2023_A.zip",
                    (f"{LFS}/arijacob/chicago_majors/main/data/ipeds/raw/major_numbers/c2023_a/c2023_a.csv",)),
    "HD2023.csv": ("https://nces.ed.gov/ipeds/datacenter/data/HD2023.zip",
                   (f"{LFS}/ftrain/ipeds2/main/sources/IPEDS202324_csv/HD2023.csv",)),
}

# One state's ACS one-year person file, used to test the field-of-degree link
# before the full national extract is in hand.
ACS_PUMS_TEST = ("https://www2.census.gov/programs-surveys/acs/data/pums/2022/1-Year/csv_pmn.zip",
                 (f"{LFS}/beeckcenter/climate-equity-workforce/main/raw_data/Minnesota%20-%20ACS%20PUMS%20-%20One-Year/psam_p27.csv",))

INDEED = ("https://raw.githubusercontent.com/hiring-lab/ai-tracker/main/AI_posting.csv", ())

# Anthropic Economic Index. The Hugging Face dataset is the source; the
# copies are committed by other researchers, and the ones marked verified
# match the sha256 that Hugging Face records for the file.
AEI_OFFICIAL = "https://huggingface.co/datasets/Anthropic/EconomicIndex"
AEI_FILES = {
    # path under data/raw/aei : (official path on Hugging Face, mirrors, note)
    "release_2025_09_15/aei_raw_claude_ai_2025-08-04_to_2025-08-11.csv": (
        f"{AEI_OFFICIAL}/resolve/main/release_2025_09_15/data/intermediate/aei_raw_claude_ai_2025-08-04_to_2025-08-11.csv",
        (f"{RAW}/IlanStrauss/anthropic-econ-critique/main/data/anthropic/release_2025_09_15/data/intermediate/aei_raw_claude_ai_2025-08-04_to_2025-08-11.csv",
         f"{LFS}/tkc88888888/EconomicIndex/main/release_2025_09_15/data/intermediate/aei_raw_claude_ai_2025-08-04_to_2025-08-11.csv"),
        "sha256 matches the Hugging Face pointer"),
    "release_2025_09_15/onet_task_statements.csv": (
        f"{AEI_OFFICIAL}/resolve/main/release_2025_09_15/data/intermediate/onet_task_statements.csv",
        (f"{RAW}/dioandre3/UMICH-STAT507/main/Final%20Project/Final%20Project/aei_data/release_2025_09_15/data/intermediate/onet_task_statements.csv",
         f"{LFS}/tkc88888888/EconomicIndex/main/release_2025_09_15/data/intermediate/onet_task_statements.csv"),
        "sha256 matches the Hugging Face pointer; the task list the release classified against"),
    "release_2026_01_15/aei_raw_claude_ai_2025-11-13_to_2025-11-20.csv": (
        f"{AEI_OFFICIAL}/resolve/main/release_2026_01_15/data/intermediate/aei_raw_claude_ai_2025-11-13_to_2025-11-20.csv",
        (f"{RAW}/IlanStrauss/anthropic-econ-critique/main/data/anthropic/release_2026_01_15/data/intermediate/aei_raw_claude_ai_2025-11-13_to_2025-11-20.csv",
         f"{LFS}/tkc88888888/EconomicIndex/main/release_2026_01_15/data/intermediate/aei_raw_claude_ai_2025-11-13_to_2025-11-20.csv"),
        "sha256 matches the Hugging Face pointer"),
    "release_2026_03_24/aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv": (
        f"{AEI_OFFICIAL}/resolve/main/release_2026_03_24/data/intermediate/aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv",
        (f"{LFS}/Engineering-AI-Systems-Team-3/chatgpt-at-work/main/data/input/aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv",
         f"{RAW}/dioandre3/UMICH-STAT507/main/Final%20Project/Final%20Project/aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv"),
        "Anthropic republished this file; the copy is one of the earlier versions and is not hash-verified against the current one"),
    "release_2026_06_26/task_pct_2026-04.csv": (
        f"{AEI_OFFICIAL}/resolve/main/release_2026_06_26/data/aei_claude_ai_2026-06-26.csv",
        (f"{RAW}/theodorewright11/ai-workforce-exposure-dataset-construction-public/main/data/task_pct_v6_1.csv",),
        "a third party's slice of the 219 MB monthly file: global claude_ai task shares for April 2026, task text only"),
    "release_2026_06_26/task_pct_2026-05.csv": (
        f"{AEI_OFFICIAL}/resolve/main/release_2026_06_26/data/aei_claude_ai_2026-06-26.csv",
        (f"{RAW}/theodorewright11/ai-workforce-exposure-dataset-construction-public/main/data/task_pct_v6_2.csv",),
        "a third party's slice of the 219 MB monthly file: global claude_ai task shares for May 2026, task text only"),
}
AEI_LABOR_MARKET = {
    "job_exposure.csv": (f"{AEI_OFFICIAL}/resolve/main/labor_market_impacts/job_exposure.csv",
                         (f"{RAW}/tkc88888888/EconomicIndex/main/labor_market_impacts/job_exposure.csv",),
                         "sha256 matches the Hugging Face file; observed exposure by six-digit SOC 2018"),
    "task_penetration.csv": (f"{AEI_OFFICIAL}/resolve/main/labor_market_impacts/task_penetration.csv",
                             (f"{RAW}/tkc88888888/EconomicIndex/main/labor_market_impacts/task_penetration.csv",),
                             "sha256 matches the Hugging Face file; penetration by task text"),
}

# OpenAI Signals v2.0, July 2024 to June 2026, by intermediate work activity.
OPENAI_OFFICIAL = "https://openai.com/signals/data-download/"
OPENAI_FILES = {
    "usa_share_of_work_related_messages_by_onet_iwa_month.csv": (
        OPENAI_OFFICIAL,
        (f"{RAW}/prashgarg/global-automation-atlas/main/outputs/source_data/openai_observed_use/usa_share_of_work_related_messages_by_onet_iwa_month.csv",),
        "v2.0 download as committed by a third party"),
    "usa_share_of_messages_by_onet_iwa_month.csv": (
        OPENAI_OFFICIAL,
        (f"{RAW}/prashgarg/global-automation-atlas/main/outputs/source_data/openai_observed_use/usa_share_of_messages_by_onet_iwa_month.csv",),
        "v2.0 download as committed by a third party"),
}
