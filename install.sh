#!/bin/sh
# Scouts Passport installer for macOS (and Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/digitally-rendered/scouts-tracker-passport/main/install.sh | sh
#
# Options (env vars): PASSPORT_HOME (install folder), PASSPORT_ZIP_URL (source zip),
# PASSPORT_NO_SHORTCUTS=1 (no Desktop launchers), PASSPORT_NONINTERACTIVE=1 (no prompts).
#
# Downloads the tool into ~/ScoutsPassport, installs uv + Python + libraries +
# a private browser, and puts launchers on the Desktop. Re-run to update; your
# private data (~/ScoutsPassportData) is never touched.
set -eu

# Where to download the tool from (a .zip of this folder). Set once by whoever
# publishes the tool, or override:  PASSPORT_ZIP_URL=... sh install.sh
ZIP_URL="${PASSPORT_ZIP_URL:-https://github.com/digitally-rendered/scouts-tracker-passport/archive/refs/heads/main.zip}"
INSTALL_DIR="${PASSPORT_HOME:-$HOME/ScoutsPassport}"

say() { printf '\n== %s ==\n' "$1"; }
die() {
  printf '\nInstall failed: %s\n' "$1" >&2
  printf 'Help: https://github.com/%s/blob/main/docs/TROUBLESHOOTING.md\n' "digitally-rendered/scouts-tracker-passport" >&2
  printf 'Or email Drew Carmichael: drew.carmichael@gmail.com\n' >&2
  exit 1
}

command -v curl >/dev/null || die "curl is required"
command -v unzip >/dev/null || die "unzip is required"

say "Downloading Scouts Passport"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$ZIP_URL" -o "$TMP/tool.zip" || die "couldn't download $ZIP_URL"
unzip -q "$TMP/tool.zip" -d "$TMP/x" || die "download wasn't a valid zip"
SRC="$TMP/x"
[ -f "$SRC/passport.py" ] || SRC=$(dirname "$(find "$TMP/x" -maxdepth 2 -name passport.py | head -1)")
[ -f "$SRC/passport.py" ] || die "zip doesn't contain the passport tool"

say "Installing into $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
# Replace the code but keep the Python environment (.venv) to make updates fast.
find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name .venv -exec rm -rf {} +
cp -R "$SRC"/. "$INSTALL_DIR"/
chmod +x "$INSTALL_DIR"/*.command 2>/dev/null || true

if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (Python manager from astral.sh)"
  curl -LsSf https://astral.sh/uv/install.sh | sh || die "uv install failed"
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:$PATH"

cd "$INSTALL_DIR"
say "Installing Python and libraries"
uv sync || die "uv sync failed"
say "Installing the browser used to read ScoutsTracker"
uv run playwright install chromium || die "browser install failed"

if [ "$(uname)" = "Darwin" ] && [ -d "$HOME/Desktop" ] && [ -z "${PASSPORT_NO_SHORTCUTS:-}" ]; then
  say "Adding launchers to your Desktop"
  for pair in "Scouts Passports:run" "Scouts Passports - Sign in:login" "Scouts Passports - Check setup:doctor"; do
    name=${pair%%:*}; target=${pair#*:}
    printf '#!/bin/bash\nexec "%s/%s.command" "$@"\n' "$INSTALL_DIR" "$target" > "$HOME/Desktop/$name.command"
    chmod +x "$HOME/Desktop/$name.command"
  done
fi

say "Checking the setup"
uv run python doctor.py || true

# stdin is the curl pipe, so ask on the terminal directly.
if [ -z "${PASSPORT_NONINTERACTIVE:-}" ] && [ -r /dev/tty ] && [ ! -d "${PASSPORT_DATA:-$HOME/ScoutsPassportData}/browser-profile" ]; then
  printf '\nSign into ScoutsTracker now? [Y/n] '
  read -r ans < /dev/tty || ans=n
  case "$ans" in [Nn]*) ;; *) uv run python passport.py login < /dev/tty ;; esac
fi

cat <<EOF

Done! To make passports, double-click "Scouts Passports" on your Desktop
(or run: $INSTALL_DIR/run.command). Your data stays private in
${PASSPORT_DATA:-$HOME/ScoutsPassportData}.
EOF
