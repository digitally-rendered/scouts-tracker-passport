# Shared by the macOS .command launchers. Finds uv and moves to the tool folder.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
pause() { echo; read -r -p "Press Enter to close this window..." _; }
need_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "The tool isn't set up yet. Double-click setup.command first."
    pause; exit 1
  fi
}
