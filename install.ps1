# Scouts Passport installer for Windows.
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/digitally-rendered/scouts-tracker-passport/main/install.ps1 | iex"
#
# Downloads the tool into %USERPROFILE%\ScoutsPassport, installs uv + Python +
# libraries + a private browser, and puts shortcuts on the Desktop. Re-run to
# update; your private data (%USERPROFILE%\ScoutsPassportData) is never touched.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # makes Invoke-WebRequest much faster

# Where to download the tool from (a .zip of this folder). Set once by whoever
# publishes the tool, or override with $env:PASSPORT_ZIP_URL.
$ZipUrl = if ($env:PASSPORT_ZIP_URL) { $env:PASSPORT_ZIP_URL } else { 'https://github.com/digitally-rendered/scouts-tracker-passport/archive/refs/heads/main.zip' }
$Dir = if ($env:PASSPORT_HOME) { $env:PASSPORT_HOME } else { Join-Path $env:USERPROFILE 'ScoutsPassport' }

function Say($m) { Write-Host "`n== $m ==" -ForegroundColor Cyan }
function Die($m) {
    Write-Host "`nInstall failed: $m" -ForegroundColor Red
    Write-Host 'Help: https://github.com/digitally-rendered/scouts-tracker-passport/blob/main/docs/TROUBLESHOOTING.md'
    Write-Host 'Or email Drew Carmichael: drew.carmichael@gmail.com'
    Read-Host 'Press Enter to close'; exit 1
}


Say 'Downloading Scouts Passport'
$tmp = Join-Path $env:TEMP ('scouts-passport-' + [guid]::NewGuid())
New-Item -ItemType Directory -Force $tmp | Out-Null
try {
    Invoke-WebRequest $ZipUrl -OutFile "$tmp\tool.zip" -UseBasicParsing
    Expand-Archive "$tmp\tool.zip" "$tmp\x" -Force
} catch { Die "couldn't download $ZipUrl ($_)" }
$src = Get-ChildItem "$tmp\x" -Recurse -Depth 1 -Filter passport.py | Select-Object -First 1
if (-not $src) { Die "zip doesn't contain the passport tool" }
$src = $src.DirectoryName

Say "Installing into $Dir"
New-Item -ItemType Directory -Force $Dir | Out-Null
# Replace the code but keep the Python environment (.venv) to make updates fast.
Get-ChildItem $Dir -Force | Where-Object Name -ne '.venv' | Remove-Item -Recurse -Force
Copy-Item "$src\*" $Dir -Recurse -Force
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
$env:PYTHONUTF8 = '1'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Say 'Installing uv (Python manager from astral.sh)'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Push-Location $Dir
try {
    Say 'Installing Python and libraries'
    uv sync; if ($LASTEXITCODE) { Die 'uv sync failed' }
    Say 'Installing the browser used to read ScoutsTracker'
    uv run playwright install chromium; if ($LASTEXITCODE) { Die 'browser install failed' }

    Say 'Adding shortcuts to your Desktop'
    $shell = New-Object -ComObject WScript.Shell
    $desk = [Environment]::GetFolderPath('Desktop')
    foreach ($s in @(@('Scouts Passports', 'run.bat'),
                     @('Scouts Passports - Sign in', 'login.bat'),
                     @('Scouts Passports - Check setup', 'doctor.bat'))) {
        $lnk = $shell.CreateShortcut((Join-Path $desk "$($s[0]).lnk"))
        $lnk.TargetPath = Join-Path $Dir $s[1]
        $lnk.WorkingDirectory = $Dir
        $lnk.Save()
    }

    Say 'Checking the setup'
    uv run python doctor.py

    $data = if ($env:PASSPORT_DATA) { $env:PASSPORT_DATA } else { Join-Path $env:USERPROFILE 'ScoutsPassportData' }
    if (-not (Test-Path (Join-Path $data 'browser-profile'))) {
        $ans = Read-Host "`nSign into ScoutsTracker now? [Y/n]"
        if ($ans -notmatch '^[Nn]') { uv run python passport.py login }
    }
} finally { Pop-Location }

Write-Host "`nDone! To make passports, double-click 'Scouts Passports' on your Desktop." -ForegroundColor Green
Write-Host "Your data stays private in $data"
