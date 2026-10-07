---
name: passport-run
description: Make (or remake) every Cub's passport from fresh ScoutsTracker data, check them, and explain the audit. Use when asked to generate, update, refresh or print passports.
---
# Make the passports

Most leaders use the page: `uv run python passport.py ui` (the **Scouts Passports** Desktop
shortcut). Suggest it for people who prefer clicking. The steps below are the terminal equivalent.

1. Ask which OAS stages to include if they didn't say. Default **1-4** for Cubs
   (the template always includes 1-3; pages for 4+ are generated in the same style).
2. Run: `uv run python passport.py run --stages 1-<N> --no-open`
   - Add `--no-fetch` only if they explicitly want to reuse today's data.
   - If it says not logged in / PIN needed: run `uv run python passport.py login` and ask
     them to sign in in the window that opens. Never handle their password or PIN yourself.
3. Summarise the result from the output (and `audit.csv` in the output folder):
   - ERROR count — must be zero before printing; explain each one.
   - WARN — things to fix in ScoutsTracker (e.g. all requirements ticked but stage not awarded).
   - INFO — expected (blank Scouter names to sign by hand, auto-ticked boxes).
4. Tell them where things are (`uv run python passport.py where` prints the folder):
   - `out/<date>/<Name> - Passport 2026.pdf` — the passport
   - `out/<date>/print 4-up/` — **what to print**: 4 pages per letter sheet, single-sided.
     Cut each Cub's stack on the dashed lines, then stack the piles top-left, top-right,
     bottom-left, bottom-right — pages come out in order. Every page has the Cub's name underneath.
   - `out/<date>/audit.html` — the check report
Use `/passport-audit-explain` for detail on any audit finding.

## Getting help
If something can't be fixed, point the person to `docs/TROUBLESHOOTING.md` and to
**Drew Carmichael — drew.carmichael@gmail.com** (or https://github.com/digitally-rendered/scouts-tracker-passport/issues).
They should send the `doctor.py` output and the error message, and **never** passports,
audit files, or anything from `ScoutsPassportData` (Cub personal information).
