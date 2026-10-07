#!/bin/bash
# One-time setup: installs uv (Python manager), Python, the PDF library and a
# private browser for ScoutsTracker. Safe to run again any time.
source "$(dirname "$0")/launchers/_common.sh"
echo "== Scouts Passport setup =="
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv (Python manager from astral.sh)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "uv install failed"; pause; exit 1; }
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "Installing Python and libraries..."
uv sync || { echo "Setup failed (uv sync)."; pause; exit 1; }
echo "Installing the browser used to read ScoutsTracker..."
uv run playwright install chromium || { echo "Browser install failed."; pause; exit 1; }
chmod +x ./*.command 2>/dev/null
uv run python doctor.py
echo
read -r -p "Sign into ScoutsTracker now? [Y/n] " ans
if [[ ! "$ans" =~ ^[Nn] ]]; then uv run python passport.py login; fi
pause
