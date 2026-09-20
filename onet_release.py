"""Point the paper's O*NET reader at the release the index has in hand.

``src.onet`` pins release 30.3 and reads it from a zip in the paper's
``data/raw``. Release 30.3 split the Skills domain into two files; earlier
releases carry one. This module lets the index run on whichever release
zip sits in ``aiindex/data/raw/onet/``, rewrites the file names the reader
expects to the names that release uses, and records the release and its
provenance in the manifest. The descriptor set is the same 161 elements
either way, so gamma and the bundles are unchanged in meaning; the vintage
is recorded so that a rerun on 30.3 can be compared.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

from . import config
from .manifest import MANIFEST

sys.path.insert(0, str(config.REPO_ROOT))
from src import onet  # noqa: E402

ONET_DIR = config.RAW_DIR / "onet"
OFFICIAL = "https://www.onetcenter.org/dl_files/database/db_{release}_text.zip"

SINGLE_SKILLS = {
    "skill": ["Skills.txt"],
}
SINGLE_SKILLS_CROSSWALK = {
    "skill": ["Skills to Work Activities.txt"],
}


# Release 30.3 renamed the work-activity crosswalk columns and merged the
# DWA and IWA reference files into one. Earlier releases are translated to
# the 30.3 names so that src.onet reads them unchanged.
PRE_30_3_RENAMES = {
    "Tasks to DWAs.txt": {"DWA ID": "DWA Element ID"},
}


def _translating_reader(names: set[str]):
    native = onet._read_file_native

    def read_file(filename: str):
        if filename == "GWAs to IWAs to DWAs.txt" and onet.MEMBER_PREFIX + filename not in names:
            dwa = native("DWA Reference.txt")
            return dwa.rename(columns={"Element ID": "GWA Element ID", "IWA ID": "IWA Element ID",
                                       "DWA ID": "DWA Element ID", "DWA Title": "DWA Element Name"})
        frame = native(filename)
        return frame.rename(columns=PRE_30_3_RENAMES.get(filename, {}))

    return read_file


def available() -> Path | None:
    ONET_DIR.mkdir(parents=True, exist_ok=True)
    zips = sorted(ONET_DIR.glob("onet_db_*_text.zip"))
    return zips[-1] if zips else None


def activate() -> str:
    """Configure src.onet for the release on disk and return its label."""
    path = available()
    if path is None:
        raise FileNotFoundError(f"no O*NET release zip in {ONET_DIR}; expected onet_db_<release>_text.zip")
    release = re.search(r"onet_db_(\d+_\d+)_text", path.name).group(1)
    onet.ONET_RELEASE = release
    onet.ZIP_PATH = path
    onet.MEMBER_PREFIX = f"db_{release}_text/"
    onet.SOURCE_URL = OFFICIAL.format(release=release)

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    if onet.MEMBER_PREFIX + "Essential Skills.txt" not in names:
        onet.DESCRIPTOR_FILES = {**onet.DESCRIPTOR_FILES, **SINGLE_SKILLS}
        onet.CROSSWALK_FILES = {**onet.CROSSWALK_FILES, **SINGLE_SKILLS_CROSSWALK}

    if not hasattr(onet, "_read_file_native"):
        onet._read_file_native = onet.read_file
    onet.read_file = _translating_reader(names)

    sidecar = path.with_suffix(path.suffix + ".source")
    grade, source = ("real", onet.SOURCE_URL)
    if sidecar.exists():
        grade, source = sidecar.read_text().split("\n")[:2]
    MANIFEST.record("onet_release", path, official_url=onet.SOURCE_URL, grade=grade,
                    source_url=source, notes=f"O*NET release {release.replace('_', '.')}")
    return release.replace("_", ".")


def ensure() -> Path:
    """Assemble the release zip from the mirrored text files when no zip is on disk."""
    from . import fetch, sources

    path = available()
    if path is not None:
        return path
    ONET_DIR.mkdir(parents=True, exist_ok=True)
    release = sources.ONET_RELEASE
    target = ONET_DIR / f"onet_db_{release}_text.zip"
    official = OFFICIAL.format(release=release)
    if fetch._download(official, target):
        target.with_suffix(".zip.source").write_text(f"real\n{official}")
        return target
    import urllib.parse
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sources.ONET_FILES:
            url = f"{sources.ONET_FILES_BASE}/{urllib.parse.quote(name)}"
            member = ONET_DIR / "parts" / name
            if not fetch._download(url, member):
                target.unlink(missing_ok=True)
                raise ConnectionError(f"could not fetch {url}")
            archive.write(member, f"db_{release}_text/{name}")
    target.with_suffix(".zip.source").write_text(f"mirror\n{sources.ONET_FILES_BASE}/")
    return target
