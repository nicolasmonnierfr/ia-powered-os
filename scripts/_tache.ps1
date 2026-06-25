# =============================================================================
# _tache.ps1 — Lanceur du tick d'orchestration pour la TACHE PLANIFIEE.
#
# N'est PAS destine a un usage manuel : c'est l'action enregistree par
# `veille.ps1 -Installer`. Role :
#   - lire le REGISTRE des perimetres inscrits (config\perimetres.json) et
#     orchestrer CHACUN d'eux (ia veille -Inscrire / -Desinscrire pour l'editer) ;
#   - journaliser chaque tick (la tache n'a pas de console) dans
#     <repo>\logs\orchestrer-tache.log ;
#   - lancer le tick en mode TRANSCRIPTION INLINE (synchrone), car un process
#     detache serait tue par le planificateur a la fin du tick.
#
# -Perimetre <chemin> (optionnel) force UN perimetre et court-circuite le
# registre : utile pour un run ad hoc ou pour une ancienne tache. Sans lui, on
# parcourt le registre.
# =============================================================================

[CmdletBinding()]
param(
    [string]$Perimetre
)

. "$PSScriptRoot\_commun.ps1"

$orchestrer = Join-Path $PSScriptRoot "orchestrer.ps1"
$log = Join-Path (Get-LogsDir) "orchestrer-tache.log"

# Source des perimetres : override explicite, sinon le registre.
$perims = if ($Perimetre) { @($Perimetre) } else { @(Read-Perimetres) }

$entete = @(
    "",
    "==============================================================",
    " Tick planifie : $(Now-Iso)",
    " Perimetres    : $(if ($perims.Count) { $perims -join ' | ' } else { '(aucun inscrit)' })",
    "=============================================================="
) -join "`r`n"
Add-Content -LiteralPath $log -Value $entete -Encoding UTF8

if (-not $perims -or $perims.Count -eq 0) {
    Add-Content -LiteralPath $log -Value " Aucun perimetre inscrit : rien a faire. (ia veille -Inscrire <dossier>)" -Encoding UTF8
    Add-Content -LiteralPath $log -Value "--- Fin du tick : $(Now-Iso) ---" -Encoding UTF8
    exit 0
}

# Un perimetre apres l'autre. Le verrou de transcription (global) garantit qu'une
# seule transcription tourne a la fois, meme reparties sur plusieurs perimetres.
# -NoEtatMd : c'est la tache "Etat" (_etat_tache.ps1, independante et frequente)
# qui detient ETAT.md. La transcription inline bloquerait sinon son rafraichissement
# pendant des heures ; et deux redacteurs = course d'ecriture sur le fichier.
foreach ($p in $perims) {
    if (-not (Test-Path -LiteralPath $p)) {
        Add-Content -LiteralPath $log -Value " /!\ Perimetre introuvable, ignore : $p" -Encoding UTF8
        continue
    }
    Add-Content -LiteralPath $log -Value "`r`n>>> Perimetre : $p" -Encoding UTF8
    & $orchestrer $p -TranscribeInline -NoEtatMd *>> $log
}

Add-Content -LiteralPath $log -Value "--- Fin du tick : $(Now-Iso) (code $LASTEXITCODE) ---" -Encoding UTF8
