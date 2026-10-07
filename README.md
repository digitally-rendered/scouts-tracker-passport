# Scouts Passport

Makes a filled-in **Cub passport** for every Cub in your Pack, straight from ScoutsTracker:
ticks, stage sign-offs (date + Scouter), nights at camp, the OAS overview grid, and
extra pages for **stage 4 and up** in the same style as the printed booklet. Then it
checks every passport and makes a print-ready file.

## Install (once)

**Mac** — open *Terminal* and paste:

```
curl -fsSL https://raw.githubusercontent.com/digitally-rendered/scouts-tracker-passport/main/install.sh | sh
```

**Windows** — open *PowerShell* and paste:

```
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/digitally-rendered/scouts-tracker-passport/main/install.ps1 | iex"
```

You don't need anything installed first. The install line:

- downloads the tool from GitHub into a `ScoutsPassport` folder in your home folder
- installs **uv**, which installs and manages Python for this tool only
- installs Python 3.12 and the libraries (PyMuPDF for PDFs, Playwright to read ScoutsTracker)
- downloads a private copy of the Chromium browser, used only to read ScoutsTracker
- puts two shortcuts on your Desktop: **Scouts Passports** (opens the page) and **Check setup**

It takes a few minutes and about 500 MB. Run the same line again any time to update; your data is kept.
Optional: Microsoft Office provides the Aptos font used on the stage 4+ pages (see Troubleshooting).

At the end it opens a browser window: **sign into ScoutsTracker there yourself**
(as you normally would, including your PIN). The tool remembers the login; it never
sees or stores your password.

> Already have the folder (e.g. downloaded the zip from GitHub)? Double-click `setup.command` (Mac)
> or `setup.bat` (Windows) instead. Mac may say the file is from an "unidentified developer":
> right-click it → **Open**. Windows may show "Windows protected your PC": **More info → Run anyway**.

ScoutsTracker asks for your **security PIN** again every so often. When the page says it needs
you to sign in again, click **Sign into ScoutsTracker**, enter your PIN, then **Make passports** again.

## Make passports

Double-click **Scouts Passports** on your Desktop. A page opens in your web browser.

![The Scouts Passports page](docs/ui.png)

1. **First time, or when it asks for your PIN:** click **Sign into ScoutsTracker**. Sign in
   in the window that opens (email, password, PIN). It closes by itself when you're in.
2. Pick the highest OAS stage to include (normally **4**) and click **Make passports**.
   It gets the latest records from ScoutsTracker, makes every passport, and checks them.
3. When it says **Done**, click **Open print file**. The page also shows how many passports
   need attention; **Open check report** explains them.

Keep the small terminal window that opens with the page; closing it closes the tool.
Click **Close** at the bottom of the page when you're finished.

> Prefer the terminal? `run.command` / `run.bat` does the same without the page.

## Print

On the page, under **Print**:

1. Pick your printer (your default printer is already selected).
2. Click **Print a test sheet** first. One sheet comes out, so you can check the text is readable
   and the dashed lines are in the middle.
3. Click **Print all passports**. Each Cub prints as its own job (single-sided, letter, actual
   size), so their stacks stay separate. Under every page are the Cub's name and the page number.

Then for each Cub's stack:

1. Cut the whole stack along the dashed lines.
2. Stack the four piles: **top-left** on top, then **top-right**, then **bottom-left**, then **bottom-right**.
3. The pages are now in order. Staple or bind them.

> Windows: install the free **SumatraPDF** (`winget install SumatraPDF.SumatraPDF`) so pages print
> at exact size. Without it, Windows' default PDF app prints them and may shrink them slightly.
> To print by hand instead, open `print 4-up/ALL CUBS - print 4-up.pdf` and print it single-sided at
> "Actual size".

## Read the audit

`audit.html` lists every Cub:

- **ERROR** — something is missing from that passport. Don't print it; run again, and if it
  persists, use *Check setup* (or ask Claude: `/passport-doctor`).
- **WARN** — something to fix in ScoutsTracker, e.g. *all requirements ticked but stage not awarded*.
  Fix it in ScoutsTracker and run again.
- **INFO** — expected. E.g. *Scouter blank*: ScoutsTracker doesn't know who signed it (often a
  Beaver-era Scouter), so the date is filled and the name is left for you to sign.

## If something goes wrong

1. Double-click **Scouts Passports - Check setup**. Every problem comes with what to do.
2. See **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**. It covers install blocks on Mac and
   Windows, PIN and login expiry, PDFs left open, audit errors, fonts, and printing.
3. Still stuck? Contact **Drew Carmichael** at **drew.carmichael@gmail.com**, or
   [open an issue](https://github.com/digitally-rendered/scouts-tracker-passport/issues).
   Include the *Check setup* output, which contains no Cub information. **Never send passports,
   the audit, or anything from `ScoutsPassportData`.**

### With Claude Code

Open this folder in Claude Code and use:

| | |
|---|---|
| `/passport-setup` | install and sign in |
| `/passport-run` | make passports and explain the results |
| `/passport-doctor` | find and fix problems |
| `/passport-audit-explain` | explain the audit in plain language |

## Your data stays private

Everything about the Cubs — downloaded records, passports, the audit — and your saved
ScoutsTracker login live in **`ScoutsPassportData`** in your home folder, *not* in the
tool folder. You can share the tool folder; never share `ScoutsPassportData`.
(To keep it elsewhere, set the `PASSPORT_DATA` environment variable.)

Optional files in `ScoutsPassportData`:

- `scouter_names.json` — names for Scouters ScoutsTracker can't identify, e.g. `{"144726": "Jane Smith"}`.
  The IDs are listed when the tool runs.
- `fonts/` — copy `Aptos.ttf`, `Aptos-Bold.ttf`, `Aptos-Narrow.ttf`, `Aptos-Narrow-Bold.ttf`
  here if Microsoft Office isn't installed (otherwise stage 4+ pages use Helvetica).

## For maintainers

| Command | What it does |
|---|---|
| `uv run python passport.py ui` | the point-and-click page (`ui.py`, local only, secret-key URL) |
| `uv run python passport.py run [--stages 1-4] [--no-fetch]` | fetch → build → fill → audit |
| `uv run python print_passports.py [--list] [--dry-run] [--test-sheet] [--cub NAME] [--printer P]` | print the 4-up files, one job per Cub |
| `uv run --group dev pytest` | tests (synthetic Cubs, no real data); CI runs them on Mac/Windows/Linux |
| `uv run python passport.py login` | sign into ScoutsTracker (saved profile) |
| `uv run python doctor.py [--online] [--json]` | setup checks |
| `uv run python passport.py blank --stages 1-5` | blank extended passport (spares) |
| `./package.sh` | build `dist/scouts-passport.zip` (code only) to host for the installers |

Pipeline: `scrape/fetch.py` reads ScoutsTracker's offline database (IndexedDB) through a
saved, logged-in browser profile → `build_data.py` writes CSVs + requirement text →
`fill_passport.py` (with `template_ext.py` for stage 4+ pages and `print_layout.py` for 4-up
sheets) → `audit_passports.py`. Paths are in `paths.py`.

The installers download `main` from GitHub
(`https://github.com/digitally-rendered/scouts-tracker-passport`). To test a different
build, set `PASSPORT_ZIP_URL` (e.g. to a zip from `./package.sh`) before running the installer.

**Never commit Cub data.** `.gitignore` blocks the usual files, and the private workspace lives
outside the repo (`paths.py`).

## Contact

Drew Carmichael — drew.carmichael@gmail.com ·
[Issues](https://github.com/digitally-rendered/scouts-tracker-passport/issues) · MIT licensed.
