---
name: passport-audit-explain
description: Explain the passport audit findings in plain language and what a leader should do about each (in ScoutsTracker or by hand). Use after a passport run or when someone asks about audit.html / audit.csv.
---
# Explain the audit

Read the newest `~/ScoutsPassportData/out/<date>/audit.csv` (or `PASSPORT_DATA`). Columns: level, cub, check, detail.

Group by level and explain briefly:

| check | meaning | what to do |
|---|---|---|
| sign-off missing / tick not placed / read-back mismatch / print file missing | the passport is missing something | ERROR — don't print; re-run, and if it persists run `/passport-doctor` and report it |
| no requirements | stage awarded but ScoutsTracker returned no requirement list | ERROR — re-fetch; report if it persists |
| badge not awarded | every requirement is ticked but the stage isn't awarded in ScoutsTracker | award the stage in ScoutsTracker, then re-run |
| earned above range | Cub earned a stage higher than the passport includes | re-run with a higher stage range |
| scouter blank | ScoutsTracker can't name who signed it (often a Beaver-era Scouter) | sign by hand, or add `{"<id>": "Name"}` to `scouter_names.json` (IDs are listed by build_data.py) |
| auto-ticked | stage was awarded, so remaining boxes were ticked | nothing |
| camp nights | more nights than the 7 boxes on page 6 | nothing (or write the total by hand) |
| stale data | fetched more than 7 days ago | re-run |

Keep names in the conversation only; don't copy the audit into other files or services.

## Getting help
If something can't be fixed, point the person to `docs/TROUBLESHOOTING.md` and to
**Drew Carmichael — drew.carmichael@gmail.com** (or https://github.com/digitally-rendered/scouts-tracker-passport/issues).
They should send the `doctor.py` output and the error message, and **never** passports,
audit files, or anything from `ScoutsPassportData` (Cub personal information).
