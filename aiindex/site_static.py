"""Writes the build's readings into the page itself, so the page reads without its script.

The page fetches site/data/readings.json when it loads. A reader without the
script, or a plain fetch of the page, gets the copy written here instead: the
readings embedded as JSON, the opening sentence with the three headline
findings, each view's method beside its sources, the research list, and the date in the footer, all written into the page
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
LIT = re.compile(r'(<div id="lit">)(.*?)(</div>)', re.S)
UPDATED = re.compile(r'(<span id="updated">)(.*?)(</span>)', re.S)
HOW = re.compile(r'(<div data-key="\w+" data-view="(\w+)"><h4>[^<]*</h4><p class="how">)(.*?)(</p>)', re.S)


def linkify(text: str, links: list[dict]) -> str:
    """Link each named study in escaped text, the same way the page does for the cards."""
    for link in links:
        text = re.sub(link["pattern"], lambda m: f'<a href="{escape(link["url"])}">{m.group(0)}</a>', text)
    return text


def _literature(themes: list[dict]) -> str:
    """The research list as plain HTML: a heading per theme and one line per study, linked."""
    out = []
    for theme in themes:
        items = "".join(f'<li><a href="{escape(st["url"])}">{escape(st["cite"])}</a>. {escape(st["text"])}</li>' for st in theme["studies"])
        out.append(f"<h4>{escape(theme['theme'])}</h4><ul>{items}</ul>")
    return "".join(out)


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
    html, n = HOW.subn(lambda m: m.group(1) + linkify(escape(views[m.group(2)]["how"]), data.get("links", [])) + m.group(4), html)
    if n != len(views):
        raise ValueError(f"the page has {n} method paragraphs for {len(views)} views")
    html, n = LIT.subn(lambda m: m.group(1) + _literature(data.get("literature", [])) + m.group(3), html, count=1)
    if n != 1:
        raise ValueError("the page has no research list to write into")
    html, n = UPDATED.subn(lambda m: m.group(1) + escape(data["built"]) + m.group(3), html, count=1)
    if n != 1:
        raise ValueError("the page has no footer date to write into")
    page.write_text(html)


if __name__ == "__main__":
    write()
