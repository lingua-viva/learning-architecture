# Lingua Viva — Windows Install (PowerShell)
# Usage: irm https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/install.ps1 | iex
#
# Cloned from mission-canvas/install.ps1 — that script is the result of a
# month of PyInstaller/installer debugging on Windows (strip.exe DLL
# corruption, the self-spawn temp-dir trap, PATH persistence). Do not
# redesign this from scratch; only adapt names/URLs/ports to this repo.
#
# Binary is named 'lv' (Lingua Viva). It installs under ~/.lingua-viva and
# starts the local teacher workbench on port 8787.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   Lingua Viva Installer (Windows)        ║" -ForegroundColor Cyan
Write-Host "  ║   Local-first Italian teacher workbench  ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Detect architecture. The release pipeline currently ships 64-bit Windows only.
if (-not [Environment]::Is64BitOperatingSystem) {
    Write-Host "  ERROR: 32-bit Windows is not supported." -ForegroundColor Red
    exit 1
}
$arch = "x86_64"
Write-Host "  ✓ Detected: windows-$arch" -ForegroundColor Green

$installDir = "$env:USERPROFILE\.lingua-viva"

# Gap 2b, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md: a native launcher so
# restarting after a reboot/crash never requires a terminal either — only
# this initial `irm | iex` does. Idempotent: checks port 8787 for an
# already-running Lingua Viva before starting a second instance, and
# tells the user plainly if something ELSE is holding the port.
function Install-NativeLauncher {
    $launcherDir = "$env:USERPROFILE\.lingua-viva"
    New-Item -ItemType Directory -Force -Path $launcherDir | Out-Null
    $launcherPath = "$launcherDir\lv-launch.ps1"

    @'
# Lingua Viva -- native launcher (Gap 2b). Double-clickable via a Desktop/
# Start Menu shortcut; never opens a visible terminal for the user.
$port = 8787
$healthUrl = "http://127.0.0.1:$port/api/health"
$uiUrl = "http://127.0.0.1:$port"
$log = "$env:USERPROFILE\.lingua-viva\launch.log"

function Write-Log($msg) {
    Add-Content -Path $log -Value "$(Get-Date): $msg"
}

function Test-PortOpen($p) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", $p)
        $client.Close()
        return $true
    } catch { return $false }
}

$healthy = $false
$portBusy = $false
try {
    $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    if ($resp.Content -match '"healthy"') { $healthy = $true } else { $portBusy = $true }
} catch {
    if (Test-PortOpen $port) { $portBusy = $true }
}

if ($healthy) {
    Write-Log "Lingua Viva is already running -- opening your browser."
    Start-Process $uiUrl
    exit 0
}
if ($portBusy) {
    Write-Log "Port $port is in use by another program -- close it and try again."
    exit 1
}

# Port is free -- start the server.
$installDir = "$env:USERPROFILE\.lingua-viva"
if (Test-Path "$installDir\lv.exe") {
    Start-Process -FilePath "$installDir\lv.exe" -ArgumentList "serve", "$port" -WindowStyle Hidden
} elseif (Test-Path "$installDir\src\lv_cli.py") {
    Push-Location $installDir
    Start-Process -FilePath "python" -ArgumentList "-m", "src.web", "$port" -WindowStyle Hidden
    Pop-Location
} else {
    Write-Log "Couldn't find the Lingua Viva install -- try re-running the installer."
    exit 1
}

$up = $false
foreach ($i in 1..30) {
    Start-Sleep -Seconds 1
    try {
        Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2 | Out-Null
        $up = $true; break
    } catch {}
}
if ($up) {
    Start-Process $uiUrl
} else {
    Write-Log "Lingua Viva didn't start in time -- try again in a moment."
    exit 1
}
'@ | Set-Content -Path $launcherPath -Encoding UTF8

    # Wrapper .bat so the shortcut never flashes a console window.
    $batPath = "$launcherDir\lv-launch.bat"
    @"
@echo off
powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "$launcherPath"
"@ | Set-Content -Path $batPath -Encoding ASCII

    # .lnk shortcut on the Desktop and in the Start Menu.
    try {
        $shell = New-Object -ComObject WScript.Shell
        foreach ($dir in @(
            [Environment]::GetFolderPath("Desktop"),
            "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
        )) {
            $shortcut = $shell.CreateShortcut("$dir\Lingua Viva.lnk")
            $shortcut.TargetPath = $batPath
            $shortcut.WorkingDirectory = $launcherDir
            $shortcut.WindowStyle = 7  # minimized/hidden console
            $shortcut.Description = "Lingua Viva -- local-first Italian teacher workbench"
            $shortcut.Save()
        }
        Write-Host "  ✓ Desktop and Start Menu shortcuts installed" -ForegroundColor Green
    } catch {
        Write-Host "  ⚠ Couldn't create shortcuts — restart with: $batPath" -ForegroundColor Yellow
    }
}

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
$binary = "lv-windows-${arch}.exe"
$url = "https://github.com/lingua-viva/learning-architecture/releases/latest/download/$binary"

Write-Host "  → Attempting binary download..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

$binarySuccess = $false
try {
    Invoke-WebRequest -Uri $url -OutFile "$installDir\lv.exe" -UseBasicParsing -ErrorAction Stop
    Write-Host "  ✓ Installed lv binary to $installDir\lv.exe" -ForegroundColor Green
    $binarySuccess = $true
} catch {
    Write-Host "  ⚠ Binary download failed or not available. Falling back to source install." -ForegroundColor Yellow
}

if ($binarySuccess) {
    # Add to PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*\.lingua-viva*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$installDir", "User")
        $env:Path = "$env:Path;$installDir"
        Write-Host "  ✓ Added to PATH" -ForegroundColor Green
    }

    # Set UTF-8 permanently
    [Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")

    Check-Ollama
    Install-NativeLauncher

    # Auto-start the web server. Launch `lv serve` directly (a detached, persistent
    # process) rather than `lv start` — a frozen onefile exe spawning ITSELF as a
    # child inherits the parent's PyInstaller temp dir and dies when the parent
    # exits. Start-Process launches an independent process that survives.
    Write-Host "  → Starting web server on http://localhost:8787 ..." -ForegroundColor Cyan
    try {
        Start-Process -FilePath "$installDir\lv.exe" -ArgumentList "serve", "8787" -WindowStyle Hidden -ErrorAction SilentlyContinue
    } catch {}

    # Give the server time to bind. The frozen binary extracts (~3-5s) and loads
    # the ontology/knowledge before binding, so poll up to ~30s.
    $up = $false
    foreach ($i in 1..30) {
        Start-Sleep -Seconds 1
        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:8787/" -UseBasicParsing -TimeoutSec 2 | Out-Null
            $up = $true; break
        } catch {}
    }

    if ($up) {
        Write-Host "  ✓ Web UI is live" -ForegroundColor Green
        Start-Process "http://localhost:8787"            # open the web UI in the browser
    } else {
        Write-Host "  ⚠ Web server didn't come up in time — start it later with 'lv serve'" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║   Installation complete!                 ║" -ForegroundColor Cyan
    Write-Host "  ╠══════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "  ║   Web UI:   http://localhost:8787         ║" -ForegroundColor Cyan
    Write-Host "  ║   Status:   lv health                    ║" -ForegroundColor Cyan
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
    Write-Host "  → Cloning Lingua Viva..." -ForegroundColor Cyan
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
Install-NativeLauncher

# Health check
Write-Host ""
Write-Host "Running health check..." -ForegroundColor Cyan
try {
    python src/lv_cli.py health
} catch {
    Write-Host "  (Run 'python src/lv_cli.py health' to verify)" -ForegroundColor Yellow
}

# Auto-start web server (source mode — src/web.py is on disk)
Write-Host "  → Starting web server on http://localhost:8787 ..." -ForegroundColor Cyan
try {
    Start-Process -FilePath "python" -ArgumentList "-m", "src.web", "8787" -WindowStyle Hidden -ErrorAction SilentlyContinue
} catch {}

Pop-Location

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║     Installation complete                ║" -ForegroundColor Cyan
Write-Host "  ╠══════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "  ║  Start:  cd $installDir                  ║" -ForegroundColor Cyan
Write-Host "  ║          python src/lv_cli.py shell      ║" -ForegroundColor Cyan
Write-Host "  ║  Web UI: http://localhost:8787            ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
