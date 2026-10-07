"""Doctor, CLI and privacy guard rails."""
import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import CUBS, FIXTURE, ROOT, WORKSPACE


def run(*args, env=None):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", env={**os.environ, **(env or {})})


def test_doctor_json_reports_every_check():
    r = run("doctor.py", "--json")
    results = json.loads(r.stdout)
    by = {x["check"]: x for x in results}
    for name in ("Python", "PDF library (PyMuPDF)", "Passport template", "Private data folder"):
        assert by[name]["status"] == "ok", by[name]
    assert all(x["status"] in ("ok", "warn", "fail") for x in results)
    assert all(x["fix"] for x in results if x["status"] != "ok")   # every problem has a fix


def test_doctor_output_has_no_cub_names(data_dir, out_dir):
    out = run("doctor.py").stdout + run("doctor.py", "--json").stdout
    assert not any(c in out for c in CUBS)


def test_cli_help():
    r = run("passport.py", "--help")
    assert r.returncode == 0 and "run" in r.stdout and "doctor" in r.stdout


def test_default_workspace_is_outside_code_folder():
    env = {k: v for k, v in os.environ.items() if k != "PASSPORT_DATA"}
    r = subprocess.run([sys.executable, "-c", "import paths; print(paths.WORKSPACE)"],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    ws = Path(r.stdout.strip())
    assert ws.name == "ScoutsPassportData"
    assert ROOT not in ws.parents and ws != ROOT


def test_tests_use_throwaway_workspace():
    import paths
    assert paths.WORKSPACE == WORKSPACE


def test_fixture_contains_only_invented_people():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert sorted(c["name"] for c in raw["cubs"]) == sorted(CUBS)
    assert set(raw["scouters"].values()) <= {"Test Scouter (inactive)", "Cub Pack", "Unknown"}
    assert set(raw) == {"fetched_at", "requirements", "scouters", "cubs"}


def test_gitignore_blocks_private_data():
    ignored = (ROOT / ".gitignore").read_text().split()
    for pattern in ("data/", "out/", "browser-profile/", "*.csv", ".env", ".claude/settings.local.json"):
        assert pattern in ignored
