#!/bin/bash
# Check that everything is set up; explains how to fix any problem.
source "$(dirname "$0")/launchers/_common.sh"
need_uv
uv run python doctor.py --online
pause
