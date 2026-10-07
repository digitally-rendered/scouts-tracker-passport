#!/bin/bash
# Build dist/scouts-passport.zip containing ONLY code (no Cub data), ready to
# host for install.sh / install.ps1 (e.g. as a GitHub release asset).
set -euo pipefail
cd "$(dirname "$0")"
rm -rf dist && mkdir -p dist/scouts-passport
FILES=(*.py scrape/*.py tests/*.py tests/fixtures/* tests/ci/* legacy/* launchers/* docs/* *.command *.bat install.sh install.ps1
       pyproject.toml uv.lock .python-version README.md .gitignore
       "Passport 2026 Printable Generic.pdf")
for f in "${FILES[@]}"; do
  [ -e "$f" ] && mkdir -p "dist/scouts-passport/$(dirname "$f")" && cp -p "$f" "dist/scouts-passport/$f"
done
mkdir -p dist/scouts-passport/.claude && cp -R .claude/skills dist/scouts-passport/.claude/
# Safety net: refuse to ship anything that looks like private data.
if find dist/scouts-passport \( -name '*.csv' -o -name 'scoutstracker.json' -o -name 'fill_log.json' \
     -o -path '*browser-profile*' -o -name 'settings.local.json' \) | grep -q .; then
  echo "Refusing to package: private data found in dist/"; exit 1
fi
(cd dist && zip -qr scouts-passport.zip scouts-passport)
echo "Built dist/scouts-passport.zip ($(du -h dist/scouts-passport.zip | cut -f1))"
