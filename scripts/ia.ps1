# =============================================================================
# ia.ps1 — Point d'entree unique des outils IA-Powered-OS (dispatcher).
#
# Aiguille vers les wrappers du dossier scripts\. A utiliser DEPUIS le
# repertoire racine d'un entretien.
#
# Commandes :
#   ia transcrire [audio] [-NoDiarize] [-ChunkMin n] ...
#   ia taguer [-Port n] [-NoBrowser]
#   ia couper [plan] [-Audio f]
#   ia anonymiser detecter|appliquer [-Transcript f] ...
#   ia setenv            # active le venv dans la session courante (python/pip)
#   ia aide              # affiche cette aide
#
# Les arguments apres la commande sont transmis tels quels au wrapper cible.
# =============================================================================

# Pas de [CmdletBinding()]/param() : un param() vide interdirait les arguments
# positionnels. On lit tout via la variable automatique $args, qui preserve la
# nature des tokens (switches) lors du splatting vers les wrappers.

. "$PSScriptRoot\_commun.ps1"

$Commande = if ($args.Count -ge 1) { [string]$args[0] } else { $null }
# Select-Object -Skip 1 garantit un Object[] (meme a 0 ou 1 element) ; un
# simple $args[1..n] retournerait une chaine si un seul element, que @Reste
# splatterait caractere par caractere (bug "d" de detecter).
$Reste = @($args | Select-Object -Skip 1)

function Show-Aide {
    Write-Host ""
    Write-Host "IA-Powered-OS — commandes" -ForegroundColor Cyan
    Write-Host "  (a lancer depuis le repertoire racine d'un entretien)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  ia transcrire [audio]            " -NoNewline -ForegroundColor Green; Write-Host "Transcrit -> 1_transcription\"
    Write-Host "  ia taguer                        " -NoNewline -ForegroundColor Green; Write-Host "Ouvre le tagueur (audio+srt charges) -> 2_coupe\"
    Write-Host "  ia couper [plan]                 " -NoNewline -ForegroundColor Green; Write-Host "Reconstruit l'audio coupe -> 2_coupe\"
    Write-Host "  ia anonymiser detecter           " -NoNewline -ForegroundColor Green; Write-Host "Detection NER + editeur d'alias"
    Write-Host "  ia anonymiser appliquer          " -NoNewline -ForegroundColor Green; Write-Host "Applique -> 3_anonymisation\"
    Write-Host "  ia setenv                        " -NoNewline -ForegroundColor Green; Write-Host "Active le venv (python/pip a la main)"
    Write-Host "  ia aide                          " -NoNewline -ForegroundColor Green; Write-Host "Cette aide"
    Write-Host ""
    Write-Host "  Options : ajoute -? a un wrapper pour son detail, ex. ia transcrire -?" -ForegroundColor Gray
    Write-Host ""
}

function Invoke-Setenv {
    $repo = Get-RepoHome
    $activate = Join-Path $repo ".venv\Scripts\Activate.ps1"
    if (-not (Test-Path -LiteralPath $activate)) {
        Write-Echec "venv introuvable : $activate"
        Write-Info  "Lance d'abord le bootstrap (bootstrap\setup-windows.ps1)."
        return
    }
    # Doit etre dot-source dans la SESSION appelante ; ia.ps1 etant lui-meme
    # appele, on ne peut pas modifier la session parente directement. On informe.
    Write-Avert "Pour activer le venv dans CETTE session, lance plutot :"
    Write-Host  "    . `"$activate`"" -ForegroundColor Yellow
    Write-Info  "(L'activation doit etre dot-sourcee ; une sous-commande ne peut pas"
    Write-Info  " modifier l'environnement de la session parente.)"
}

$map = @{
    "transcrire" = "transcrire.ps1"
    "taguer"     = "taguer.ps1"
    "couper"     = "couper.ps1"
    "anonymiser" = "anonymiser.ps1"
}

switch ($Commande) {
    { $_ -in @($null, "", "aide", "help", "-h", "--help") } { Show-Aide; break }
    "setenv" { Invoke-Setenv; break }
    default {
        if ($map.ContainsKey($Commande)) {
            $cible = Join-Path $PSScriptRoot $map[$Commande]
            if ($Reste.Count) { & $cible @Reste } else { & $cible }
            exit $LASTEXITCODE
        } else {
            Write-Echec "Commande inconnue : '$Commande'"
            Show-Aide
            exit 1
        }
    }
}
