"""Scouts passport tool - one entry point for everything.

    python passport.py ui          open the point-and-click page in your browser
    python passport.py run [--stages 1-4] [--no-fetch] [--no-open]
        fetch fresh data from ScoutsTracker, make every Cub's passport,
        audit them, and open the results
    python passport.py login       sign into ScoutsTracker (once; saved privately)
    python passport.py doctor      check the setup (add --online to test the login)
    python passport.py blank       make a blank extended passport for spares
    python passport.py where       show where the private data is kept

Launchers (run.command / run.bat etc.) call this with `uv run`.
"""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from paths import DATA_DIR, OUT_DIR, SUPPORT, WORKSPACE  # noqa: E402

DEFAULT_STAGES = "1-4"


def step(title: str, script: str, *args: str) -> int:
    print(f"\n=== {title} ===", flush=True)
    return subprocess.call([sys.executable, str(HERE / script), *args])


def open_path(p: Path) -> None:
    try:
        if platform.system() == "Windows":
            os.startfile(str(p))  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.call(["open", str(p)])
        else:
            subprocess.call(["xdg-open", str(p)])
    except Exception as e:  # noqa: BLE001
        print(f"(couldn't open {p}: {e})")


def ask_stages() -> str:
    if not sys.stdin.isatty():
        return DEFAULT_STAGES
    ans = input(f"Highest OAS stage to include in the passports (3-9) [{DEFAULT_STAGES[-1]}]: ").strip()
    if not ans:
        return DEFAULT_STAGES
    if ans.isdigit() and 3 <= int(ans) <= 9:
        return f"1-{ans}"
    print(f"Didn't understand {ans!r}; using {DEFAULT_STAGES}")
    return DEFAULT_STAGES


def cmd_run(a) -> int:
    stages = a.stages or ask_stages()
    today = date.today().isoformat()
    data_dir = DATA_DIR / today
    out_dir = OUT_DIR / today

    if not a.no_fetch:
        if step("1/4  Fetching from ScoutsTracker", "scrape/fetch.py", "--out", str(data_dir)):
            print("\nFetching failed. If it mentions logging in or your PIN, double-click "
                  "'Scouts Passports - Sign in' and sign in again, then re-run.\n" + SUPPORT)
            return 1
    elif not (data_dir / "raw").is_dir():
        from build_data import latest_data_dir
        data_dir = latest_data_dir()
        print(f"Using existing data from {data_dir.name}")
    if step("2/4  Preparing data", "build_data.py", str(data_dir)):
        return 1
    if step(f"3/4  Making passports (stages {stages})", "fill_passport.py", "--all",
            "--stages", stages, "--data", str(data_dir), "--out", str(out_dir)):
        return 1
    rc = step("4/4  Checking passports", "audit_passports.py",
              "--data", str(data_dir), "--out", str(out_dir))

    print("\n" + ("All passports passed the audit." if rc == 0 else
                  "Some passports have ERRORS - see the audit report before printing.\n" + SUPPORT))
    print(f"Passports: {out_dir}")
    if not a.no_open:
        open_path(out_dir / "audit.html")
        open_path(out_dir)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="Scouts passport tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch, fill, audit")
    r.add_argument("--stages", help=f"OAS stage range, e.g. {DEFAULT_STAGES} (asks if omitted)")
    r.add_argument("--no-fetch", action="store_true", help="reuse the latest fetched data")
    r.add_argument("--no-open", action="store_true", help="don't open the results")
    sub.add_parser("ui", help="open the point-and-click page")
    sub.add_parser("login", help="sign into ScoutsTracker")
    d = sub.add_parser("doctor", help="check setup")
    d.add_argument("--online", action="store_true")
    d.add_argument("--json", action="store_true")
    b = sub.add_parser("blank", help="blank extended passport")
    b.add_argument("--stages", default=DEFAULT_STAGES)
    sub.add_parser("where", help="show private data folder")
    a = ap.parse_args()

    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "ui":
        import ui
        return ui.main()
    if a.cmd == "login":
        return subprocess.call([sys.executable, str(HERE / "scrape/login.py")])
    if a.cmd == "doctor":
        extra = (["--online"] if a.online else []) + (["--json"] if a.json else [])
        return subprocess.call([sys.executable, str(HERE / "doctor.py"), *extra])
    if a.cmd == "blank":
        out = OUT_DIR / f"blank-passport-stages-{a.stages}.pdf"
        rc = subprocess.call([sys.executable, str(HERE / "template_ext.py"),
                              "--stages", a.stages, "--out", str(out)])
        if rc == 0:
            open_path(out)
        return rc
    if a.cmd == "where":
        print(WORKSPACE)
        open_path(WORKSPACE)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
