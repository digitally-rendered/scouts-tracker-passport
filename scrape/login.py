"""Open a browser window so you can log into ScoutsTracker once.

The login is saved in .browser-profile/ and reused by the fetch scripts.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrape.session import open_tracker, is_logged_in  # noqa: E402

TIMEOUT_S = 600


def main() -> int:
    with open_tracker(headless=False) as page:
        print("A browser window has opened. Log into ScoutsTracker (Cubs) there.")
        deadline = time.time() + TIMEOUT_S
        while time.time() < deadline:
            try:
                if is_logged_in(page):
                    page.wait_for_timeout(5000)  # let the app finish its first sync
                    print("Logged in - session saved. You can run the fetch step now.")
                    return 0
            except Exception:
                pass
            time.sleep(2)
    print("Timed out waiting for login (10 minutes). Run this again when ready.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
