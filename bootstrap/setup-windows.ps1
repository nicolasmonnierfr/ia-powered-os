# ============================================================
#  IA-Powered-OS — Bootstrap Windows
#  Installe les prerequis et l'environnement Python du projet.
#  A lancer depuis la racine du repo :  .\bootstrap\setup-windows.ps1
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "=== IA-Powered-OS : installation ===" -ForegroundColor Cyan

# --- 0. Verifier qu'on est a la racine du repo ---
if (-not (Test-Path ".\requirements.txt")) {
    Write-Host "[ERREUR] Lance ce script depuis la racine du repo IA-Powered-OS." -ForegroundColor Red
    exit 1
}

# --- 1. Prerequis systeme (winget) ---
Write-Host "`n[1/4] Verification des prerequis systeme..." -ForegroundColor Yellow

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

# Python 3.12
if (Test-Command "py") {
    $hasPy312 = (py -0p 2>$null) -match "3\.12"
} else {
    $hasPy312 = $false
}
if (-not $hasPy312) {
    Write-Host "  Python 3.12 absent. Installation via winget..." -ForegroundColor Gray
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    Write-Host "  >>> FERME ET ROUVRE PowerShell, puis relance ce script." -ForegroundColor Magenta
    exit 0
} else {
    Write-Host "  Python 3.12 : OK" -ForegroundColor Green
}

# ffmpeg
if (-not (Test-Command "ffmpeg")) {
    Write-Host "  ffmpeg absent. Installation via winget..." -ForegroundColor Gray
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Write-Host "  >>> FERME ET ROUVRE PowerShell, puis relance ce script." -ForegroundColor Magenta
    exit 0
} else {
    Write-Host "  ffmpeg : OK" -ForegroundColor Green
}

# --- 2. Environnement virtuel ---
Write-Host "`n[2/4] Creation de l'environnement virtuel (.venv)..." -ForegroundColor Yellow
if (-not (Test-Path ".\.venv")) {
    py -3.12 -m venv .venv
    Write-Host "  .venv cree." -ForegroundColor Green
} else {
    Write-Host "  .venv existe deja." -ForegroundColor Green
}

# Activation
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip --quiet

# --- 3. torch CPU (AVANT whisperx) ---
Write-Host "`n[3/4] Installation de torch (CPU)..." -ForegroundColor Yellow
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# --- 4. whisperx + reste ---
Write-Host "`n[4/4] Installation de whisperx et dependances..." -ForegroundColor Yellow
pip install -r requirements.txt

# --- 4 bis. Modele spaCy FR (anonymisation) ---
Write-Host "`n[4bis/4] Installation du modele spaCy francais (anonymisation)..." -ForegroundColor Yellow
# Le modele n'est pas un paquet PyPI : on l'installe par son wheel officiel.
# (fr_core_news_md ~46 Mo ; basculer sur _lg pour plus de precision si besoin.)
python -m spacy download fr_core_news_md
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Fallback : installation directe du wheel du modele..." -ForegroundColor Gray
    pip install "https://github.com/explosion/spacy-models/releases/download/fr_core_news_md-3.8.0/fr_core_news_md-3.8.0-py3-none-any.whl"
}

# --- Config .env ---
if (-not (Test-Path ".\config\.env")) {
    Copy-Item ".\config\.env.example" ".\config\.env"
    Write-Host "`n[CONFIG] config\.env cree depuis le modele." -ForegroundColor Magenta
    Write-Host "         >>> Edite-le pour y mettre ton token Hugging Face." -ForegroundColor Magenta
}

Write-Host "`n=== Installation terminee ===" -ForegroundColor Cyan
Write-Host "Pour activer l'environnement plus tard :  .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
