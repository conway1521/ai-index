import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def fresh_checks():
    from aiindex import checks
    checks.reset()
    yield
    checks.reset()
