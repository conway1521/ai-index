"""Get an input file into data/raw, from the official host or a mirror.

The official URL is always the first attempt. A mirror is tried only when
the official host refuses, and the manifest records both. When nothing is
reachable and a fixture exists, the fixture is used and graded as such. The
grade is what separates a build that ran on the publisher's numbers from
one that ran on a stand-in, and the build report reads it back.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from . import config
from .manifest import MANIFEST

TIMEOUT = 300


def _download(url: str, target: Path, attempts: int = 3) -> bool:
    """Stream the file to disk, retrying a transfer that is cut off part way."""
    import http.client
    import shutil
    import tempfile

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                expected = response.headers.get("Content-Length")
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                    shutil.copyfileobj(response, handle, length=1 << 20)
                    temp = Path(handle.name)
            if temp.stat().st_size == 0 or (expected and temp.stat().st_size != int(expected)):
                temp.unlink(missing_ok=True)
                continue
            temp.replace(target)
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, http.client.IncompleteRead, OSError):
            continue
    return False


def get(name: str, filename: str, official_url: str, *,
        mirrors: tuple[str, ...] = (), fixture: str | None = None,
        notes: str = "", refresh: bool = False) -> tuple[Path, str]:
    """Return the local path and its grade, recording both in the manifest.

    A file already in data/raw is reused without a network call and graded
    by a sidecar written when it was fetched, so a build is repeatable
    offline once the inputs are in place.
    """
    target = config.RAW_DIR / filename
    sidecar = target.with_suffix(target.suffix + ".source")

    if target.exists() and not refresh and sidecar.exists():
        grade, source_url = sidecar.read_text().split("\n")[:2]
        MANIFEST.record(name, target, official_url=official_url, grade=grade,
                        source_url=source_url or None, notes=notes)
        return target, grade

    if _download(official_url, target):
        sidecar.write_text(f"real\n{official_url}")
        MANIFEST.record(name, target, official_url=official_url, grade="real", notes=notes)
        return target, "real"

    for mirror in mirrors:
        if _download(mirror, target):
            sidecar.write_text(f"mirror\n{mirror}")
            MANIFEST.record(name, target, official_url=official_url, grade="mirror",
                            source_url=mirror, notes=notes)
            return target, "mirror"

    if fixture is not None:
        path = config.FIXTURE_DIR / fixture
        if not path.exists():
            raise FileNotFoundError(f"neither {official_url} nor a mirror is reachable, "
                                    f"and the fixture {path} does not exist")
        MANIFEST.record(name, path, official_url=official_url, grade="fixture",
                        source_url=str(path), notes=notes)
        return path, "fixture"

    raise ConnectionError(f"{official_url} unreachable and no mirror or fixture given")
