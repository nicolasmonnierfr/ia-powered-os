# =============================================================================
# couper.ps1 — Reconstruit l'audio raccourci (wrapper de couper_audio.py)
#
# A lancer DEPUIS le repertoire racine de l'entretien (celui qui contient
# l'audio). Le plan de coupe doit avoir ete exporte dans 2_coupe\ par le
# tagueur (bouton « Exporter vers 2_coupe »).
#
# Usage :
#   .\couper.ps1                       # plan auto-decouvert dans 2_coupe\
#   .\couper.ps1 monplan.json          # plan explicite
#   .\couper.ps1 -Audio monaudio.m4a   # audio source explicite
#
# Sortie : 2_coupe\<nom>_coupe<ext>
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Plan,
    [string]$Audio
)

. "$PSScriptRoot\_commun.ps1"

$repo   = Get-RepoHome
$python = Get-PythonExe -RepoHome $repo
$outil  = Get-Tool -RepoHome $repo "tools\transcription\couper_audio.py"

$coupeDir = Get-SousDossier "2_coupe" -Creer

# --- Localisation du plan de coupe -------------------------------------------
if ($Plan) {
    if (-not (Test-Path -LiteralPath $Plan)) { Write-Echec "Plan introuvable : $Plan"; exit 1 }
    $planFile = Get-Item -LiteralPath $Plan
} else {
    # Auto-decouverte : plan_de_coupe.json dans 2_coupe\, sinon a la racine.
    $candidats = @(
        (Join-Path $coupeDir "plan_de_coupe.json"),
        (Join-Path (Get-EntretienRoot) "plan_de_coupe.json")
    )
    $planFile = $null
    foreach ($c in $candidats) {
        if (Test-Path -LiteralPath $c) { $planFile = Get-Item -LiteralPath $c; break }
    }
    if (-not $planFile) {
        Write-Echec "Aucun plan_de_coupe.json trouve dans 2_coupe\ ni a la racine."
        Write-Info  "Exporte d'abord le plan depuis le tagueur (bouton « Exporter vers 2_coupe »)."
        exit 1
    }
}
Write-Etape "Plan de coupe : $($planFile.Name)"
Write-Info  "Source : $($planFile.DirectoryName)"

# --- Localisation de l'audio source ------------------------------------------
# Le plan est dans 2_coupe\ mais l'audio est a la racine : on passe --audio
# explicitement pour lever toute ambiguite cote couper_audio.py.
if ($Audio) {
    if (-not (Test-Path -LiteralPath $Audio)) { Write-Echec "Audio introuvable : $Audio"; exit 1 }
    $audioFile = Get-Item -LiteralPath $Audio
} else {
    try { $audioFile = Find-Audio } catch { Write-Echec $_; exit 1 }
}
$stem = $audioFile.BaseName
$ext  = $audioFile.Extension
Write-Info "Audio source : $($audioFile.Name)"

# --- Sortie ------------------------------------------------------------------
$output = Join-Path $coupeDir "$stem`_coupe$ext"

# --- Execution ---------------------------------------------------------------
$pyArgs = @($outil, $planFile.FullName, "--audio", $audioFile.FullName, "--output", $output)
$ctx = Start-Etape -Etape "coupe" -Details @{ plan = $planFile.Name }
Write-Info "Reencodage en cours (precis a la milliseconde)..."
Write-Info "Log detaille : $($ctx.LogFile)"
$code = Invoke-Logge -Contexte $ctx -Exe $python -Arguments $pyArgs
if ($code -ne 0) {
    Complete-Etape -Contexte $ctx -Statut "echec" -Message "couper_audio.py a renvoye le code $code"
    Write-Echec "La coupe a echoue (code $code). Voir le log : $($ctx.LogFile)"
    exit $code
}

# --- Rangement du plan + verification ----------------------------------------
# Si le plan etait a la racine, on le deplace dans 2_coupe\ pour tout regrouper.
if ($planFile.DirectoryName -eq (Get-EntretienRoot)) {
    Move-Vers $planFile.FullName $coupeDir | Out-Null
    Write-Info "Plan deplace dans 2_coupe\"
}

if (Test-Path -LiteralPath $output) {
    Complete-Etape -Contexte $ctx -Statut "fait"
    Write-Ok "Audio coupe ecrit dans 2_coupe\"
    Write-Info "  $stem`_coupe$ext"
    Write-Avert "Verifie que 2_coupe\ contient aussi $stem`_coupe.srt et $stem`_coupe.txt (exportes par le tagueur)."
} else {
    Complete-Etape -Contexte $ctx -Statut "echec" -Message "Audio coupe non produit"
    Write-Avert "Audio coupe attendu non trouve. Voir le log : $($ctx.LogFile)"
}
