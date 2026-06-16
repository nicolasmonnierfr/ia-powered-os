# =============================================================================
# transcrire.ps1 — Transcription d'un entretien (wrapper de transcribe_robuste.py)
#
# A lancer DEPUIS le repertoire racine de l'entretien (celui qui contient
# l'audio). Diarisation activee par defaut.
#
# Usage :
#   .\transcrire.ps1                  # transcrit l'audio du repertoire courant
#   .\transcrire.ps1 -NoDiarize       # sans diarisation
#   .\transcrire.ps1 -ChunkMin 10     # troncons de 10 min
#   .\transcrire.ps1 monaudio.m4a     # audio explicite
#
# Sortie : 1_transcription\<nom>.txt et 1_transcription\<nom>.srt
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Audio,
    [switch]$NoDiarize,
    [int]$ChunkMin,
    [string]$Model,
    [string]$Language
)

. "$PSScriptRoot\_commun.ps1"

$repo   = Get-RepoHome
$python = Get-PythonExe -RepoHome $repo
$outil  = Get-Tool -RepoHome $repo "tools\transcription\transcribe_robuste.py"

# --- Audio cible -------------------------------------------------------------
if ($Audio) {
    if (-not (Test-Path -LiteralPath $Audio)) { Write-Echec "Audio introuvable : $Audio"; exit 1 }
    $audioFile = Get-Item -LiteralPath $Audio
} else {
    try { $audioFile = Find-Audio } catch { Write-Echec $_; exit 1 }
}
$stem = $audioFile.BaseName

Write-Etape "Transcription de : $($audioFile.Name)"
Write-Info  "Diarisation : $(if ($NoDiarize) {'NON'} else {'OUI'})"

# --- Dossier de sortie -------------------------------------------------------
$dest = Get-SousDossier "1_transcription" -Creer

# --- Construction des arguments ----------------------------------------------
$pyArgs = @($outil, $audioFile.Name, "--outdir", $dest)
if (-not $NoDiarize) { $pyArgs += "--diarize" }
if ($ChunkMin)       { $pyArgs += @("--chunk-min", $ChunkMin) }
if ($Model)          { $pyArgs += @("--model", $Model) }
if ($Language)       { $pyArgs += @("--language", $Language) }

# --- Execution (avec log centralise + suivi dans entretien.json) -------------
$modeleLabel = if ($Model) { $Model } else { "defaut" }
$ctx = Start-Etape -Etape "transcription" -Details @{ diarisation = (-not $NoDiarize); modele = $modeleLabel }
Write-Info "Lancement (peut etre LONG en CPU)..."
Write-Info "Log detaille : $($ctx.LogFile)"
$code = Invoke-Logge -Contexte $ctx -Exe $python -Arguments $pyArgs

if ($code -ne 0) {
    Complete-Etape -Contexte $ctx -Statut "echec" -Message "transcribe_robuste.py a renvoye le code $code"
    Write-Echec "La transcription a echoue (code $code). Voir le log : $($ctx.LogFile)"
    exit $code
}

# --- Verification ------------------------------------------------------------
$txt = Join-Path $dest "$stem.txt"
$srt = Join-Path $dest "$stem.srt"
if ((Test-Path -LiteralPath $txt) -and (Test-Path -LiteralPath $srt)) {
    Complete-Etape -Contexte $ctx -Statut "fait"
    Write-Ok "Transcription rangee dans 1_transcription\"
    Write-Info "  $stem.txt"
    Write-Info "  $stem.srt"
} else {
    Complete-Etape -Contexte $ctx -Statut "echec" -Message "Sorties .txt/.srt non trouvees dans 1_transcription\"
    Write-Avert "Sorties attendues non trouvees dans 1_transcription\. Voir le log : $($ctx.LogFile)"
}
