# =============================================================================
# reconcilier.ps1 — Reconciliation AUTO des locuteurs entre troncons (empreinte
# vocale). Pre-remplit la 1re etape (manuelle) du tagueur.
#
# A lancer DEPUIS le repertoire racine de l'entretien. Lit les troncons WAV
# conserves cote IA-Powered-OS (data\.chunks\) et ecrit une suggestion de
# mapping  T<n>-X -> Locuteur global  dans 1_transcription\<stem>.reconcile.json,
# que le tagueur charge automatiquement.
#
# Prerequis : transcription faite AVEC diarisation (etiquettes locales T1-A...).
#
# Usage :
#   .\reconcilier.ps1
#   .\reconcilier.ps1 -Speakers 2     # force le nombre de locuteurs
# =============================================================================

[CmdletBinding()]
param(
    [int]$Speakers,
    [switch]$Quiet        # silencieux en cas d'absence de troncons (usage auto)
)

. "$PSScriptRoot\_commun.ps1"

$repo   = Get-RepoHome
$python = Get-PythonExe -RepoHome $repo
$outil  = Get-Tool -RepoHome $repo "tools\transcription\reconcilier.py"
$root   = Get-EntretienRoot

Write-Etape "Réconciliation des locuteurs (empreinte vocale) : $(Split-Path -Leaf $root)"

$pyArgs = @($outil, "--root", $root)
if ($PSBoundParameters.ContainsKey("Speakers")) { $pyArgs += @("--speakers", $Speakers) }

& $python @pyArgs
$code = $LASTEXITCODE
if ($code -ne 0 -and -not $Quiet) {
    Write-Avert "Réconciliation non produite (code $code). Le tagueur restera en mode manuel."
}
exit $code
