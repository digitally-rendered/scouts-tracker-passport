"""Send the passports straight to a printer.

Layouts (--layout):
  4up       4 pages per letter sheet, single-sided; cut and stack   (default)
  booklet   full size, 2 pages per side; print both sides, fold, staple on the fold
  fullsize  full size, 1 page per sheet; both sides if the printer can

Double-sided (--duplex auto|yes|no): "auto" asks the printer. If the printer
can't print both sides, booklets are printed in two passes ("manual duplex"):

    print_passports.py --layout booklet --pass fronts      # 1. fronts
    (put the printed stack back in the paper tray)
    print_passports.py --layout booklet --pass backs       # 2. backs
    add --reverse-backs and/or --rotate-backs if the test sheet came out wrong

Other options:
    --list               show printers (and which print both sides)
    --dry-run            show what would print, use no paper
    --test-sheet         just the first sheet of one Cub
    --cub "First Last"   only this Cub (repeatable)
    --printer NAME       default: the system default printer
    --yes                don't ask before printing

Everything is sent as ONE print job (each Cub's sheets together, in name order),
because some network printers interleave pages from jobs sent at the same time.
With --separate-jobs, each job is sent only after the previous one has finished
printing (and its sheet count is checked); if one fails, nothing after it is sent.

macOS/Linux print with lp. Windows uses SumatraPDF if installed (exact size,
double-sided control) and otherwise the default PDF app.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pymupdf  # noqa: E402

from paths import OUT_DIR  # noqa: E402
from print_layout import LAYOUTS  # noqa: E402

IS_WIN = platform.system() == "Windows"
PASSPORT_SUFFIX = " - Passport 2026.pdf"


# ---------------------------------------------------------------- printers --

def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _ps_quote(v) -> str:
    return str(v).replace("'", "''")


def list_printers() -> tuple[list[str], str | None]:
    """(printer names, default printer)."""
    if IS_WIN:
        ps = ("Get-Printer | Select-Object Name | ConvertTo-Json -Compress; "
              "'---'; (Get-CimInstance Win32_Printer | Where-Object Default).Name")
        js, _, default = _run(["powershell", "-NoProfile", "-Command", ps]).partition("---")
        try:
            data = json.loads(js.strip() or "[]")
        except json.JSONDecodeError:
            data = []
        data = [data] if isinstance(data, dict) else data
        return [d["Name"] for d in data], (default.strip() or None)
    names = [line.split()[0] for line in _run(["lpstat", "-e"]).splitlines() if line.strip()]
    default = None
    for line in _run(["lpstat", "-d"]).splitlines():
        if ":" in line and "no system default" not in line:
            default = line.split(":", 1)[1].strip()
    return names, default


def printer_duplex(printer: str) -> bool:
    """Can this printer print both sides by itself?"""
    if IS_WIN:
        ps = (f"(Get-CimInstance Win32_Printer -Filter \"Name='{_ps_quote(printer)}'\")"
              ".CapabilityDescriptions -contains 'Duplex'")
        return _run(["powershell", "-NoProfile", "-Command", ps]).strip().lower() == "true"
    for line in _run(["lpoptions", "-p", printer, "-l"]).splitlines():
        key, _, values = line.partition(":")
        if key.split("/")[0] in ("Duplex", "sides", "KMDuplex", "EFDuplex"):
            v = values.lower()
            if "tumble" in v or "two-sided" in v:
                return True
    return False


def find_sumatra() -> str | None:
    found = shutil.which("SumatraPDF") or shutil.which("SumatraPDF.exe")
    if found:
        return found
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
                 os.environ.get("ProgramFiles(x86)", "")):
        p = Path(base) / "SumatraPDF" / "SumatraPDF.exe"
        if base and p.exists():
            return str(p)
    return None


def print_command(pdf: Path, printer: str, title: str, sides: str = "one") -> list[str]:
    """Command printing one file, letter, actual size. sides: one | long | short."""
    if not IS_WIN:
        lp_sides = {"one": "one-sided", "long": "two-sided-long-edge",
                    "short": "two-sided-short-edge"}[sides]
        return ["lp", "-d", printer, "-t", title, "-o", "media=Letter",
                "-o", f"sides={lp_sides}", "-o", "print-scaling=none", "-o", "fit-to-page=false",
                str(pdf)]
    sumatra = find_sumatra()
    if sumatra:
        mode = {"one": "simplex", "long": "duplexlong", "short": "duplexshort"}[sides]
        return [sumatra, "-print-to", printer, "-print-settings", f"noscale,{mode},paper=letter",
                "-silent", str(pdf)]
    # Fallback: the default PDF app's "print to" verb (may scale; no 2-sided control).
    return ["powershell", "-NoProfile", "-Command",
            f"Start-Process -FilePath '{_ps_quote(pdf)}' -Verb PrintTo "
            f"-ArgumentList '\"{_ps_quote(printer)}\"' -Wait"]


# ------------------------------------------------------------------- files --

def latest_out_dir() -> Path:
    dirs = sorted(p for p in OUT_DIR.glob("20*-*-*") if (p / "fill_log.json").exists())
    if not dirs:
        raise SystemExit("No passports yet - make the passports first.")
    return dirs[-1]


def layout_files(out_dir: Path, layout: str, only: list[str] | None = None) -> list[tuple[str, Path]]:
    """[(Cub name, print-ready PDF)] for a layout, making missing files from the passports."""
    folder, maker, _ = LAYOUTS[layout]
    cubs = sorted(json.loads((out_dir / "fill_log.json").read_text(encoding="utf-8"))["cubs"])
    if only:
        wanted = {n.strip().lower() for n in only}
        missing = wanted - {c.lower() for c in cubs}
        if missing:
            raise SystemExit(f"No passport for: {', '.join(sorted(missing))}")
        cubs = [c for c in cubs if c.lower() in wanted]
    (out_dir / folder).mkdir(exist_ok=True)
    files = []
    for cub in cubs:
        src = out_dir / f"{cub}{PASSPORT_SUFFIX}"
        dst = out_dir / folder / f"{src.stem} - {folder}.pdf"
        if not src.exists():
            raise SystemExit(f"Missing passport for {cub}: {src.name}")
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            if layout == "4up":
                maker(src, dst, src.stem, cub)
            else:
                maker(src, dst, cub)
        files.append((cub, dst))
    return files


def pages(pdf: Path) -> int:
    with pymupdf.open(pdf) as d:
        return len(d)


def _tmp(name: str) -> Path:
    return Path(tempfile.mkdtemp(prefix="passport-print-")) / name


def first_sheet_copy(pdf: Path, sides_per_sheet: int = 1) -> Path:
    """A copy with just the first sheet (1 side, or front+back)."""
    out = _tmp(f"TEST {pdf.name}")
    with pymupdf.open(pdf) as d, pymupdf.open() as one:
        one.insert_pdf(d, from_page=0, to_page=min(sides_per_sheet, len(d)) - 1)
        one.save(out)
    return out


def manual_pass(files: list[tuple[str, Path]], which: str, reverse: bool = False,
                rotate: bool = False) -> Path:
    """One PDF of every front (odd sides) or every back (even sides), all Cubs in order.

    Backs can be reversed (if the printer stacks pages the other way round) and/or
    turned upside down (if the backs came out upside down on the test sheet)."""
    start = 0 if which == "fronts" else 1
    out = _tmp(f"{which}.pdf")
    with pymupdf.open() as combined:
        for _, pdf in files:
            with pymupdf.open(pdf) as d:
                for i in range(start, len(d), 2):
                    combined.insert_pdf(d, from_page=i, to_page=i)
        if which == "backs":
            order = list(range(len(combined)))
            if reverse:
                order.reverse()
            combined.select(order)
            if rotate:
                for page in combined:
                    page.set_rotation((page.rotation + 180) % 360)
        combined.save(out)
    return out


JOB_TIMEOUT_S = 20 * 60     # minimum; grows with the job (see wait_for_job)
POLL_S = 3

_JOB_TEST = """{ NAME "job" OPERATION Get-Job-Attributes
  GROUP operation-attributes-tag
  ATTR charset attributes-charset utf-8
  ATTR naturalLanguage attributes-natural-language en
  ATTR uri printer-uri $uri
  ATTR integer job-id %d
  ATTR keyword requested-attributes job-state,job-media-sheets-completed
  DISPLAY job-state
  DISPLAY job-media-sheets-completed
}"""


def job_status(printer: str, job_id: int) -> tuple[str, int | None]:
    """(state, sheets printed) from the local print system, e.g. ("completed", 16)."""
    import re
    test = _tmp("job.test")
    test.write_text(_JOB_TEST % job_id)
    out = _run(["ipptool", "-tv", f"ipp://localhost/printers/{printer}", str(test)])
    state = re.search(r"job-state \(enum\) = (\S+)", out)
    sheets = re.search(r"job-media-sheets-completed \(integer\) = (\d+)", out)
    return (state.group(1) if state else "unknown"), (int(sheets.group(1)) if sheets else None)


def wait_for_job(printer: str, job_id: int, expected: int, log=print, sleep=None) -> bool:
    """Wait until the printer has finished this job, so jobs never run at the same
    time (some network printers interleave their pages). True if it printed fully."""
    import time
    sleep = sleep or time.sleep
    waited = 0
    limit = max(JOB_TIMEOUT_S, expected * 15)   # ~4 pages/min worst case, incl. paper refills
    while waited < limit:
        state, sheets = job_status(printer, job_id)
        if state in ("completed", "canceled", "aborted"):
            if state != "completed":
                log(f"  job {job_id} was {state} after {sheets or 0} of {expected} sheets")
                return False
            if sheets is not None and sheets < expected:
                log(f"  job {job_id} finished but the printer reported {sheets} of {expected} sheets")
                return False
            return True
        if state == "unknown":          # can't ask (e.g. no ipptool): fall back to the queue list
            if f"{printer}-{job_id} " not in _run(["lpstat", "-W", "not-completed", "-o", printer]):
                return True
        sleep(POLL_S)
        waited += POLL_S
    log(f"  stopped watching job {job_id} after {limit // 60} minutes (it may still be printing)")
    return False


def send(jobs: list[tuple[str, Path, str]], printer: str, dry_run: bool = False, log=print,
         wait: bool = True) -> int:
    """Print (title, pdf, sides) jobs one at a time. Returns how many failed."""
    import re
    failed = 0
    for title, pdf, sides in jobs:
        n = pages(pdf)
        desc = f"{title}: {n} side{'s' if n != 1 else ''}" + (
            "" if sides == "one" else f", double-sided ({sides} edge)")
        if dry_run:
            log(f"[dry run] {desc} -> {printer}")
            continue
        r = subprocess.run(print_command(pdf, printer, title, sides), capture_output=True, text=True)
        if r.returncode != 0:
            failed += 1
            log(f"FAILED {title}: {(r.stderr or r.stdout).strip()[:300]}")
            continue
        m = re.search(r"request id is \S+-(\d+)", r.stdout)
        if not (wait and m and not IS_WIN):
            log(f"Sent {desc} to {printer}")
            continue
        log(f"Printing {desc} (job {m.group(1)})...")
        expected = n if sides == "one" else (n + 1) // 2
        if wait_for_job(printer, int(m.group(1)), expected, log):
            log(f"  done: {title}")
        else:
            failed += 1
            log(f"STOPPED: {title} didn't finish. Nothing else was sent. Check the printer, "
                f"then print the rest with --cub.")
            break
    return failed


def print_all(files, printer: str, dry_run: bool = False, log=print) -> int:
    """Print 4-up files, one single-sided job per Cub."""
    return send([(f"Passport - {n}", f, "one") for n, f in files], printer, dry_run, log)


AFTER = {
    "4up": "Cut each Cub's stack on the dashed lines, then stack the piles top-left, "
           "top-right, bottom-left, bottom-right.",
    "booklet": "Fold each Cub's stack in half (keep it in order) and staple on the fold.",
    "fullsize": "Each Cub's pages are in order - staple or bind on the left edge.",
}


def combine(files: list[tuple[str, Path]]) -> Path:
    """One PDF with every Cub's sheets back to back (each Cub's together, in order)."""
    out = _tmp(f"Passports - {len(files)} Cubs.pdf")
    with pymupdf.open() as combined:
        for _, pdf in files:
            with pymupdf.open(pdf) as d:
                combined.insert_pdf(d)
        combined.save(out, garbage=3, deflate=True)
    return out


def plan_jobs(files, layout: str, duplex: bool, which: str | None, test: bool,
              reverse: bool = False, rotate: bool = False,
              one_job: bool = True) -> tuple[list, str]:
    """Work out the print jobs. Returns (jobs, what to do afterwards)."""
    edge = LAYOUTS[layout][2]
    if test:
        files = files[:1]

    if which:                                    # manual double-sided pass
        if edge is None:
            raise SystemExit("The 4-per-sheet layout is single-sided; it has no fronts/backs.")
        src = [(n, first_sheet_copy(f, 2)) for n, f in files] if test else files
        pdf = manual_pass(src, which, reverse, rotate)
        who = files[0][0] if len(files) == 1 else f"{len(files)} Cubs"
        label = f"{'TEST ' if test else ''}Passport {which} - {who}"
        after = ("Now take the printed stack out, turn it over (printed side up) like turning a "
                 "page, and put it back in the paper tray. Then print the backs."
                 if which == "fronts" else
                 "Check the backs: each sheet's back should belong to the same sheet and be the "
                 "right way up. If the order is backwards, use 'reverse backs'; if upside down, "
                 "use 'turn backs upside down' - then try the test sheet again."
                 if test else AFTER[layout])
        return [(label, pdf, "one")], after

    if layout == "booklet" and not duplex:
        raise SystemExit("This printer can't print both sides by itself. Print the booklet in two "
                         "passes: --pass fronts, reload the paper, then --pass backs.")
    sides = edge if (edge and duplex) else "one"
    per_sheet = 2 if sides != "one" else 1
    if test:
        name, pdf = files[0]
        return [(f"Passport - {name} (test sheet)", first_sheet_copy(pdf, per_sheet), sides)], AFTER[layout]
    if one_job and len(files) > 1:
        # A single job can't be interleaved with anything else by the printer.
        return [(f"Passports - {len(files)} Cubs", combine(files), sides)], AFTER[layout]
    return [(f"Passport - {name}", pdf, sides) for name, pdf in files], AFTER[layout]


def main() -> int:
    ap = argparse.ArgumentParser(description="Print the passports",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("--list", action="store_true", help="list printers and exit")
    ap.add_argument("--printer", help="printer name (default: the system default)")
    ap.add_argument("--layout", choices=list(LAYOUTS), default="4up")
    ap.add_argument("--duplex", choices=["auto", "yes", "no"], default="auto",
                    help="does the printer print both sides by itself? (default: ask it)")
    ap.add_argument("--pass", dest="which", choices=["fronts", "backs"],
                    help="manual double-sided printing: print fronts, reload, print backs")
    ap.add_argument("--reverse-backs", action="store_true", help="manual pass: backs in reverse order")
    ap.add_argument("--rotate-backs", action="store_true", help="manual pass: turn backs upside down")
    ap.add_argument("--cub", action="append", help="only this Cub (repeatable)")
    ap.add_argument("--dir", help="passports folder (default: newest out/<date>)")
    ap.add_argument("--dry-run", action="store_true", help="show what would print, use no paper")
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    ap.add_argument("--test-sheet", action="store_true", help="just the first sheet of one Cub")
    ap.add_argument("--separate-jobs", action="store_true",
                    help="one print job per Cub instead of one job for everyone")
    ap.add_argument("--no-wait", action="store_true",
                    help="send every job at once instead of one after another (not recommended)")
    a = ap.parse_args()

    printers, default = list_printers()
    if a.list:
        if not printers:
            print("No printers found. Add one in your computer's printer settings.")
        for p in printers:
            print(f"{p}{'   (default)' if p == default else ''}"
                  f"{'   prints both sides' if printer_duplex(p) else '   one side only'}")
        return 0

    printer = a.printer or default
    if not printer:
        raise SystemExit("No default printer. Choose one with --printer (see --list).")
    if printers and printer not in printers:
        raise SystemExit(f"Printer {printer!r} not found. Available: {', '.join(printers)}")
    duplex = printer_duplex(printer) if a.duplex == "auto" else a.duplex == "yes"
    if IS_WIN and not find_sumatra():
        print("Note: SumatraPDF isn't installed, so Windows' default PDF app will print; it may "
              "shrink pages and can't print both sides. For best results: "
              "winget install SumatraPDF.SumatraPDF")

    out_dir = Path(a.dir) if a.dir else latest_out_dir()
    files = layout_files(out_dir, a.layout, a.cub)
    jobs, after = plan_jobs(files, a.layout, duplex, a.which, a.test_sheet,
                            a.reverse_backs, a.rotate_backs, one_job=not a.separate_jobs)
    total = sum(pages(p) for _, p, _ in jobs)
    two = any(s != "one" for _, _, s in jobs)
    sheets = (total + 1) // 2 if two else total
    print(f"{a.layout}: {len(jobs)} job(s), {sheets} sheet(s) of paper"
          f"{', double-sided' if two else ''}, to {printer} (passports from {out_dir.name})")

    if not a.dry_run and not a.yes:
        if not sys.stdin.isatty():
            raise SystemExit("Add --yes to print without asking.")
        if input(f"Print {sheets} sheet(s) now? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing printed.")
            return 0
    failed = send(jobs, printer, a.dry_run, wait=not a.no_wait)
    if not a.dry_run:
        print("\n" + (after if not failed else
                      f"{failed} job(s) failed - check the printer, then reprint those Cubs with --cub."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
