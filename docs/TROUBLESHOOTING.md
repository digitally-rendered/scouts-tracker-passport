# Troubleshooting

**Start here:** on the Scouts Passports page click **Check setup**, or double-click
**Scouts Passports - Check setup** on your Desktop
(or `doctor.command` / `doctor.bat` in the `ScoutsPassport` folder). It checks everything
and tells you how to fix each problem. In Claude Code, `/passport-doctor` does the same and
can run the fixes for you.

Still stuck? See [Getting help](#getting-help) at the bottom.

---

## Installing

### Mac: "cannot be opened because it is from an unidentified developer"
This happens if you downloaded the zip in a browser instead of using the `curl` install line.
- Right-click (or Control-click) the `.command` file → **Open** → **Open**. You only need to do this once per file.
- Or open Terminal and run: `xattr -dr com.apple.quarantine ~/ScoutsPassport`
- Or use the one-line installer from the README instead; it avoids this.

### Mac: "Permission denied" when double-clicking a `.command` file
Open Terminal and run: `chmod +x ~/ScoutsPassport/*.command`

### Windows: "Windows protected your PC" (blue SmartScreen box)
Click **More info** → **Run anyway**. This appears the first time a downloaded `.bat` is run.

### Windows: "running scripts is disabled on this system"
PowerShell is blocking the installer. Paste the install line **exactly** as written in the
README. It includes `-ExecutionPolicy ByPass`, which allows just this one script to run.

### "uv is not recognized" / "command not found: uv" right after installing
uv was installed but this window doesn't know about it yet. **Close the Terminal/PowerShell
window, open a new one**, and run the install line again (it's safe to repeat).

### The installer can't download (work laptop, school network, firewall)
The installer downloads from `github.com`, `astral.sh` (uv), `pypi.org` (libraries) and
`playwright.azureedge.net` / `cdn.playwright.dev` (the browser). Some managed networks block these.
Try a home network, or ask your IT team to allow them.

### "Browser install failed"
Run the setup launcher again (`setup.command` / `setup.bat`). If it still fails, check that
you have about 500 MB of free disk space.

---

## Signing into ScoutsTracker

### "ScoutsTracker is asking for your security PIN"
ScoutsTracker asks for your **security PIN** again every so often. This is normal.
On the Scouts Passports page click **Sign into ScoutsTracker**, enter your PIN in the window that
opens, click **Connect**, and wait for the window to close by itself. Then click **Make passports** again.

### "Not logged into ScoutsTracker"
Your saved login has expired or was never created. Click **Sign into ScoutsTracker** on the page and log in
the way you normally do (email, password, PIN). The tool never sees or stores your password;
the browser window keeps the login in your private data folder.

### The sign-in window closed before I finished, or "Timed out waiting for login"
The window waits 10 minutes. Just run **Sign in** again.

### I have several ScoutsTracker accounts (Group, Cubs, Parent…)
The tool always connects as **Cubs (as Scouter)**. If you don't have a Scouter login for the
Cub section, ask your Group Commissioner or Section Contact to add you.

### Fewer Cubs than expected / a Cub is missing
Only **active Cubs** get a passport: youth members whose status is active and who haven't
left or moved up. Check the Cub's status in ScoutsTracker. Cubs who have moved up to Scouts
won't appear.

---

## Making passports

### The page doesn't open / "This site can't be reached"
The page only works while its small terminal window is open. Double-click **Scouts Passports**
again. If the browser didn't open by itself, copy the address shown in that terminal window into
your browser. Bookmarks to the page don't work later, because the address changes each time
(it includes a secret key).

### "Open the page from the Scouts Passports shortcut"
You opened an old or bookmarked address. Close the tab and double-click **Scouts Passports** again.

### The buttons do nothing / "The tool isn't running any more"
The page only works while its terminal window is open. Close the tab and double-click
**Scouts Passports** again to get a fresh page.

### Finding out what happened
Everything the page runs (making passports, signing in, printing) is written to
`ScoutsPassportData/logs/<date>.log`. The log has no passwords. It does name Cubs, so read it
yourself rather than sending it on. Send only the error lines if you ask for help.

### The page says "Something is already running"
Wait for the current task to finish (the spinner shows what it's doing). The sign-in task waits
up to 10 minutes for you to finish signing in.

### "PDF is open" / "Permission denied" when saving / "Passports not open elsewhere" fails
Close the passports in Acrobat, Preview or your browser, then run again. Windows locks a PDF
while it is open.

### The audit says ERROR
Something is missing from that Cub's passport, so don't print it yet.
1. Run again (a network hiccup during the fetch can cause this).
2. If it's still there, run **Check setup** and contact Drew (below) with the ERROR line.
   The line only says what is missing (e.g. "Camping Skills 2 earned but not written on the
   passport"), so you can share it.

### The audit says WARN: "all requirements ticked but stage not awarded"
In ScoutsTracker every requirement is ticked, but nobody has awarded the stage yet. Award it
in ScoutsTracker (Badges → the Cub → the stage), then run again.

### Scouter name is blank on some sign-offs ("scouter blank")
ScoutsTracker records who signed it but won't show the name to the Cub section. This is usually a
Beaver-era Scouter. Either sign by hand, or add names to `scouter_names.json` in your private data
folder. The tool prints the IDs it couldn't name when it runs, for example:
```json
{"144726": "Jane Smith"}
```

### Stage 4+ pages look slightly different / "Aptos font not found"
The original booklet uses the **Aptos** font, which comes with Microsoft Office. Without
Office, stage 4+ pages use Helvetica instead, which works but looks a little different.
To match exactly, copy `Aptos.ttf`, `Aptos-Bold.ttf`, `Aptos-Narrow.ttf` and `Aptos-Narrow-Bold.ttf`
from a computer that has Office into the `fonts` folder inside your private data folder.

### More camp nights than boxes on page 6
Page 6 has 7 boxes. The audit lists the real total; write it in by hand if you like.

### The data is old ("stale data")
Click **Make passports** with **Get the latest from ScoutsTracker** ticked.

---

## Printing

### Printing from the page
Under **Print**, choose your printer, click **Print a test sheet**, then **Print all passports**.
Each Cub is sent as its own print job. From a terminal: `uv run python print_passports.py --dry-run`
shows what would print; drop `--dry-run` to print, and add `--cub "First Last"` for one Cub.

### Booklet backs come out upside down, or on the wrong sheet
That depends on how your printer feeds paper, which is why there's a test sheet. On the page
(booklet layout, one-sided printer): tick **Turn backs upside down** if the back was upside
down, and **Reverse backs** if the backs landed on the wrong sheets. Then repeat
**Test: print front** / **Test: print back** until the folded test sheet is right.
The page remembers both settings. Reload the printed stack **printed side up**, turned over like a page.

### "This printer can't print both sides by itself"
From the terminal, a booklet on a one-sided printer needs two passes:
`--layout booklet --pass fronts`, reload the paper, then `--layout booklet --pass backs`.
The page does this for you, one Cub at a time.

### "No printers found"
Add the printer in your computer's settings first (Mac: System Settings → Printers & Scanners;
Windows: Settings → Bluetooth & devices → Printers & scanners), then reopen the page.

### Pages come out shrunk or not centred (Windows)
Without SumatraPDF, Windows hands the file to your default PDF app, which may "fit to page".
Install SumatraPDF (`winget install SumatraPDF.SumatraPDF`, free) and print again. The tool uses
it automatically.

### Some passports didn't print
The page shows which ones failed (open **Show details**). Fix the printer (paper, jam, offline),
then print just those Cubs: `uv run python print_passports.py --cub "First Last"`.

### Which file do I print by hand?
`print 4-up/ALL CUBS - print 4-up.pdf`, **single-sided**, on letter paper, at **"Actual size" / 100%**
(not "Fit to page"). Each sheet has 4 passport pages, and under every page is the Cub's
name and page number.

### Cutting and putting pages in order
Do one Cub at a time (their name is printed at the bottom of each of their sheets):
1. Cut the whole stack along the dashed lines.
2. Put the piles together: **top-left** on top, then **top-right**, then **bottom-left**, then **bottom-right**.
3. The pages are now in order.

### The text is too small
Four pages per sheet prints each page at about 65% size. Print one sheet first to check.
To print full size instead, print the individual passport PDF at 1 page per sheet.

### I need spare blank passports
`uv run python passport.py blank --stages 1-4` (in the `ScoutsPassport` folder) makes a blank
one that includes the stage 4 pages.

---

## Where is everything?

| What | Where |
|---|---|
| The tool | `ScoutsPassport` in your home folder |
| Your private data (Cub records, passports, audit, login) | `ScoutsPassportData` in your home folder |
| Today's passports | `ScoutsPassportData/out/<date>/` |
| Print files | `ScoutsPassportData/out/<date>/print 4-up/` |

`uv run python passport.py where` opens the private data folder.

**Never share or upload `ScoutsPassportData`.** It contains the Cubs' records and your
ScoutsTracker login. Uninstalling = delete both folders and the Desktop shortcuts.

---

## Getting help

- **Drew Carmichael** — drew.carmichael@gmail.com
- Report a problem: <https://github.com/digitally-rendered/scouts-tracker-passport/issues>

Please include:
1. Mac or Windows.
2. The output of **Check setup** (copy the text or take a screenshot). It contains no Cub information.
3. The error message you saw.

Please **don't** send passports, `audit.html`, or anything from `ScoutsPassportData`; those
contain the Cubs' personal information.
