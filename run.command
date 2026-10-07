#!/bin/bash
# Fetch fresh data from ScoutsTracker, make all passports, check them.
source "$(dirname "$0")/launchers/_common.sh"
need_uv
uv run python passport.py run "$@"
pause
