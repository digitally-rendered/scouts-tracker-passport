"""Test setup: point the private workspace at a throwaway folder BEFORE any of
the tool's modules are imported, and build passports once from the synthetic
fixture (three invented Cubs - no real data)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(tempfile.mkdtemp(prefix="passport-test-"))
os.environ["PASSPORT_DATA"] = str(WORKSPACE)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "scoutstracker.json"
CUBS = ["Alex Tester", "Blair Example", "Casey Sample"]


@pytest.fixture(scope="session")
def data_dir() -> Path:
    import build_data
    d = WORKSPACE / "data" / "2026-01-01"
    (d / "raw").mkdir(parents=True)
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    (d / "raw" / "scoutstracker.json").write_text(json.dumps(raw), encoding="utf-8")
    build_data.build(d)
    return d


@pytest.fixture(scope="session")
def out_dir(data_dir) -> Path:
    import fill_passport
    out = WORKSPACE / "out" / "2026-01-01"
    fill_passport.FILL_LOG.clear()
    fill_passport.use_data_dir(data_dir)
    fill_passport.fill_all_from_roster(max_stage=4, out_dir=out)
    return out


@pytest.fixture(scope="session")
def fill_log(out_dir) -> dict:
    return json.loads((out_dir / "fill_log.json").read_text(encoding="utf-8"))["cubs"]


@pytest.fixture(scope="session")
def findings(data_dir, out_dir) -> list[dict]:
    import audit_passports
    return audit_passports.audit(data_dir, out_dir)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(WORKSPACE, ignore_errors=True)
