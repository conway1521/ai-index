"""Writes the build's readings into the page itself, so the page reads without its script.

The page fetches site/data/readings.json when it loads. A reader without the
script, or a plain fetch of the page, gets the copy written here instead: the
readings embedded as JSON, the opening sentence with the three headline
findings, each view's method beside its sources, and the date in the footer, all written into the page
as text. Run by export_site after it writes the
readings, and runnable on its own as python -m aiindex.site_static.
"""

from __future__ import annotations

import json
import re
from html import escape

from . import config

PAGE = config.REPO_ROOT / "site" / "index.html"
READINGS = config.REPO_ROOT / "site" / "data" / "readings.json"
OPEN_JSON = '<script type="application/json" id="readings">'
LEDE = re.compile(r'(<p class="lede" id="lede">)(.*?)(</p>)', re.S)
UPDATED = re.compile(r'(<span id="updated">)(.*?)(</span>)', re.S)
HOW = re.compile(r'(<div data-key="\w+" data-view="(\w+)"><h4>[^<]*</h4><p class="how">)(.*?)(</p>)', re.S)


def write(page=PAGE, readings=READINGS) -> None:
    text = readings.read_text()
    data = json.loads(text)
    lede, views = data["lede"], data["views"]
    html = page.read_text()
    start = html.index(OPEN_JSON) + len(OPEN_JSON)
    end = html.index("</script>", start)
    html = html[:start] + text.replace("</", "<\\/") + html[end:]
    html, n = LEDE.subn(lambda m: m.group(1) + lede + m.group(3), html, count=1)
    if n != 1:
        raise ValueError("the page has no lede paragraph to write into")
    html, n = HOW.subn(lambda m: m.group(1) + escape(views[m.group(2)]["how"]) + m.group(4), html)
    if n != len(views):
        raise ValueError(f"the page has {n} method paragraphs for {len(views)} views")
    html, n = UPDATED.subn(lambda m: m.group(1) + escape(data["built"]) + m.group(3), html, count=1)
    if n != 1:
        raise ValueError("the page has no footer date to write into")
    page.write_text(html)


if __name__ == "__main__":
    write()
