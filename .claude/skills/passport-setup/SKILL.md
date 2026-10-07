---
name: passport-setup
description: Set up the Scouts passport tool on this computer (Mac or Windows) and sign into ScoutsTracker. Use when someone is installing the tool, it says "not set up yet", or uv/Python/browser are missing.
---
# Set up the passport tool

Easiest path for a new person (downloads code + everything else):
- Mac: `curl -fsSL https://raw.githubusercontent.com/digitally-rendered/scouts-tracker-passport/main/install.sh | sh`
- Windows: `powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/digitally-rendered/scouts-tracker-passport/main/install.ps1 | iex"`

If the code folder is already here, set up the dependencies as below.

The scripts do all the work; your job is to run them and explain results in plain language.

1. Detect the OS. Run the setup script from the tool folder **non-interactively**:
   - macOS/Linux: `uv sync && uv run playwright install chromium`
     (if `uv` is missing: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then add `~/.local/bin` to PATH for this shell)
   - Windows (PowerShell): same commands; if uv is missing: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. Run `uv run python doctor.py` and summarise: what passed, what needs fixing, and the fix.
3. ScoutsTracker sign-in: run `uv run python passport.py login`. It opens a browser window —
   tell the person to **sign in themselves** in that window (email, password, PIN).
   **Never ask for, type, or store their password or PIN**, and never put credentials in a file.
4. When login finishes, run `uv run python doctor.py --online` to confirm.

Private data (Cub records, passports, the login) lives in `~/ScoutsPassportData`
(or `PASSPORT_DATA`), never in the tool folder. Don't copy it anywhere else.

## Common setup problems
- `uv` not found right after installing → open a new terminal (PATH updates only in new windows).
- Mac "unidentified developer" on a `.command` file → right-click → Open, or
  `xattr -dr com.apple.quarantine <tool folder>`.
- Windows "Windows protected your PC" → More info → Run anyway. "Scripts disabled" → use the
  install line with `-ExecutionPolicy ByPass`.
- Download blocked (managed network) → needs github.com, astral.sh, pypi.org, playwright CDN.
- "asking for your security PIN" → ScoutsTracker's PIN expired; run `passport.py login` and let
  the person enter it.

## Getting help
If something can't be fixed, point the person to `docs/TROUBLESHOOTING.md` and to
**Drew Carmichael — drew.carmichael@gmail.com** (or https://github.com/digitally-rendered/scouts-tracker-passport/issues).
They should send the `doctor.py` output and the error message, and **never** passports,
audit files, or anything from `ScoutsPassportData` (Cub personal information).
