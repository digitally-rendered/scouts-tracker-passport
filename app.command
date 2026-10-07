#!/bin/bash
# Open the Scouts Passports page in your browser.
source "$(dirname "$0")/launchers/_common.sh"
need_uv
uv run python ui.py
