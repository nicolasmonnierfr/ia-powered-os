# =============================================================================
# taguer.ps1 — Ouvre le tagueur sur l'entretien courant (serveur local Python).
#
# A lancer DEPUIS le repertoire racine de l'entretien. Demarre un petit serveur
# local (127.0.0.1) qui sert le tagueur ET les fichiers de l'entretien : l'audio
# (racine) et le .srt (1_transcription\) sont charges automatiquement, et les
# exports vont directement dans 2_coupe\.
#
# Le serveur s'arrete tout seul quand tu fermes l'onglet (heartbeat). Tu peux
# aussi faire Ctrl+C dans cette fenetre.
#
# Usage :
#   .\taguer.ps1
#   .\taguer.ps1 -Port 9000
#   .\taguer.ps1 -NoBrowser     # ne pas ouvrir Chrome automatiquement
# =============================================================================

[CmdletBinding()]
param(
    [int]$Port = 8765,
    [switch]$NoBrowser,
    [switch]$NoReconcile,   # ne pas pre-reconcilier les locuteurs (empreinte vocale)
    [string]$Find        # ouvre le tagueur PILE sur ce terme (saut + lecture)
)

. "$PSScriptRoot\_commun.ps1"

$repo    = Get-RepoHome
$python  = Get-PythonExe -RepoHome $repo
$serveur = Get-Tool -RepoHome $repo "tools\transcription\serveur_tagueur.py"
$tagger  = Get-Tool -RepoHome $repo "tools\transcription\tagger.html"
$root    = Get-EntretienRoot

# Pre-reconciliation AUTO des locuteurs entre troncons (empreinte vocale) : si le
# transcript brut existe (1_transcription\*.srt, etiquettes locales) sans
# suggestion deja calculee, on la genere maintenant pour pre-remplir la 1re etape
# du tagueur. Non bloquant : en cas d'echec, le tagueur reste en mode manuel.
if (-not $NoReconcile) {
    $trans = Join-Path $root "1_transcription"
    if (Test-Path -LiteralPath $trans) {
        $hasSrt = @(Get-ChildItem -LiteralPath $trans -File -Filter *.srt -EA SilentlyContinue).Count -gt 0
        $hasRec = @(Get-ChildItem -LiteralPath $trans -File -Filter *.reconcile.json -EA SilentlyContinue).Count -gt 0
        if ($hasSrt -and -not $hasRec) {
            Write-Info "Pré-réconciliation des locuteurs (empreinte vocale)... (1re fois : peut être long)"
            try { & (Join-Path $PSScriptRoot "reconcilier.ps1") -Quiet } catch { Write-Avert "Réconciliation auto ignorée : $_" }
        }
    }
}

# Verification minimale : un audio doit etre present a la racine.
try { $audio = Find-Audio } catch { Write-Avert $_ }

Write-Etape "Tagueur — entretien : $(Split-Path -Leaf $root)"
if ($audio) { Write-Info "Audio detecte : $($audio.Name)" }
Write-Info "Le serveur s'arrete a la fermeture de l'onglet (ou Ctrl+C ici)."

$pyArgs = @($serveur, "--root", $root, "--tagger", $tagger, "--port", $Port)
if ($NoBrowser) { $pyArgs += "--no-browser" }
if ($Find)      { $pyArgs += @("--find", $Find); Write-Info "Ouverture sur le terme : « $Find »" }

# Log du serveur tagueur (sans toucher au statut 'coupe' : c'est couper.ps1 qui
# finalise la coupe ; ici on trace juste la session de tagging).
$ctx = Start-Etape -Etape "coupe" -Details @{ sous_etape = "tagging" }
$projet = Read-Projet
# On remet 'coupe' en a_faire tant que l'audio coupe n'est pas produit ; le log
# reste, mais le statut ne ment pas sur l'avancement.
$projet.etapes.coupe.statut = "en_cours"
Write-Projet $projet
Write-Info "Log detaille : $($ctx.LogFile)"

$null = Invoke-Logge -Contexte $ctx -Exe $python -Arguments $pyArgs

Add-Content -LiteralPath $ctx.LogFile -Value "`r`n--- Session de tagging terminee (serveur arrete) ---" -Encoding UTF8
