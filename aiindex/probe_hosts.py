"""Ask every publisher whether it will serve this machine.

The build fetches from official hosts first and falls back to committed
copies. Which of those two paths it takes depends entirely on where it is
running: BLS refuses requests from some networks outright, and the Census
Bureau, NCES and Hugging Face are unreachable from others. That is a fact
about the network, not about the code, so it is worth measuring rather
than assuming.

This module asks each host for the first few kilobytes of a real file and
records what came back: the status, the bytes, the time, and whether the
payload looks like the file it should be rather than an error page. Run it
anywhere the build might run.

    python -m aiindex.probe_hosts
    python -m aiindex.probe_hosts --markdown > reachability.md
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict

# One real file per publisher, chosen so the answer is about the host and
# not about one unlucky path. Each carries the first bytes its format must
# begin with, so a login wall or an error page served with status 200 is
# caught rather than counted as a success.
TARGETS = [
    ("BLS OEWS national", "https://www.bls.gov/oes/special-requests/oesm24nat.zip", b"PK", "wage bill"),
    ("BLS OEWS state", "https://www.bls.gov/oes/special-requests/oesm24st.zip", b"PK", "wage bill, by state"),
    ("BLS front page", "https://www.bls.gov/", b"<", "does BLS answer at all"),
    ("Census CPS monthly", "https://www2.census.gov/programs-surveys/cps/datasets/2025/basic/jan25pub.zip", b"PK", "young-worker gauge"),
    ("Census BTOS", "https://www.census.gov/hfp/btos/data_downloads", b"<", "firm adoption"),
    ("Census ACS PUMS", "https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_pus.zip", b"PK", "field of degree to occupation"),
    ("Census occupation crosswalk", "https://www2.census.gov/programs-surveys/demo/guidance/industry-occupation/2018-occupation-code-list-and-crosswalk.xlsx", b"PK", "CPS occupation codes to SOC"),
    ("O*NET database", "https://www.onetcenter.org/dl_files/database/db_30_3_text.zip", b"PK", "tasks, ratings and skills"),
    ("NCES IPEDS completions", "https://nces.ed.gov/ipeds/datacenter/data/C2024_A.zip", b"PK", "awards by field"),
    ("NCES CIP to SOC", "https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx", b"PK", "field to occupation, declared"),
    ("Hugging Face AEI", "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/labor_market_impacts/job_exposure.csv", b"", "usage and observed exposure"),
    ("OpenAI Signals", "https://openai.com/signals/data-download/", b"<", "usage by work activity"),
    ("Clearinghouse", "https://nscresearchcenter.org/current-term-enrollment-estimates/", b"<", "enrolment by field"),
    ("National Weather Service", "https://api.weather.gov/stations/KSFO/observations/latest", b"{", "the sky on the front page"),
    ("GitHub raw", "https://raw.githubusercontent.com/hiring-lab/ai-tracker/main/README.md", b"#", "the committed copies, and the control"),
]

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
TIMEOUT = 30
PEEK = 2048


@dataclass
class Result:
    name: str
    url: str
    used_for: str
    status: int | None
    ok: bool
    bytes_seen: int
    seconds: float
    note: str

    @property
    def mark(self) -> str:
        return "yes" if self.ok else "no"


def probe(name: str, url: str, magic: bytes, used_for: str, user_agent: str = BROWSER_UA) -> Result:
    """Fetch the first bytes of one file and judge what came back."""
    request = urllib.request.Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "*/*",
        # Most hosts honour this and send only the opening bytes; the ones
        # that ignore it send the whole file, which the read below cuts off.
        "Range": f"bytes=0-{PEEK - 1}",
    })
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            payload = response.read(PEEK)
            status = response.status
        elapsed = time.time() - started
        if magic and not payload.startswith(magic):
            looks_like = payload[:60].decode("utf-8", "replace").replace("\n", " ")
            return Result(name, url, used_for, status, False, len(payload), elapsed,
                          f"answered, but the payload is not the file: {looks_like!r}")
        return Result(name, url, used_for, status, True, len(payload), elapsed, "served")
    except urllib.error.HTTPError as error:
        elapsed = time.time() - started
        reason = {403: "refused this client", 404: "no file at that path",
                  429: "rate limited", 503: "unavailable"}.get(error.code, error.reason)
        return Result(name, url, used_for, error.code, False, 0, elapsed, str(reason))
    except (urllib.error.URLError, socket.timeout, OSError) as error:
        elapsed = time.time() - started
        return Result(name, url, used_for, None, False, 0, elapsed,
                      f"no answer: {getattr(error, 'reason', error)}")


def run(user_agent: str = BROWSER_UA) -> list[Result]:
    return [probe(name, url, magic, used_for, user_agent) for name, url, magic, used_for in TARGETS]


def as_markdown(results: list[Result], user_agent: str) -> str:
    reachable = sum(r.ok for r in results)
    lines = [
        "# Host reachability",
        "",
        f"{reachable} of {len(results)} publishers served this machine. "
        "Where a publisher refuses, the build falls back to a committed copy "
        "and the manifest grades that input `mirror` rather than `real`.",
        "",
        "| Publisher | Served | Status | Time | What it feeds | Note |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.name} | {r.mark} | {r.status if r.status is not None else 'none'} | "
                     f"{r.seconds:.1f}s | {r.used_for} | {r.note} |")
    blocked = [r.name for r in results if not r.ok]
    lines += ["", f"Refusing: {', '.join(blocked) if blocked else 'none'}.", "",
              f"Identified as `{user_agent[:48]}...`."]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", action="store_true", help="write a table rather than lines")
    parser.add_argument("--json", action="store_true", help="write the raw results")
    parser.add_argument("--plain-agent", action="store_true",
                        help="identify as Python rather than as a browser, to separate a client block from an address block")
    args = parser.parse_args()

    user_agent = f"python-urllib/{sys.version_info.major}.{sys.version_info.minor}" if args.plain_agent else BROWSER_UA
    results = run(user_agent)

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    elif args.markdown:
        print(as_markdown(results, user_agent))
    else:
        for r in results:
            print(f"{r.mark:>3}  {str(r.status or '-'):>4}  {r.seconds:5.1f}s  {r.name:<28} {r.note}")
        print(f"\n{sum(r.ok for r in results)} of {len(results)} served this machine.")
    # The probe reports; it does not fail a build. A publisher refusing is a
    # fact to record, not an error to stop on.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
