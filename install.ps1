# Still I Rise — Windows Install (PowerShell)
# Usage: irm https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/install.ps1 | iex
#
# Cloned from mission-canvas/install.ps1 — that script is the result of a
# month of PyInstaller/installer debugging on Windows (strip.exe DLL
# corruption, the self-spawn temp-dir trap, PATH persistence). Do not
# redesign this from scratch; only adapt names/URLs/ports to this repo.
#
# Binary is named 'sir' (Still I Rise), not 'mc' — this is a fork of Mission
# Canvas and both would otherwise install to the same PATH entry. Sharing
# the name 'mc' would let whichever product installs second silently
# overwrite the other's binary on any machine that has both.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   Still I Rise Installer (Windows)       ║" -ForegroundColor Cyan
Write-Host "  ║   AI education for refugee children      ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Detect architecture
$arch = if ([Environment]::Is64BitOperatingSystem) { "x86_64" } else { "x86" }
Write-Host "  ✓ Detected: windows-$arch" -ForegroundColor Green

$installDir = "$env:USERPROFILE\.still-i-rise"

function Check-Ollama {
    try {
        ollama --version 2>&1 | Out-Null
        Write-Host "  ✓ Ollama detected" -ForegroundColor Green
        Write-Host "  → Suggestion: Run 'ollama pull qwen3:8b' to pull the required model." -ForegroundColor Yellow
    } catch {
        Write-Host "  ⚠ Ollama not found. Install from https://ollama.com" -ForegroundColor Yellow
    }
}

# ── Try binary install first ──
$binary = "sir-windows-${arch}.exe"
$url = "https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/dist/$binary"

Write-Host "  → Attempting binary download..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

$binarySuccess = $false
try {
    Invoke-WebRequest -Uri $url -OutFile "$installDir\sir.exe" -UseBasicParsing -ErrorAction Stop
    Write-Host "  ✓ Installed sir binary to $installDir\sir.exe" -ForegroundColor Green
    $binarySuccess = $true
} catch {
    Write-Host "  ⚠ Binary download failed or not available. Falling back to source install." -ForegroundColor Yellow
}

if ($binarySuccess) {
    # Add to PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*\.still-i-rise*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$installDir", "User")
        $env:Path = "$env:Path;$installDir"
        Write-Host "  ✓ Added to PATH" -ForegroundColor Green
    }

    # Set UTF-8 permanently
    [Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")

    Check-Ollama

    # Auto-start the web server. Launch `sir serve` directly (a detached, persistent
    # process) rather than `sir start` — a frozen onefile exe spawning ITSELF as a
    # child inherits the parent's PyInstaller temp dir and dies when the parent
    # exits. Start-Process launches an independent process that survives.
    Write-Host "  → Starting web server on http://localhost:7896 ..." -ForegroundColor Cyan
    try {
        Start-Process -FilePath "$installDir\sir.exe" -ArgumentList "serve", "7896" -WindowStyle Hidden -ErrorAction SilentlyContinue
    } catch {}

    # Give the server time to bind. The frozen binary extracts (~3-5s) and loads
    # the ontology/knowledge before binding, so poll up to ~30s.
    $up = $false
    foreach ($i in 1..30) {
        Start-Sleep -Seconds 1
        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:7896/" -UseBasicParsing -TimeoutSec 2 | Out-Null
            $up = $true; break
        } catch {}
    }

    if ($up) {
        Write-Host "  ✓ Web UI is live" -ForegroundColor Green
        Start-Process "http://localhost:7896"            # open the web UI in the browser
    } else {
        Write-Host "  ⚠ Web server didn't come up in time — start it later with 'sir serve'" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║   Installation complete!                 ║" -ForegroundColor Cyan
    Write-Host "  ╠══════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "  ║   Web UI:   http://localhost:7896         ║" -ForegroundColor Cyan
    Write-Host "  ║   Status:   sir health                   ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    exit 0
}

# ── Source fallback ──
Write-Host "  → Installing from source..." -ForegroundColor Cyan

# Check Python
try {
    $pyver = python --version 2>&1
    if ($pyver -match "3\.(1[1-9]|[2-9]\d)") {
        Write-Host "  Python: $pyver ✓" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Python 3.11+ required (found $pyver)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ERROR: Python not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

# Check Git
try {
    git --version | Out-Null
    Write-Host "  Git: ✓" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Git required. Install from https://git-scm.com" -ForegroundColor Red
    exit 1
}

# Clone or Update
if (-not (Test-Path "$installDir\.git")) {
    Write-Host "  → Cloning Still I Rise..." -ForegroundColor Cyan
    git clone https://github.com/lingua-viva/learning-architecture.git "$installDir"
} else {
    Write-Host "  → Updating existing clone..." -ForegroundColor Cyan
    Push-Location "$installDir"
    try { git pull --quiet } catch {}
    Pop-Location
}

# Install dependencies
Push-Location "$installDir"
Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
pip install --quiet --break-system-packages pyyaml redis fastapi uvicorn websockets pdfplumber sqlite-vec pytest 2>$null
if ($LASTEXITCODE -ne 0) {
    pip install --quiet pyyaml redis fastapi uvicorn websockets pdfplumber sqlite-vec pytest 2>$null
}

# Install Node dependencies (optional)
try {
    $nodever = node --version 2>&1
    Write-Host "  Node.js: $nodever ✓" -ForegroundColor Green
    if (Test-Path "runtime/package.json") {
        Set-Location runtime
        npm install --silent 2>$null
        Set-Location ..
    }
} catch {
    Write-Host "  Node.js: not found (optional)" -ForegroundColor Yellow
}

Check-Ollama

# Health check
Write-Host ""
Write-Host "Running health check..." -ForegroundColor Cyan
try {
    python src/mc_cli.py health
} catch {
    Write-Host "  (Run 'python src/mc_cli.py health' to verify)" -ForegroundColor Yellow
}

# Auto-start web server (source mode — src/web.py is on disk)
Write-Host "  → Starting web server on http://localhost:7896 ..." -ForegroundColor Cyan
try {
    Start-Process -FilePath "python" -ArgumentList "-m", "src.web", "7896" -WindowStyle Hidden -ErrorAction SilentlyContinue
} catch {}

Pop-Location

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║     Installation complete                ║" -ForegroundColor Cyan
Write-Host "  ╠══════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "  ║  Start:  cd $installDir                  ║" -ForegroundColor Cyan
Write-Host "  ║          python src/mc_cli.py shell      ║" -ForegroundColor Cyan
Write-Host "  ║  Web UI: http://localhost:7896            ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
