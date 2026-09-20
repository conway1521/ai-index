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
