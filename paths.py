"""Where private data lives - kept OUTSIDE the code folder.

Everything about the Cubs (ScoutsTracker exports, filled passports, audits)
and the saved ScoutsTracker login goes in one private workspace folder, so the
code folder can be shared or copied without any personal information.

Default: ~/ScoutsPassportData   (override with the PASSPORT_DATA env variable)

    ScoutsPassportData/
        data/<date>/           fetched ScoutsTracker data + derived CSVs
        out/<date>/            filled passports, fill_log.json, audit.html
        browser-profile/       saved ScoutsTracker login (keep private!)
        scouter_names.json     optional names for unresolved Scouter IDs
        fonts/                 optional Aptos*.ttf files (if Office isn't installed)
"""
import os
import sys
from pathlib import Path

# Windows consoles default to cp1252 and crash on ✓ / ❑ - force UTF-8 output.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

CODE_DIR = Path(__file__).resolve().parent
WORKSPACE = Path(os.environ.get("PASSPORT_DATA") or Path.home() / "ScoutsPassportData")
DATA_DIR = WORKSPACE / "data"
OUT_DIR = WORKSPACE / "out"
PROFILE_DIR = WORKSPACE / "browser-profile"
SCOUTER_NAMES = WORKSPACE / "scouter_names.json"
FONTS_DIR = WORKSPACE / "fonts"  # optional: drop Aptos*.ttf here if Office isn't installed
TEMPLATE_PDF = CODE_DIR / "Passport 2026 Printable Generic.pdf"

REPO_URL = "https://github.com/digitally-rendered/scouts-tracker-passport"
SUPPORT = ("Need help? See " + REPO_URL + "/blob/main/docs/TROUBLESHOOTING.md\n"
           "or contact Drew Carmichael: drew.carmichael@gmail.com "
           "(send the output of the 'Check setup' launcher - never Cub data).")
