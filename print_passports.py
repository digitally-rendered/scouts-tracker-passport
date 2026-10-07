"""Send the 4-up print files straight to a printer, one job per Cub.

Each Cub is a separate print job (in name order) so their stacks stay apart
in the output tray. Printing is single-sided, letter, actual size.

    python print_passports.py --list                 # show printers
    python print_passports.py --dry-run              # show what would print
    python print_passports.py                        # print every Cub (asks first)
    python print_passports.py --cub "First Last"     # just one Cub (repeatable)
    python print_passports.py --printer NAME --yes   # no question (used by the page)
    python print_passports.py --test-sheet           # one sheet only, to check size

macOS/Linux use the built-in print system (lp). Windows uses SumatraPDF if it
is installed (exact size, recommended) and otherwise the default PDF app.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from paths import OUT_DIR  # noqa: E402

IS_WIN = platform.system() == "Windows"
SUFFIX = " - Passport 2026 - print 4-up.pdf"
COMBINED = "ALL CUBS - print 4-up.pdf"


# ---------------------------------------------------------------- printers --

def list_printers() -> tuple[list[str], str | None]:
    """(printer names, default printer)."""
    if IS_WIN:
        ps = ("Get-Printer | Select-Object Name | ConvertTo-Json -Compress; "
              "'---'; (Get-CimInstance Win32_Printer | Where-Object Default).Name")
        out = _run(["powershell", "-NoProfile", "-Command", ps])
        js, _, default = out.partition("---")
        import json
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


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


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


def print_command(pdf: Path, printer: str, title: str) -> list[str]:
    """The command that prints one file single-sided, letter, actual size."""
    if not IS_WIN:
        return ["lp", "-d", printer, "-t", title, "-o", "media=Letter",
                "-o", "sides=one-sided", "-o", "print-scaling=none", "-o", "fit-to-page=false",
                str(pdf)]
    sumatra = find_sumatra()
    if sumatra:
        return [sumatra, "-print-to", printer, "-print-settings", "noscale,simplex,paper=letter",
                "-silent", str(pdf)]
    # Fallback: the default PDF app's "print to" verb (it may scale pages).
    q = lambda v: str(v).replace("'", "''")  # noqa: E731  (PowerShell single-quote escaping)
    return ["powershell", "-NoProfile", "-Command",
            f"Start-Process -FilePath '{q(pdf)}' -Verb PrintTo "
            f"-ArgumentList '\"{q(printer)}\"' -Wait"]


# ------------------------------------------------------------------- files --

def latest_print_dir() -> Path:
    dirs = sorted(p / "print 4-up" for p in OUT_DIR.glob("20*-*-*") if (p / "print 4-up").is_dir())
    if not dirs:
        raise SystemExit("No print files yet - make the passports first.")
    return dirs[-1]


def cub_files(print_dir: Path, only: list[str] | None = None) -> list[tuple[str, Path]]:
    files = sorted((f.name[: -len(SUFFIX)], f) for f in print_dir.glob(f"*{SUFFIX}"))
    if only:
        wanted = {n.strip().lower() for n in only}
        files = [(n, f) for n, f in files if n.lower() in wanted]
        missing = wanted - {n.lower() for n, _ in files}
        if missing:
            raise SystemExit(f"No print file for: {', '.join(sorted(missing))}")
    return files


def first_sheet_copy(pdf: Path) -> Path:
    """A one-page copy of the first sheet, for a test print."""
    import tempfile

    import pymupdf
    out = Path(tempfile.mkdtemp(prefix="passport-test-")) / f"TEST {pdf.name}"
    with pymupdf.open(pdf) as d, pymupdf.open() as one:
        one.insert_pdf(d, from_page=0, to_page=0)
        one.save(out)
    return out


def sheet_count(pdf: Path) -> int:
    import pymupdf
    with pymupdf.open(pdf) as d:
        return len(d)


def print_all(files, printer: str, dry_run: bool = False, log=print) -> int:
    """Send each Cub as its own job. Returns the number of jobs that failed."""
    failed = 0
    for name, pdf in files:
        cmd = print_command(pdf, printer, f"Passport - {name}")
        if dry_run:
            log(f"[dry run] {name}: {sheet_count(pdf)} sheets -> {printer}")
            continue
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            log(f"Sent {name} ({sheet_count(pdf)} sheets) to {printer}")
        else:
            failed += 1
            log(f"FAILED {name}: {(r.stderr or r.stdout).strip()[:300]}")
    return failed


def main() -> int:
    ap = argparse.ArgumentParser(description="Print the passports (4 per sheet), one job per Cub")
    ap.add_argument("--list", action="store_true", help="list printers and exit")
    ap.add_argument("--printer", help="printer name (default: the system default)")
    ap.add_argument("--cub", action="append", help="only this Cub (repeatable)")
    ap.add_argument("--dir", help="print folder (default: newest out/<date>/print 4-up)")
    ap.add_argument("--dry-run", action="store_true", help="show what would print, use no paper")
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    ap.add_argument("--test-sheet", action="store_true",
                    help="print just the first sheet of one Cub to check size and readability")
    a = ap.parse_args()

    printers, default = list_printers()
    if a.list:
        if not printers:
            print("No printers found. Add one in your computer's printer settings.")
        for p in printers:
            print(f"{p}{'   (default)' if p == default else ''}")
        return 0

    printer = a.printer or default
    if not printer:
        raise SystemExit("No default printer. Choose one with --printer (see --list).")
    if printers and printer not in printers:
        raise SystemExit(f"Printer {printer!r} not found. Available: {', '.join(printers)}")
    if IS_WIN and not find_sumatra():
        print("Note: SumatraPDF isn't installed, so Windows' default PDF app will print and may "
              "shrink pages. For exact size: winget install SumatraPDF.SumatraPDF")

    print_dir = Path(a.dir) if a.dir else latest_print_dir()
    files = cub_files(print_dir, a.cub)
    if not files:
        raise SystemExit(f"No print files in {print_dir}")
    if a.test_sheet:
        name, pdf = files[0]
        files = [(f"{name} (test sheet)", first_sheet_copy(pdf))]
    sheets = sum(sheet_count(f) for _, f in files)
    print(f"{len(files)} passport(s), {sheets} sheets, single-sided, to {printer} "
          f"(from {print_dir.parent.name})")

    if not a.dry_run and not a.yes:
        if not sys.stdin.isatty():
            raise SystemExit("Add --yes to print without asking.")
        if input(f"Print {sheets} sheets now? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing printed.")
            return 0
    failed = print_all(files, printer, a.dry_run)
    if not a.dry_run:
        print("\nAll sent. Cut each Cub's stack on the dashed lines, then stack the piles "
              "top-left, top-right, bottom-left, bottom-right." if not failed else
              f"\n{failed} job(s) failed - check the printer and try those Cubs again with --cub.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
