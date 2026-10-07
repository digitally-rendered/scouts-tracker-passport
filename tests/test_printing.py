"""print_passports.py: never sends anything to a real printer."""
import subprocess

import pymupdf
import pytest

import print_passports as pp


@pytest.fixture
def print_dir(out_dir):
    return out_dir / "print 4-up"


def test_finds_one_file_per_cub_in_name_order(print_dir):
    files = pp.cub_files(print_dir)
    assert [n for n, _ in files] == ["Alex Tester", "Blair Example", "Casey Sample"]
    assert all(f.exists() for _, f in files)
    assert not any("ALL CUBS" in f.name for _, f in files)


def test_filter_by_cub(print_dir):
    assert [n for n, _ in pp.cub_files(print_dir, ["blair example"])] == ["Blair Example"]
    with pytest.raises(SystemExit):
        pp.cub_files(print_dir, ["Nobody Here"])


def test_mac_command_is_single_sided_letter_actual_size(monkeypatch, tmp_path):
    monkeypatch.setattr(pp, "IS_WIN", False)
    cmd = pp.print_command(tmp_path / "a.pdf", "Office Printer", "Passport - A")
    assert cmd[:3] == ["lp", "-d", "Office Printer"]
    for opt in ("media=Letter", "sides=one-sided", "print-scaling=none"):
        assert opt in cmd


def test_windows_uses_sumatra_when_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(pp, "IS_WIN", True)
    monkeypatch.setattr(pp, "find_sumatra", lambda: r"C:\Tools\SumatraPDF.exe")
    cmd = pp.print_command(tmp_path / "a.pdf", "Brother", "t")
    assert cmd[0].endswith("SumatraPDF.exe") and "-print-to" in cmd
    assert "noscale" in cmd[cmd.index("-print-settings") + 1]


def test_windows_fallback_escapes_quotes(monkeypatch, tmp_path):
    monkeypatch.setattr(pp, "IS_WIN", True)
    monkeypatch.setattr(pp, "find_sumatra", lambda: None)
    cmd = pp.print_command(tmp_path / "Sam O'Brien.pdf", "Bob's Printer", "t")
    assert cmd[0] == "powershell" and "O''Brien" in cmd[-1] and "Bob''s Printer" in cmd[-1]


def test_dry_run_prints_nothing(print_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    lines = []
    assert pp.print_all(pp.cub_files(print_dir), "P", dry_run=True, log=lines.append) == 0
    assert not calls and len(lines) == 3 and all("[dry run]" in l for l in lines)


def test_one_job_per_cub_and_failures_counted(print_dir, monkeypatch):
    sent = []

    def fake_run(cmd, **k):
        sent.append(cmd)
        return subprocess.CompletedProcess(cmd, 1 if "Blair" in cmd[-1] else 0, "", "paper jam")
    monkeypatch.setattr(pp, "IS_WIN", False)
    monkeypatch.setattr(subprocess, "run", fake_run)
    lines = []
    assert pp.print_all(pp.cub_files(print_dir), "P", log=lines.append) == 1
    assert len(sent) == 3 and [c[4] for c in sent] == [
        "Passport - Alex Tester", "Passport - Blair Example", "Passport - Casey Sample"]
    assert any(l.startswith("FAILED Blair Example") for l in lines)


def test_test_sheet_is_one_page(print_dir):
    _, pdf = pp.cub_files(print_dir)[0]
    one = pp.first_sheet_copy(pdf)
    with pymupdf.open(one) as d:
        assert len(d) == 1 and "page 1 of" in d[0].get_text()
