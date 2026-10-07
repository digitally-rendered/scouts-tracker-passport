"""print_passports.py + print_layout.py: never sends anything to a real printer."""
import subprocess

import pymupdf
import pytest

import print_layout as pl
import print_passports as pp


# ------------------------------------------------------------- layouts --

def test_booklet_page_order():
    # 8 pages (0-based): sheet 1 front 8|1, back 2|7; sheet 2 front 6|3, back 4|5
    assert pl.booklet_order(8) == [(7, 0), (1, 6), (5, 2), (3, 4)]
    order = pl.booklet_order(64)
    assert len(order) == 32 and sorted(i for side in order for i in side) == list(range(64))


def test_layout_files_made_on_demand(out_dir):
    for layout in ("4up", "booklet", "fullsize"):
        files = pp.layout_files(out_dir, layout)
        assert [n for n, _ in files] == ["Alex Tester", "Blair Example", "Casey Sample"]
        assert all(f.exists() for _, f in files)


def test_booklet_is_full_size_landscape_pairs(out_dir):
    _, f = pp.layout_files(out_dir, "booklet", ["Alex Tester"])[0]
    with pymupdf.open(f) as d, pymupdf.open(out_dir / "Alex Tester - Passport 2026.pdf") as src:
        n = len(src) + (-len(src)) % 4
        assert len(d) == n // 2                                   # 2 pages per side
        assert (d[0].rect.width, d[0].rect.height) == (792, 612)  # landscape letter
        assert "Alex Tester" in d[0].get_text()                   # cover is on sheet 1's front (right half)
        right = pymupdf.Rect(396, 0, 792, 612)
        assert "belongs to" in d[0].get_text(clip=right)


def test_fullsize_is_actual_size_with_footer(out_dir):
    _, f = pp.layout_files(out_dir, "fullsize", ["Alex Tester"])[0]
    with pymupdf.open(f) as d:
        assert (d[0].rect.width, d[0].rect.height) == (612, 792) and len(d) % 2 == 0
        assert "Alex Tester  -  page 1 of" in d[0].get_text()


def test_filter_by_cub(out_dir):
    assert [n for n, _ in pp.layout_files(out_dir, "4up", ["blair example"])] == ["Blair Example"]
    with pytest.raises(SystemExit):
        pp.layout_files(out_dir, "4up", ["Nobody Here"])


# ------------------------------------------------------------ commands --

def test_mac_command_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(pp, "IS_WIN", False)
    cmd = pp.print_command(tmp_path / "a.pdf", "Office Printer", "t")
    assert cmd[:3] == ["lp", "-d", "Office Printer"]
    for opt in ("media=Letter", "sides=one-sided", "print-scaling=none"):
        assert opt in cmd
    assert "sides=two-sided-short-edge" in pp.print_command(tmp_path / "a.pdf", "P", "t", "short")
    assert "sides=two-sided-long-edge" in pp.print_command(tmp_path / "a.pdf", "P", "t", "long")


def test_windows_uses_sumatra_when_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(pp, "IS_WIN", True)
    monkeypatch.setattr(pp, "find_sumatra", lambda: r"C:\Tools\SumatraPDF.exe")
    cmd = pp.print_command(tmp_path / "a.pdf", "Brother", "t", "short")
    settings = cmd[cmd.index("-print-settings") + 1]
    assert cmd[0].endswith("SumatraPDF.exe") and "noscale" in settings and "duplexshort" in settings


def test_windows_fallback_escapes_quotes(monkeypatch, tmp_path):
    monkeypatch.setattr(pp, "IS_WIN", True)
    monkeypatch.setattr(pp, "find_sumatra", lambda: None)
    cmd = pp.print_command(tmp_path / "Sam O'Brien.pdf", "Bob's Printer", "t")
    assert cmd[0] == "powershell" and "O''Brien" in cmd[-1] and "Bob''s Printer" in cmd[-1]


@pytest.mark.parametrize("options,expected", [
    ("Duplex/2-Sided Printing: *None DuplexNoTumble DuplexTumble", True),
    ("sides/Two-Sided: *one-sided two-sided-long-edge two-sided-short-edge", True),
    ("PageSize/Media Size: A4 *Letter\nMediaType/MediaType: *any", False),   # e.g. the Brother MFC-9130CW
])
def test_duplex_detection(monkeypatch, options, expected):
    monkeypatch.setattr(pp, "IS_WIN", False)
    monkeypatch.setattr(pp, "_run", lambda cmd: options)
    assert pp.printer_duplex("P") is expected


# ------------------------------------------------------------- planning --

def test_print_all_is_one_job_with_each_cub_together(out_dir):
    files = pp.layout_files(out_dir, "4up")
    assert len(pp.plan_jobs(files, "4up", False, None, False)[0]) == 3    # default: one job per Cub
    (title, pdf, sides), = pp.plan_jobs(files, "4up", False, None, False, one_job=True)[0]
    assert title == "Passports - 3 Cubs" and sides == "one"
    assert pp.pages(pdf) == sum(pp.pages(f) for _, f in files)
    with pymupdf.open(pdf) as d:
        owners = [next(n for n, _ in files if n in p.get_text()) for p in d]
    assert owners == sorted(owners)            # Alex..., then Blair..., then Casey... - never mixed


def test_booklet_on_duplex_printer_is_short_edge(out_dir):
    files = pp.layout_files(out_dir, "booklet")
    jobs, after = pp.plan_jobs(files, "booklet", True, None, False, one_job=False)
    assert len(jobs) == 3 and all(sides == "short" for _, _, sides in jobs)
    (_, _, sides), = pp.plan_jobs(files, "booklet", True, None, False, one_job=True)[0]
    assert sides == "short" and "fold" in after.lower()


def test_booklet_on_single_sided_printer_needs_two_passes(out_dir):
    with pytest.raises(SystemExit, match="two\\s+passes"):
        pp.plan_jobs(pp.layout_files(out_dir, "booklet"), "booklet", False, None, False)


def test_manual_passes_split_fronts_and_backs(out_dir):
    files = pp.layout_files(out_dir, "booklet", ["Alex Tester"])
    sides = pp.pages(files[0][1])
    (_, fronts, s1), = pp.plan_jobs(files, "booklet", False, "fronts", False)[0]
    (_, backs, s2), = pp.plan_jobs(files, "booklet", False, "backs", False, reverse=True, rotate=True)[0]
    assert s1 == s2 == "one"
    assert pp.pages(fronts) == pp.pages(backs) == sides // 2
    with pymupdf.open(backs) as b:
        assert all(p.rotation == 180 for p in b)


def test_manual_backs_reverse_order(out_dir):
    files = pp.layout_files(out_dir, "booklet", ["Alex Tester"])
    normal = pp.manual_pass(files, "backs")
    rev = pp.manual_pass(files, "backs", reverse=True)
    with pymupdf.open(normal) as a, pymupdf.open(rev) as b:
        assert [p.get_text() for p in a] == [p.get_text() for p in reversed(list(b))]


def test_test_sheets(out_dir):
    files = pp.layout_files(out_dir, "booklet")
    jobs, _ = pp.plan_jobs(files, "booklet", True, None, True)
    assert len(jobs) == 1 and pp.pages(jobs[0][1]) == 2              # one sheet, front + back
    jobs, _ = pp.plan_jobs(files, "booklet", False, "fronts", True)
    assert pp.pages(jobs[0][1]) == 1
    jobs, _ = pp.plan_jobs(pp.layout_files(out_dir, "4up"), "4up", False, None, True)
    assert len(jobs) == 1 and pp.pages(jobs[0][1]) == 1
    with pytest.raises(SystemExit):
        pp.plan_jobs(pp.layout_files(out_dir, "4up"), "4up", False, "fronts", False)


# --------------------------------------------------------------- sending --

def test_dry_run_prints_nothing(out_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    lines = []
    assert pp.print_all(pp.layout_files(out_dir, "4up"), "P", dry_run=True, log=lines.append) == 0
    assert not calls and len(lines) == 3 and all("[dry run]" in l for l in lines)


def test_one_job_per_cub_and_failures_counted(out_dir, monkeypatch):
    sent = []

    def fake_run(cmd, **k):
        sent.append(cmd)
        return subprocess.CompletedProcess(cmd, 1 if "Blair" in cmd[-1] else 0, "", "paper jam")
    monkeypatch.setattr(pp, "IS_WIN", False)
    monkeypatch.setattr(subprocess, "run", fake_run)
    lines = []
    assert pp.print_all(pp.layout_files(out_dir, "4up"), "P", log=lines.append) == 1
    assert [c[4] for c in sent] == [
        "Passport - Alex Tester", "Passport - Blair Example", "Passport - Casey Sample"]
    assert any(l.startswith("FAILED Passport - Blair Example") for l in lines)


# ------------------------------------------------- one job at a time --

def test_waits_for_each_job_before_sending_the_next(out_dir, monkeypatch):
    events, next_id = [], iter(range(500, 600))
    monkeypatch.setattr(pp, "IS_WIN", False)

    def fake_run(cmd, **k):
        jid = next(next_id)
        events.append(("sent", cmd[4], jid))
        return subprocess.CompletedProcess(cmd, 0, f"request id is P-{jid} (1 file(s))\n", "")
    polls = {}

    def fake_status(printer, jid):
        polls[jid] = polls.get(jid, 0) + 1
        events.append(("poll", jid))
        return ("processing", 3) if polls[jid] < 3 else ("completed", 16)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(pp, "job_status", fake_status)
    monkeypatch.setattr(pp, "pages", lambda pdf: 16)
    files = pp.layout_files(out_dir, "4up")
    jobs = [(f"Passport - {n}", f, "one") for n, f in files]
    assert pp.send(jobs, "P", log=lambda m: None, wait=True) == 0
    sent_at = [i for i, e in enumerate(events) if e[0] == "sent"]
    # every job's last poll (completed) happens before the next job is sent
    for a, b in zip(sent_at, sent_at[1:]):
        jid = events[a][2]
        assert ("poll", jid) in events[a:b] and polls[jid] == 3


def test_stops_when_a_job_prints_short(out_dir, monkeypatch):
    monkeypatch.setattr(pp, "IS_WIN", False)
    sent = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: sent.append(cmd) or
                        subprocess.CompletedProcess(cmd, 0, f"request id is P-{len(sent)} (1 file(s))", ""))
    monkeypatch.setattr(pp, "job_status", lambda p, j: ("completed", 10))   # 10 of 16
    monkeypatch.setattr(pp, "pages", lambda pdf: 16)
    lines = []
    files = pp.layout_files(out_dir, "4up")
    assert pp.send([(n, f, "one") for n, f in files], "P", log=lines.append) == 1
    assert len(sent) == 1                                   # nothing after the bad job
    assert any("10 of 16" in l for l in lines) and any(l.startswith("STOPPED") for l in lines)


def test_double_sided_expects_half_the_sides_as_sheets(monkeypatch):
    seen = {}
    monkeypatch.setattr(pp, "job_status", lambda p, j: ("completed", 16))
    assert pp.wait_for_job("P", 1, 16, log=lambda m: None)
    monkeypatch.setattr(pp, "job_status", lambda p, j: ("aborted", 2))
    assert not pp.wait_for_job("P", 1, 16, log=lambda m: seen.setdefault("m", m))
    assert "aborted" in seen["m"]
