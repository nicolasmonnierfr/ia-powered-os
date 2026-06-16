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
#   ia analyser          # detection NER + editeur (ecrit memoire_client.json)
#   ia anonymiser        # applique le remplacement -> transcript anonymise
#   ia repersonnaliser [-Rapport f] [-Court]   # reinjecte les vrais noms (#12)
#   ia etat              # affiche l'avancement de l'entretien courant
#   ia tableau [perim]   # vue globale de tous les entretiens d'un perimetre
#   ia orchestrer [perim]# une passe : tableau + execution de l'automatisable
#   ia veille [perim]    # surveillance continue (boucle / tache planifiee)
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
    Write-Host "  ia analyser                      " -NoNewline -ForegroundColor Green; Write-Host "Detection NER + editeur -> memoire_client.json"
    Write-Host "  ia anonymiser                    " -NoNewline -ForegroundColor Green; Write-Host "Applique le remplacement -> 3_anonymisation\"
    Write-Host "  ia repersonnaliser [-Rapport f]  " -NoNewline -ForegroundColor Green; Write-Host "Reinjecte les vrais noms dans un rapport (#12)"
    Write-Host "  ia etat                          " -NoNewline -ForegroundColor Green; Write-Host "Avancement de l'entretien courant (entretien.json)"
    Write-Host "  ia tableau [perimetre]           " -NoNewline -ForegroundColor Green; Write-Host "Vue globale de tous les entretiens"
    Write-Host "  ia orchestrer [perimetre]        " -NoNewline -ForegroundColor Green; Write-Host "Une passe : tableau + execute l'automatisable"
    Write-Host "  ia veille [perimetre]            " -NoNewline -ForegroundColor Green; Write-Host "Surveillance continue (boucle / tache planifiee)"
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

function Show-Etat {
    $p = Get-ProjetPath
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Avert "Aucun entretien.json ici. Lance une commande (ex. ia transcrire) pour l'initialiser,"
        Write-Info  "ou place-toi dans le repertoire racine d'un entretien."
        return
    }
    $projet = Read-Projet
    Write-Host ""
    Write-Host "Entretien : $($projet.entretien)" -ForegroundColor Cyan
    Write-Host "Audio     : $($projet.audio)" -ForegroundColor Gray
    Write-Host "Mis a jour: $($projet.maj_le)" -ForegroundColor Gray
    Write-Host ""
    $libelles = [ordered]@{ transcription = "Transcription"; coupe = "Coupe"; anonymisation = "Anonymisation" }
    foreach ($k in $libelles.Keys) {
        $e = $projet.etapes.$k
        $couleur = switch ($e.statut) {
            "fait"     { "Green" }
            "en_cours" { "Yellow" }
            "echec"    { "Red" }
            default    { "DarkGray" }
        }
        $duree = if ($e.duree_sec) { " ($([int]$e.duree_sec)s)" } else { "" }
        Write-Host ("  {0,-14} " -f $libelles[$k]) -NoNewline
        Write-Host ("{0}{1}" -f $e.statut, $duree) -ForegroundColor $couleur
        if ($e.statut -eq "echec" -and $e.message) {
            Write-Host ("                 -> {0}" -f $e.message) -ForegroundColor Red
        }
        if ($e.log) {
            Write-Host ("                 log: {0}" -f $e.log) -ForegroundColor DarkGray
        }
    }
    Write-Host ""
}

# Wrappers simples : commande -> script.
$map = @{
    "transcrire" = "transcrire.ps1"
    "taguer"     = "taguer.ps1"
    "couper"     = "couper.ps1"
    "orchestrer" = "orchestrer.ps1"
    "veille"     = "veille.ps1"
}

# Commandes d'anonymisation : toutes servies par anonymisation.ps1, avec une ETAPE
# interne injectee en premier argument positionnel. (option A : un seul wrapper)
$mapAnon = @{
    "analyser"        = "detecter"
    "anonymiser"      = "appliquer"
    "repersonnaliser" = "repersonnaliser"
}

function Show-Tableau {
    param([object[]]$ArgsReste)
    $repo   = Get-RepoHome
    $python = Get-PythonExe -RepoHome $repo
    $etatPy = Join-Path $repo "tools\orchestrateur\etat.py"
    if (-not (Test-Path -LiteralPath $etatPy)) { Write-Echec "etat.py introuvable : $etatPy"; return }
    $perim = if ($ArgsReste -and $ArgsReste.Count -ge 1) { [string]$ArgsReste[0] } else { (Get-Location).Path }
    & $python $etatPy $perim --format table
}

switch ($Commande) {
    { $_ -in @($null, "", "aide", "help", "-h", "--help") } { Show-Aide; break }
    "setenv"  { Invoke-Setenv; break }
    "etat"    { Show-Etat; break }
    "tableau" { Show-Tableau -ArgsReste $Reste; break }
    default {
        if ($mapAnon.ContainsKey($Commande)) {
            # anonymisation.ps1 <etape> [args...]
            $cible = Join-Path $PSScriptRoot "anonymisation.ps1"
            $etape = $mapAnon[$Commande]
            & $cible $etape @Reste
            exit $LASTEXITCODE
        } elseif ($map.ContainsKey($Commande)) {
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
