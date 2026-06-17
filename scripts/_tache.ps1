# =============================================================================
# _tache.ps1 — Lanceur du tick d'orchestration pour la TACHE PLANIFIEE.
#
# N'est PAS destine a un usage manuel : c'est l'action enregistree par
# `veille.ps1 -Installer`. Role :
#   - journaliser chaque tick (la tache n'a pas de console) dans
#     <repo>\logs\orchestrer-tache.log ;
#   - lancer le tick en mode TRANSCRIPTION INLINE (synchrone), car un process
#     detache serait tue par le planificateur a la fin du tick.
#
# Usage (par le planificateur) :
#   _tache.ps1 -Perimetre "D:\...\Interviews"
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Perimetre
)

. "$PSScriptRoot\_commun.ps1"

$orchestrer = Join-Path $PSScriptRoot "orchestrer.ps1"
$log = Join-Path (Get-LogsDir) "orchestrer-tache.log"

$entete = @(
    "",
    "==============================================================",
    " Tick planifie : $(Now-Iso)",
    " Perimetre     : $Perimetre",
    "=============================================================="
) -join "`r`n"
Add-Content -LiteralPath $log -Value $entete -Encoding UTF8

# Tous les flux (succes/erreur/warning/info) vers le log de tache.
# -NoEtatMd : c'est la tache "Etat" (_etat_tache.ps1, independante et frequente)
# qui detient ETAT.md. La transcription inline bloquerait sinon son rafraichissement
# pendant des heures ; et deux redacteurs = course d'ecriture sur le fichier.
& $orchestrer $Perimetre -TranscribeInline -NoEtatMd *>> $log

Add-Content -LiteralPath $log -Value "--- Fin du tick : $(Now-Iso) (code $LASTEXITCODE) ---" -Encoding UTF8
