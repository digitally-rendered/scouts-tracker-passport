"""Check that everything needed to make passports is in place.

Prints a checklist; every problem comes with a plain-English fix.

Usage:
    python doctor.py            # quick checks
    python doctor.py --online   # also check the saved ScoutsTracker login (opens a hidden browser)
    python doctor.py --json     # machine-readable (used by the Claude skill)
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from paths import (DATA_DIR, FONTS_DIR, OUT_DIR, PROFILE_DIR,  # noqa: E402
                   SUPPORT, TEMPLATE_PDF, WORKSPACE)

IS_WIN = platform.system() == "Windows"
SETUP = "setup.bat" if IS_WIN else "setup.command"
LOGIN = "login.bat" if IS_WIN else "login.command"
RUN = "run.bat" if IS_WIN else "run.command"

results: list[dict] = []


def check(name: str, ok: bool | None, detail: str = "", fix: str = "") -> bool:
    """ok=True pass, False fail, None warning."""
    results.append({"check": name, "status": {True: "ok", False: "fail", None: "warn"}[ok],
                    "detail": detail, "fix": "" if ok else fix})
    return bool(ok)


def run_checks(online: bool) -> None:
    check("Operating system", True, f"{platform.system()} {platform.release()} ({platform.machine()})")

    v = sys.version_info
    check("Python", v >= (3, 11), f"{v.major}.{v.minor}.{v.micro} at {sys.executable}",
          f"Run {SETUP} again (it installs the right Python).")

    check("uv installer", bool(shutil.which("uv")) or None, shutil.which("uv") or "not on PATH",
          f"Run {SETUP}. If it was just installed, close and reopen the terminal.")

    try:
        import pymupdf as fitz
        check("PDF library (PyMuPDF)", True, fitz.VersionBind)
    except ImportError:
        check("PDF library (PyMuPDF)", False, "not installed", f"Run {SETUP}.")

    browser_ok = False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = Path(p.chromium.executable_path)
        browser_ok = exe.exists()
        check("Browser for ScoutsTracker", browser_ok, str(exe) if browser_ok else "Chromium not downloaded",
              "Run: uv run playwright install chromium   (or run " + SETUP + " again)")
    except ImportError:
        check("Browser for ScoutsTracker", False, "Playwright not installed", f"Run {SETUP}.")
    except Exception as e:  # noqa: BLE001
        check("Browser for ScoutsTracker", False, str(e)[:200], f"Run {SETUP} again.")

    if TEMPLATE_PDF.exists():
        try:
            import pymupdf as fitz
            with fitz.open(TEMPLATE_PDF) as d:
                n = len(d)
            check("Passport template", n == 51, f"{TEMPLATE_PDF.name}: {n} pages",
                  "The template PDF looks different from the one this tool was built for "
                  "(expected 51 pages). Re-download the tool.")
        except Exception as e:  # noqa: BLE001
            check("Passport template", False, f"can't open: {e}", "Re-download the tool.")
    else:
        check("Passport template", False, f"missing {TEMPLATE_PDF}", "Re-download the tool.")

    try:
        from template_ext import Fonts
        fonts = Fonts.detect()
        check("Aptos font (stage 4+ pages)", None if fonts.is_fallback else True,
              "Helvetica will be used instead" if fonts.is_fallback else fonts.body[1],
              "Optional. Install Microsoft Office, or copy Aptos.ttf, Aptos-Bold.ttf, "
              f"Aptos-Narrow.ttf and Aptos-Narrow-Bold.ttf into {FONTS_DIR}")
    except Exception as e:  # noqa: BLE001
        check("Aptos font (stage 4+ pages)", None, str(e)[:200])

    try:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        probe = WORKSPACE / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        check("Private data folder", True, str(WORKSPACE))
    except OSError as e:
        check("Private data folder", False, f"{WORKSPACE}: {e}",
              "Make sure the folder isn't read-only, or set PASSPORT_DATA to another folder.")
    if any(s in str(WORKSPACE) for s in ("OneDrive", "iCloud", "Mobile Documents", "Dropbox")):
        check("Private data folder sync", None, "inside a cloud-synced folder",
              "Cub records and your login will be uploaded to the cloud. "
              "Consider setting PASSPORT_DATA to a local folder.")

    enc = (sys.stdout.encoding or "").lower()
    check("Console text", "utf" in enc or None, enc or "unknown",
          "Ticks may show as '?' in the terminal. Passports are not affected.")

    try:
        socket.create_connection(("scoutstracker.ca", 443), timeout=5).close()
        check("Internet (scoutstracker.ca)", True, "reachable")
    except OSError as e:
        check("Internet (scoutstracker.ca)", False, str(e), "Check your internet connection.")

    has_profile = PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())
    check("ScoutsTracker login saved", has_profile, str(PROFILE_DIR) if has_profile else "never logged in",
          f"Run {LOGIN} and sign into ScoutsTracker in the window that opens.")
    if online and has_profile and browser_ok:
        try:
            from scrape.fetch import connect
            from scrape.session import open_tracker
            with open_tracker(headless=True) as page:
                connect(page, timeout_s=40)
            check("ScoutsTracker login still valid", True, "connected as Scouter")
        except SystemExit as e:
            check("ScoutsTracker login still valid", False, str(e),
                  f"Run {LOGIN} and sign in again (the security PIN expires every so often).")
        except Exception as e:  # noqa: BLE001
            check("ScoutsTracker login still valid", False, str(e)[:200], f"Run {LOGIN} and sign in again.")

    data_dirs = sorted(p for p in DATA_DIR.glob("20*-*-*") if (p / "raw").is_dir())
    if data_dirs:
        latest = data_dirs[-1]
        missing = [f for f in ("tracking.csv", "stage_signoffs.csv", "cub_stats.csv",
                               "oas_requirements.json", "roster.json") if not (latest / f).exists()]
        age = (datetime.now() - datetime.strptime(latest.name, "%Y-%m-%d")).days
        if missing:
            check("Latest ScoutsTracker data", False, f"{latest.name}: missing {', '.join(missing)}",
                  f"Run {RUN} again.")
        else:
            check("Latest ScoutsTracker data", True if age <= 7 else None,
                  f"{latest.name} ({age} days old)", f"Run {RUN} to fetch fresh data.")
    else:
        check("Latest ScoutsTracker data", None, "none yet", f"Run {RUN}.")

    try:
        import print_passports
        printers, default = print_passports.list_printers()
        check("Printer", True if printers else None,
              f"{len(printers)} found, default: {default or 'none'}" if printers else "none found",
              "Optional: add a printer in your computer's settings to print from the tool.")
        if IS_WIN and printers:
            check("Exact-size printing (SumatraPDF)", True if print_passports.find_sumatra() else None,
                  "installed" if print_passports.find_sumatra() else "not installed",
                  "Optional: winget install SumatraPDF.SumatraPDF  (otherwise pages may print shrunk)")
    except Exception as e:  # noqa: BLE001
        check("Printer", None, str(e)[:200], "Optional.")

    out_dirs = sorted(p for p in OUT_DIR.glob("20*-*-*") if p.is_dir())
    if out_dirs:
        locked = []
        for pdf in out_dirs[-1].glob("*.pdf"):
            try:
                with pdf.open("r+b"):
                    pass
            except OSError:
                locked.append(pdf.name)
        check("Passports not open elsewhere", not locked,
              f"{len(locked)} passport PDF(s) open" if locked else out_dirs[-1].name,
              "Close these PDFs (e.g. in Acrobat) before running again.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Check the passport tool setup")
    ap.add_argument("--online", action="store_true", help="also test the saved ScoutsTracker login")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    run_checks(a.online)

    if a.json:
        print(json.dumps(results, indent=1))
    else:
        icon = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}
        print("\nScouts Passport - setup check\n")
        for r in results:
            print(f"{icon[r['status']]} {r['check']}: {r['detail']}")
            if r["fix"]:
                print(f"       -> {r['fix']}")
        fails = sum(r["status"] == "fail" for r in results)
        warns = sum(r["status"] == "warn" for r in results)
        print(f"\n{fails} problem(s), {warns} warning(s).")
        if not fails:
            print("Ready to go." if not warns else "Ready to go (warnings are optional to fix).")
        else:
            print("\n" + SUPPORT)
    return 1 if any(r["status"] == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
