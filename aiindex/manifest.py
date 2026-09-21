"""Record where every input file came from and whether it was the real one.

A number in an index table is traceable to a file, and the file to a URL,
a byte count, a hash and a time. The grade says whether the file is the
publisher's release ("real"), a copy of it served from somewhere else
("mirror", with the mirror URL recorded beside the official one), or a
fixture built for the tests because the publisher's host was unreachable
("fixture"). A fixture never reaches a published table without the grade
travelling with it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config

GRADES = ("real", "mirror", "fixture")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Manifest:
    """One manifest per build, written at the end, appended to as files load."""

    def __init__(self, path: Path = config.MANIFEST_PATH) -> None:
        self.path = path
        self.entries: dict[str, dict] = {}

    def record(self, name: str, path: Path, *, official_url: str,
               grade: str, source_url: str | None = None,
               notes: str = "") -> dict:
        if grade not in GRADES:
            raise ValueError(f"grade must be one of {GRADES}, got {grade!r}")
        path = Path(path)
        entry = {
            "path": str(path.relative_to(config.REPO_ROOT)) if path.is_relative_to(config.REPO_ROOT) else str(path),
            "official_url": official_url,
            "source_url": source_url or (official_url if grade == "real" else None),
            "grade": grade,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notes": notes,
        }
        self.entries[name] = entry
        return entry

    def grades(self) -> dict[str, str]:
        return {name: entry["grade"] for name, entry in self.entries.items()}

    def write(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "files": self.entries}
        self.path.write_text(json.dumps(payload, indent=2))
        return self.path


MANIFEST = Manifest()
