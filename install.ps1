# Delentia OS - one-line installer for Windows PowerShell.
#
# Usage:
#   iex (irm https://raw.githubusercontent.com/delentia-labs/delentia-os/main/install.ps1)
#
# Same real steps as install.sh (the Linux/macOS/WSL2 installer): checks
# for git and Python 3.10+ already on the machine (no silent system
# package installs, no elevation requested), clones or reuses the repo,
# creates a project-local virtualenv, installs the base package, and
# prints the real next commands.
#
# Deliberately does NOT set $ErrorActionPreference = "Stop" globally.
# Direct testing on this exact platform found that doing so turns git's
# and pip's completely normal stderr progress/warning output into
# terminating NativeCommandErrors, and that native commands' own
# $LASTEXITCODE is not reliable enough on its own in every PowerShell
# host to gate on alone. Every step below instead verifies success by
# checking the REAL resulting artifact (a file that must now exist, or a
# module that must now import) - a signal that stayed correct across
# every failure mode hit during testing, unlike exit codes or stderr
# capture in this environment.

$RepoUrl = "https://github.com/delentia-labs/delentia-os.git"
$InstallDir = if ($env:DELENTIA_INSTALL_DIR) { $env:DELENTIA_INSTALL_DIR } else { Join-Path $HOME "delentia-os" }

function Write-Info($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Warn($msg)  { Write-Host "!! $msg" -ForegroundColor Yellow }
function Fail($msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

# --- 1. Preflight: git and Python, no auto-install ----------------------

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git is required but not found. Install it first, e.g.: winget install --id Git.Git -e`nThen re-run this installer."
}

$PythonCmd = $null
foreach ($candidate in @("python3.12", "python3.11", "python3.10", "python", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $versionOutput = & $candidate -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($versionOutput) {
                $parts = $versionOutput -split "\."
                $major = [int]$parts[0]
                $minor = [int]$parts[1]
                if ($major -eq 3 -and $minor -ge 10) {
                    $PythonCmd = $candidate
                    break
                }
            }
        } catch {}
    }
}

if (-not $PythonCmd) {
    Fail "Python 3.10+ is required but was not found on PATH. Install it first, e.g.: winget install --id Python.Python.3.12 -e`nThen re-run this installer (open a NEW terminal after installing)."
}
$pyVersion = & $PythonCmd --version
Write-Info "Using $pyVersion ($PythonCmd)"

# --- 2. Get the source: reuse cwd if already the right repo, else clone -

$pyprojectPath = Join-Path (Get-Location) "pyproject.toml"
if ((Test-Path $pyprojectPath) -and (Select-String -Path $pyprojectPath -Pattern '^name = "delentia-os"' -Quiet)) {
    Write-Info "Already inside a delentia-os checkout ($(Get-Location)) - installing in place."
    $InstallDir = (Get-Location).Path
} elseif (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Info "Found an existing checkout at $InstallDir - pulling latest main."
    git -C $InstallDir pull --ff-only origin main
} else {
    Write-Info "Cloning $RepoUrl into $InstallDir"
    git clone --depth 1 $RepoUrl $InstallDir
    if (-not (Test-Path (Join-Path $InstallDir ".git"))) {
        Fail "git clone did not produce a .git directory at $InstallDir - see output above for the real error."
    }
}

Set-Location $InstallDir

# --- 3. Virtualenv + base install ----------------------------------------

$venvPath = Join-Path $InstallDir ".venv"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Info "Creating virtualenv at $venvPath"
    & $PythonCmd -m venv .venv
    if (-not (Test-Path $activateScript)) {
        Fail "python -m venv did not produce $activateScript - see output above for the real error."
    }
}

. $activateScript

# Use the venv's python.exe by its FULL path from here on rather than the
# bare "python" command name, to remove any ambiguity about which
# interpreter a later PATH lookup resolves to after dot-sourcing
# Activate.ps1 changes $env:PATH mid-script.
$venvPython = Join-Path $venvPath "Scripts\python.exe"

# NOTE for future editors: an em-dash (the U+2014 character, not a plain
# ASCII hyphen) anywhere in this file previously caused Windows
# PowerShell 5.1 to silently stop executing partway through the script
# with NO error - confirmed by direct testing (file-based execution
# markers proved the pip-install block below was never even reached).
# Keep this file plain-ASCII-only; do not reintroduce em-dashes, curly
# quotes, or other non-ASCII punctuation.

Write-Info "Installing delentia-os (base package) - this can take a minute..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e .

& $venvPython -c "import rct_control_plane" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: delentia-os did not install correctly - import rct_control_plane failed." -ForegroundColor Red
    Write-Host "Re-run this from $InstallDir with the venv activated to see the real error:" -ForegroundColor Red
    Write-Host "    python -m pip install -e ." -ForegroundColor Red
    exit 1
}

# --- 4. Done: real next steps, not just "it worked" ----------------------

Write-Host ""
Write-Info "Installed. To use it in a NEW terminal, first activate the venv:"
$activateHint = $venvPath + "\Scripts\Activate.ps1"
Write-Host ('    . "' + $activateHint + '"')
Write-Host ""
Write-Info "Then, in order:"
Write-Host "    delentia doctor     # real preflight check - tells you exactly what's missing"
Write-Host "    delentia init       # creates a local .env from the template"
Write-Host "    delentia chat       # start the terminal chat UI"
Write-Host ""
Write-Info "For a fully local, zero-cloud setup (no API keys, nothing leaves this machine):"
Write-Host "    1. Install Ollama:  https://ollama.com/download"
Write-Host "    2. Pull a model:    ollama pull llama3.1"
Write-Host "    3. delentia already talks to Ollama at http://127.0.0.1:11434 by default."
Write-Host ""
Write-Info "Optional heavier extras (image generation, video/audio analysis - pulls in torch):"
Write-Host "    pip install -e `".[diffusion,media-ai]`""
Write-Host ""
Write-Warn "Note: the newer torch CVE-patched release needs Windows Long Path support enabled first (a one-time system setting: gpedit.msc > Computer Configuration > Administrative Templates > System > Filesystem > Enable Win32 long paths). The base install above does not need this."
