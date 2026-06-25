# =============================================================================
# synthese.ps1 — Synthese multi-entretiens (perimetre = manifeste, pas un dossier).
#
# A lancer DEPUIS le dossier d'une mission (le « perimetre » qui contient les
# entretiens). Sous-commandes :
#
#   ia synthese init [perimetre]        # pre-genere synthese.manifeste.json
#   ia synthese verifier [manifeste]    # GARDE-FOU anti-fuite (avant tout envoi IA)
#
# La synthese ne porte que sur les entretiens DESIGNES dans le manifeste (tu
# selectionnes/edites la liste). Le garde-fou confronte le contenu anonymise a la
# memoire client (LOCALE) : tout vrai nom residuel BLOQUE l'envoi. Les noms de
# fichiers ne partent jamais (le payload ne porte que des labels neutres).
#
# (L'appel a l'IA -- 'ia synthese lancer' -- viendra dans un increment suivant.)
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Action,
    [Parameter(Position = 1)] [string]$Cible,
    [string]$Dump
)

. "$PSScriptRoot\_commun.ps1"

$repo    = Get-RepoHome
$python  = Get-PythonExe -RepoHome $repo
$manifPy = Get-Tool -RepoHome $repo "tools\synthese\manifeste.py"
$gardePy = Get-Tool -RepoHome $repo "tools\synthese\garde_fou.py"
$NOM_MANIFESTE = "synthese.manifeste.json"

function Show-AideSynthese {
    Write-Host ""
    Write-Host "ia synthese — synthese multi-entretiens" -ForegroundColor Cyan
    Write-Host "  ia synthese init [perimetre]      " -NoNewline -ForegroundColor Green; Write-Host "Pre-genere $NOM_MANIFESTE (scan recursif)"
    Write-Host "  ia synthese verifier [manifeste]  " -NoNewline -ForegroundColor Green; Write-Host "Garde-fou anti-fuite (avant tout envoi IA)"
    Write-Host ""
    Write-Host "  Flux : init -> editer le manifeste (inclure/role/interviewe) -> verifier." -ForegroundColor Gray
    Write-Host ""
}

switch ($Action) {

    "init" {
        $perim = if ($Cible) { $Cible } else { (Get-Location).Path }
        if (-not (Test-Path -LiteralPath $perim)) { Write-Echec "Perimetre introuvable : $perim"; exit 1 }
        Write-Etape "Generation du manifeste de synthese"
        & $python $manifPy init $perim
        exit $LASTEXITCODE
    }

    "verifier" {
        $manif = if ($Cible) { $Cible } else { Join-Path (Get-Location).Path $NOM_MANIFESTE }
        if (-not (Test-Path -LiteralPath $manif)) {
            Write-Echec "Manifeste introuvable : $manif"
            Write-Info  "Genere-le d'abord : ia synthese init"
            exit 1
        }
        Write-Etape "Garde-fou : verification anti-fuite"
        $pyArgs = @($gardePy, $manif)
        if ($Dump) { $pyArgs += @("--dump", $Dump) }
        & $python @pyArgs
        $code = $LASTEXITCODE
        if ($code -eq 0) { Write-Ok "Payload sur : aucun vrai nom detecte." }
        else { Write-Avert "Verification non passee (voir ci-dessus) — ne pas envoyer en l'etat." }
        exit $code
    }

    default {
        if ($Action) { Write-Echec "Sous-commande inconnue : '$Action'" }
        Show-AideSynthese
        if ($Action) { exit 1 }
    }
}
