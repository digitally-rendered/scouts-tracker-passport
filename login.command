#!/bin/bash
# Sign into ScoutsTracker (a browser window opens; type your details there).
source "$(dirname "$0")/launchers/_common.sh"
need_uv
uv run python passport.py login
pause
