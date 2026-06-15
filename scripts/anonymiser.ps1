# =============================================================================
# anonymiser.ps1 — Pipeline d'anonymisation en DEUX temps (etape sensible).
#
# A lancer DEPUIS le repertoire racine de l'entretien.
#
#   .\anonymiser.ps1 detecter     # 1) detection NER -> ouvre l'editeur d'alias
#                                  #    (tu valides, l'alias.yaml est ecrit au
#                                  #     niveau du perimetre)
#   .\anonymiser.ps1 appliquer    # 2) applique l'alias -> transcript anonymise
#                                  #    + table, dans 3_anonymisation\
#
# Le perimetre (alias.yaml + table_correspondance.json) est trouve par
# recherche ASCENDANTE depuis l'entretien. Au tout premier entretien d'un
# perimetre, un alias.yaml vide est cree dans le parent immediat.
#
# /!\ Etape sensible : une erreur = fuite de donnees. Relis toujours le
#     transcript anonymise avant tout envoi a une IA externe.
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)] [ValidateSet("detecter", "appliquer")] [string]$Commande,
    [string]$Transcript,
    [int]$Port = 8770,
    [switch]$NoBrowser
)

. "$PSScriptRoot\_commun.ps1"

if (-not $Commande) {
    Write-Echec "Precise la commande : 'detecter' ou 'appliquer'."
    Write-Info  "  .\anonymiser.ps1 detecter    puis    .\anonymiser.ps1 appliquer"
    exit 1
}

$repo   = Get-RepoHome
$python = Get-PythonExe -RepoHome $repo

# --- Resolution du transcript source -----------------------------------------
if ($Transcript) {
    if (-not (Test-Path -LiteralPath $Transcript)) { Write-Echec "Transcript introuvable : $Transcript"; exit 1 }
    $src = (Resolve-Path -LiteralPath $Transcript).Path
} else {
    $src = Find-TranscriptSource
    if (-not $src) {
        Write-Echec "Aucun transcript .srt trouve (ni dans 2_coupe\, ni dans 1_transcription\)."
        Write-Info  "Lance d'abord .\transcrire.ps1 (et eventuellement .\taguer.ps1 + .\couper.ps1)."
        exit 1
    }
}
$srcItem = Get-Item -LiteralPath $src
Write-Info "Transcript source : $($srcItem.Name)  (dans $($srcItem.Directory.Name)\)"

# --- Resolution du perimetre (alias + table par recherche ascendante) --------
$perim = Resolve-Perimetre
if ($perim.AliasExiste) {
    Write-Info "Perimetre (alias trouve) : $($perim.Dir)"
} else {
    Write-Avert "Aucun alias.yaml en remontant : un nouveau perimetre sera initialise dans $($perim.Dir)"
}

$anonDir = Get-SousDossier "3_anonymisation" -Creer

# =============================================================================
# COMMANDE : detecter
# =============================================================================
if ($Commande -eq "detecter") {
    $detecter = Get-Tool -RepoHome $repo "tools\anonymisation\detecter.py"
    $serveur  = Get-Tool -RepoHome $repo "tools\anonymisation\serveur_editeur.py"
    $editeur  = Get-Tool -RepoHome $repo "tools\anonymisation\editeur_alias.html"

    $etatOut = Join-Path $anonDir "$($srcItem.BaseName).etat.json"

    Write-Etape "1/2 Detection des entites (NER local)"
    $pyArgs = @($detecter, $src, "--out", $etatOut)
    if ($perim.AliasExiste) { $pyArgs += @("--alias", $perim.AliasPath) }
    if (Test-Path -LiteralPath $perim.TablePath) { $pyArgs += @("--table", $perim.TablePath) }

    & $python @pyArgs
    if ($LASTEXITCODE -ne 0) { Write-Echec "La detection a echoue (code $LASTEXITCODE)."; exit $LASTEXITCODE }
    if (-not (Test-Path -LiteralPath $etatOut)) { Write-Echec "Etat de detection non produit."; exit 1 }
    Write-Ok "Etat de detection : 3_anonymisation\$($srcItem.BaseName).etat.json"

    Write-Etape "Validation humaine — ouverture de l'editeur d'alias"
    Write-Info "Valide les entites, puis clique « Exporter alias.yaml »."
    Write-Info "L'alias sera ecrit ici : $($perim.AliasPath)"
    Write-Info "Ferme l'onglet quand tu as termine (le serveur s'arrete seul)."

    $srvArgs = @($serveur, "--etat", $etatOut, "--alias", $perim.AliasPath, "--editeur", $editeur, "--port", $Port)
    if ($NoBrowser) { $srvArgs += "--no-browser" }
    & $python @srvArgs

    Write-Ok "Detection + validation terminees."
    Write-Info "Etape suivante : .\anonymiser.ps1 appliquer"
    exit 0
}

# =============================================================================
# COMMANDE : appliquer
# =============================================================================
if ($Commande -eq "appliquer") {
    $appliquer = Get-Tool -RepoHome $repo "tools\anonymisation\appliquer.py"

    if (-not (Test-Path -LiteralPath $perim.AliasPath)) {
        Write-Echec "alias.yaml introuvable : $($perim.AliasPath)"
        Write-Info  "Lance d'abord .\anonymiser.ps1 detecter et valide l'alias."
        exit 1
    }

    Write-Etape "2/2 Application de l'anonymisation"
    Write-Info "Alias : $($perim.AliasPath)"

    # appliquer.py ecrit transcript_anonymise + rapport + table dans --outdir.
    # On vise 3_anonymisation\ ; la table sera ensuite remontee au perimetre.
    $pyArgs = @($appliquer, $src, "--alias", $perim.AliasPath, "--outdir", $anonDir)
    if (Test-Path -LiteralPath $perim.TablePath) { $pyArgs += @("--table", $perim.TablePath) }

    & $python @pyArgs
    if ($LASTEXITCODE -ne 0) { Write-Echec "L'application a echoue (code $LASTEXITCODE)."; exit $LASTEXITCODE }

    # --- Remonter la table au niveau du perimetre (et non dans 3_anonymisation) -
    $tableProduite = Join-Path $anonDir "table_correspondance.json"
    if (Test-Path -LiteralPath $tableProduite) {
        Move-Item -LiteralPath $tableProduite -Destination $perim.TablePath -Force
        Write-Ok "Table de correspondance (LOCALE) : $($perim.TablePath)"
    } else {
        Write-Avert "table_correspondance.json non produite la ou attendu."
    }

    $anonFile = Join-Path $anonDir "$($srcItem.BaseName)_anonymise$($srcItem.Extension)"
    if (Test-Path -LiteralPath $anonFile) {
        Write-Ok "Transcript anonymise : 3_anonymisation\$($srcItem.BaseName)_anonymise$($srcItem.Extension)"
    }
    Write-Avert "RELIS le transcript anonymise avant tout envoi a une IA externe."
    Write-Avert "NE JAMAIS envoyer table_correspondance.json (contient les vrais noms)."
    exit 0
}
