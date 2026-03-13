# VerdantME — Windows setup (PowerShell)
# Run from the repo root: .\setup\setup.ps1
# If blocked by execution policy: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function warn { param($msg) Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function fail { param($msg) Write-Host "  [X]  $msg" -ForegroundColor Red; exit 1 }
function step { param($msg) Write-Host "`n$msg" -ForegroundColor White }

# ── Resolve repo root ────────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

Write-Host "`nVerdantME setup" -ForegroundColor White
Write-Host "────────────────────────────────────"

# ── 1. Check Python ──────────────────────────────────────────────────────────
step "1. Checking Python"

$PythonExe = $null
foreach ($cmd in @("py", "python", "python3")) {
    try {
        $verStr = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($verStr -match "^(\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 10) {
                $PythonExe = $cmd
                ok "Found Python $verStr ($cmd)"
                break
            }
        }
    } catch { }
}

if (-not $PythonExe) {
    fail "Python 3.10+ not found. Install from https://python.org (tick 'Add to PATH').`n     See setup\README.md for details."
}

# ── 2. Create virtual environment ───────────────────────────────────────────
step "2. Virtual environment"

if (Test-Path ".venv") {
    ok ".venv already exists — skipping creation"
} else {
    & $PythonExe -m venv .venv
    ok "Created .venv"
}

$Pip        = ".venv\Scripts\pip.exe"
$Activate   = ".venv\Scripts\Activate.ps1"

# ── 3. Install dependencies ──────────────────────────────────────────────────
step "3. Installing dependencies"

& $Pip install --quiet --upgrade pip
& $Pip install --quiet -e .
ok "Installed jobfinder and all dependencies"

# ── 4. Config file ───────────────────────────────────────────────────────────
step "4. Config file"

if (Test-Path "config.json") {
    ok "config.json already exists — skipping"
} else {
    Copy-Item "config.example.json" "config.json"
    ok "Created config.json from example (edit it to customise filters)"
}

# ── 5. .env file ─────────────────────────────────────────────────────────────
step "5. API key file"

if (Test-Path ".env") {
    ok ".env already exists — skipping"
} else {
    Copy-Item ".env.example" ".env"
    warn "Created .env — add your API key before running"
}

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host "`n────────────────────────────────────"
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host @"

Next steps:

  1. Open .env and add your API key
     Anthropic: https://console.anthropic.com
     Gemini:    https://aistudio.google.com (free tier available)

  2. Start the app:
     . $Activate
     jobfinder serve

  3. Open http://localhost:8000 in your browser

Need help? See setup\README.md
"@
