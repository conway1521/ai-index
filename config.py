"""Paths and constants shared across the index."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
RAW_DIR = PACKAGE_ROOT / "data" / "raw"
FIXTURE_DIR = PACKAGE_ROOT / "tests" / "fixtures"
OUTPUT_DIR = PACKAGE_ROOT / "output"
TABLE_DIR = OUTPUT_DIR / "tables"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
CHECKS_PATH = OUTPUT_DIR / "checks.csv"

# The exposure measures the state layer reports under. Names follow
# src.ai_measures, where each is built and validated.
EXPOSURE_MEASURES = ("eloundou_beta", "felten_language", "anthropic_observed")

# Age band for the young-worker gauge, inclusive.
YOUNG_AGE = (22, 27)

# Seed for every relabelling draw in the package.
SEED = 20260920
