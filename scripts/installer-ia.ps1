# =============================================================================
# installer-ia.ps1 — Rend la commande "ia" disponible dans tous les terminaux.
#
# Ajoute au PROFIL PowerShell :
#   - la variable IA_POWERED_OS_HOME (localisation du repo) ;
#   - une fonction "ia" qui aiguille vers les wrappers, et gere "ia setenv"
#     (activation du venv dans la session courante, possible car c'est une
#      FONCTION executee dans ta session, pas un script isole).
#
# A lancer UNE FOIS, depuis le repo :
#   .\scripts\installer-ia.ps1
#
# Pour desinstaller : .\scripts\installer-ia.ps1 -Desinstaller
# =============================================================================

[CmdletBinding()]
param([switch]$Desinstaller)

$ErrorActionPreference = "Stop"

# Repo = parent du dossier scripts\ (ou ce fichier reside).
$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $repo "requirements.txt"))) {
    Write-Host "[ERREUR] Ce script doit etre lance depuis le repo IA-Powered-OS." -ForegroundColor Red
    exit 1
}

$profilePath = $PROFILE.CurrentUserAllHosts
$marqueurDebut = "# >>> IA-Powered-OS >>>"
$marqueurFin   = "# <<< IA-Powered-OS <<<"

# --- S'assurer que le fichier de profil existe -------------------------------
$profileDir = Split-Path -Parent $profilePath
if (-not (Test-Path -LiteralPath $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
}

# --- Retirer un ancien bloc IA-Powered-OS s'il existe (idempotent) -----------
$contenu = Get-Content -LiteralPath $profilePath -Raw -ErrorAction SilentlyContinue
if ($null -eq $contenu) { $contenu = "" }
$pattern = [regex]::Escape($marqueurDebut) + "[\s\S]*?" + [regex]::Escape($marqueurFin) + "\r?\n?"
$contenu = [regex]::Replace($contenu, $pattern, "")

if ($Desinstaller) {
    Set-Content -LiteralPath $profilePath -Value $contenu -Encoding UTF8
    Write-Host "[OK] Commande 'ia' retiree du profil ($profilePath)." -ForegroundColor Green
    Write-Host "     Ouvre un nouveau terminal pour que ce soit effectif." -ForegroundColor Gray
    exit 0
}

# --- Construire le bloc a injecter -------------------------------------------
# Note : le chemin du repo est fige a l'installation. Si tu deplaces le repo,
# relance ce script.
$bloc = @"
$marqueurDebut
`$env:IA_POWERED_OS_HOME = "$repo"
function ia {
    `$scripts = Join-Path `$env:IA_POWERED_OS_HOME "scripts"
    `$cmd = if (`$args.Count -ge 1) { [string]`$args[0] } else { `$null }
    `$rest = @(`$args | Select-Object -Skip 1)
    # 'setenv' doit s'executer DANS cette session -> gere ici, pas dans ia.ps1.
    if (`$cmd -eq "setenv") {
        `$act = Join-Path `$env:IA_POWERED_OS_HOME ".venv\Scripts\Activate.ps1"
        if (Test-Path -LiteralPath `$act) { . `$act; Write-Host "[OK] venv active dans cette session." -ForegroundColor Green }
        else { Write-Host "[ERREUR] venv introuvable : `$act" -ForegroundColor Red }
        return
    }
    `$dispatch = Join-Path `$scripts "ia.ps1"
    if (`$rest.Count) { & `$dispatch `$cmd @rest } else { & `$dispatch `$cmd }
}
$marqueurFin
"@

$nouveau = ($contenu.TrimEnd() + "`r`n`r`n" + $bloc + "`r`n").TrimStart()
Set-Content -LiteralPath $profilePath -Value $nouveau -Encoding UTF8

Write-Host "[OK] Commande 'ia' installee dans le profil :" -ForegroundColor Green
Write-Host "     $profilePath" -ForegroundColor Gray
Write-Host "     IA_POWERED_OS_HOME = $repo" -ForegroundColor Gray
Write-Host ""
Write-Host "Ouvre un NOUVEAU terminal, puis teste :" -ForegroundColor Cyan
Write-Host "     ia aide" -ForegroundColor Yellow
