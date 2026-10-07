"""fill_passport.py + audit_passports.py end to end on the invented Cubs."""
import json
import shutil

import pymupdf
import pytest

import audit_passports
import fill_passport
from conftest import CUBS


def pdf_text(path):
    with pymupdf.open(path) as d:
        return "\n".join(p.get_text() for p in d)


def test_every_cub_gets_a_passport(out_dir, fill_log):
    assert sorted(fill_log) == sorted(CUBS)
    for cub, log in fill_log.items():
        assert "error" not in log
        assert (out_dir / log["pdf"]).exists()
        assert log["unplaced"] == [], cub


def test_audit_has_no_errors(findings):
    errors = [f for f in findings if f["level"] == "ERROR"]
    assert errors == []


def test_audit_flags_expected_warnings_and_notes(findings):
    def has(level, cub, check, text=""):
        return any(f["level"] == level and f["cub"] == cub and f["check"] == check
                   and text in f["detail"] for f in findings)
    assert has("WARN", "Blair Example", "badge not awarded", "Camping Skills 1")
    assert has("INFO", "Blair Example", "scouter blank", "Aquatic Skills 4")
    assert has("INFO", "Alex Tester", "auto-ticked", "Camping Skills 2")
    assert not any(f["cub"] == "Casey Sample" and f["level"] != "INFO" for f in findings)


def test_stage_4_signoff_written(fill_log):
    assert "Aquatic Skills 4" in fill_log["Blair Example"]["signoffs_written"]
    assert fill_log["Blair Example"]["earned_not_in_passport"] == []


def test_pdf_contents(out_dir, fill_log):
    alex = pdf_text(out_dir / fill_log["Alex Tester"]["pdf"])
    assert "Alex Tester" in alex                        # cover
    assert "Test Scouter" in alex and "2025-05-14" in alex   # sign-off line
    assert "9" in alex                                  # tally count drawn


def test_read_back_matches_log(out_dir, fill_log):
    for cub, log in fill_log.items():
        assert audit_passports.read_back(out_dir / log["pdf"]) == (log["checks_drawn"], log["counts_drawn"]), cub


def test_stage_above_range_is_reported(data_dir, tmp_path):
    fill_passport.use_data_dir(data_dir)
    fill_passport.fill_passport("Blair Example", max_stage=3, out_dir=tmp_path)
    log = fill_passport.FILL_LOG["Blair Example"]
    assert log["earned_not_in_passport"] == ["Aquatic Skills 4"]
    assert "Aquatic Skills 4" not in log["signoffs_written"]


@pytest.fixture
def out_copy(out_dir, tmp_path):
    d = tmp_path / "out"
    shutil.copytree(out_dir, d)
    return d


def test_audit_catches_missing_print_file(data_dir, out_copy):
    (out_copy / "print 4-up" / "Alex Tester - Passport 2026 - print 4-up.pdf").unlink()
    f = audit_passports.audit(data_dir, out_copy)
    assert any(x["level"] == "ERROR" and x["check"] == "print file missing" for x in f)


def test_audit_catches_unplaced_ticks_and_tampered_pdf(data_dir, out_copy):
    log_path = out_copy / "fill_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8"))
    log["cubs"]["Alex Tester"]["unplaced"] = ["Camping Skills 1.1 = ✓"]
    log["cubs"]["Alex Tester"]["checks_drawn"] += 1
    log_path.write_text(json.dumps(log), encoding="utf-8")
    checks = {x["check"] for x in audit_passports.audit(data_dir, out_copy) if x["level"] == "ERROR"}
    assert {"tick not placed", "read-back mismatch"} <= checks


def test_audit_catches_missing_passport(data_dir, out_copy):
    log_path = out_copy / "fill_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8"))
    del log["cubs"]["Casey Sample"]
    log_path.write_text(json.dumps(log), encoding="utf-8")
    f = audit_passports.audit(data_dir, out_copy)
    assert any(x["level"] == "ERROR" and x["cub"] == "Casey Sample" and x["check"] == "no passport" for x in f)


def test_audit_reports_written(findings, out_dir):
    audit_passports.write_reports(findings, out_dir, CUBS)
    html = (out_dir / "audit.html").read_text(encoding="utf-8")
    assert "0 errors" in html and all(c in html for c in CUBS)
    assert (out_dir / "audit.csv").read_text(encoding="utf-8").startswith("level,cub,check,detail")
