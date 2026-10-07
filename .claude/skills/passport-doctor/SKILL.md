---
name: passport-doctor
description: Diagnose problems with the Scouts passport tool on Mac or Windows (won't start, fetch fails, login expired, fonts, PDFs locked). Use whenever something about the passport tool isn't working.
---
# Diagnose the passport tool

1. Run `uv run python doctor.py --online --json` from the tool folder
   (if `uv` itself isn't found, the tool isn't set up — use `/passport-setup`).
2. For each item with status `fail` or `warn`, explain in one plain sentence what it means
   and give the `fix`. Offer to run safe fixes yourself and ask before running them:
   - missing libraries/browser → `uv sync` / `uv run playwright install chromium`
   - login expired → `uv run python passport.py login` (the person signs in themselves;
     never ask for or type their password/PIN)
   - PDFs locked → ask them to close the PDFs, then re-run
   - Aptos font warning → optional; Office provides it, or copy Aptos*.ttf into
     `~/ScoutsPassportData/fonts`
   - "asking for your security PIN" → normal periodic PIN expiry: run `uv run python passport.py login`
   - fetch connects to the wrong account → the person needs a Cubs Scouter login in ScoutsTracker
   - Windows SmartScreen / Mac Gatekeeper blocks a launcher → see docs/TROUBLESHOOTING.md "Installing"
3. Re-run the doctor and confirm everything passes.
4. For anything else, look it up in `docs/TROUBLESHOOTING.md`.
Don't edit the Python code to work around a failing check unless asked — report it instead.

## Getting help
If something can't be fixed, point the person to `docs/TROUBLESHOOTING.md` and to
**Drew Carmichael — drew.carmichael@gmail.com** (or https://github.com/digitally-rendered/scouts-tracker-passport/issues).
They should send the `doctor.py` output and the error message, and **never** passports,
audit files, or anything from `ScoutsPassportData` (Cub personal information).
