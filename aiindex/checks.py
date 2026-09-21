"""Unit checks that every layer runs on its own tables before writing them.

Each check returns a row for the checks table and raises when the check
fails, so a build cannot write a table whose units are wrong. The rows are
kept even when a check passes, because a reader of the output should be
able to see what was verified and with what tolerance, not only that nothing
raised.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config

ROWS: list[dict] = []


class CheckFailed(AssertionError):
    pass


def _row(layer: str, check: str, ok: bool, detail: str, value: float | None = None) -> dict:
    row = {"layer": layer, "check": check, "ok": bool(ok), "value": value, "detail": detail}
    ROWS.append(row)
    if not ok:
        raise CheckFailed(f"[{layer}] {check}: {detail}")
    return row


def unique_key(frame: pd.DataFrame, keys: list[str], layer: str) -> dict:
    dupes = int(frame.duplicated(subset=keys).sum())
    return _row(layer, f"unique key {keys}", dupes == 0,
                f"{dupes} duplicate rows on {keys}", dupes)


def nonnegative(series: pd.Series, layer: str, name: str) -> dict:
    bad = int((series < 0).sum())
    return _row(layer, f"nonnegative {name}", bad == 0, f"{bad} negative values in {name}", bad)


def within(series: pd.Series, lo: float, hi: float, layer: str, name: str) -> dict:
    bad = int(((series < lo) | (series > hi)).sum())
    return _row(layer, f"{name} in [{lo}, {hi}]", bad == 0,
                f"{bad} values of {name} outside [{lo}, {hi}]", bad)


def shares_sum_to_one(frame: pd.DataFrame, by: list[str], share: str,
                      layer: str, tol: float = 1e-6) -> dict:
    totals = frame.groupby(by)[share].sum() if by else pd.Series([frame[share].sum()])
    worst = float((totals - 1.0).abs().max()) if len(totals) else 0.0
    return _row(layer, f"{share} sums to one within {by}", worst <= tol,
                f"largest deviation from one is {worst:.2e}", worst)


def close(actual: float, expected: float, rel: float, layer: str, name: str) -> dict:
    gap = abs(actual - expected) / abs(expected) if expected else abs(actual)
    return _row(layer, f"{name} within {rel:.0%} of expected", gap <= rel,
                f"actual {actual:,.6g} against expected {expected:,.6g}, gap {gap:.2%}", gap)


def bounded_by(part: pd.Series, whole: pd.Series, layer: str, name: str,
               tol: float = 1e-9) -> dict:
    aligned = pd.concat([part, whole], axis=1, join="inner")
    bad = int((aligned.iloc[:, 0] > aligned.iloc[:, 1] * (1 + tol)).sum())
    return _row(layer, f"{name} never exceeds its whole", bad == 0,
                f"{bad} rows where the part exceeds the whole", bad)


def coverage(covered: float, total: float, layer: str, name: str,
             minimum: float) -> dict:
    share = covered / total if total else 0.0
    return _row(layer, f"{name} coverage at least {minimum:.0%}", share >= minimum,
                f"{share:.1%} of {name} covered", share)


def note(layer: str, check: str, detail: str, value: float | None = None) -> dict:
    """A recorded observation that is not a pass or fail condition."""
    row = {"layer": layer, "check": check, "ok": True, "value": value, "detail": detail}
    ROWS.append(row)
    return row


def write(path: Path = config.CHECKS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ROWS).to_csv(path, index=False)
    return path


def reset() -> None:
    ROWS.clear()
