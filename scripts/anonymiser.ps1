# =============================================================================
# anonymiser.ps1 — Pipeline d'anonymisation en TROIS temps (etape sensible).
#
# A lancer DEPUIS le repertoire racine de l'entretien.
#
#   ia analyser          # 1) detection NER -> ouvre l'editeur (tu valides ;
#                        #    memoire_client.json ecrite au niveau du perimetre)
#   ia anonymiser        # 2) applique -> transcript anonymise dans 3_anonymisation\
#   ia repersonnaliser   # 3) (apres l'IA externe) reinjecte les vrais noms (#12)
#
# Etapes internes (ce wrapper) : detecter / appliquer / repersonnaliser.
#
# Le perimetre (memoire_client.json) est trouve par recherche ASCENDANTE
# depuis l'entretien. Au tout premier entretien d'un perimetre, une
# memoire_client.json est creee dans le parent immediat.
#
# Suivi (entretien.json + logs centralises) : les trois sous-commandes sont
# instrumentees sous l'etape "anonymisation" (champ details.sous_etape). C'est
# 'appliquer' qui porte le statut final 'fait'/'echec' ; 'detecter' laisse le
# statut en 'en_cours' (validation a faire) ; 'repersonnaliser' (post-traitement
# inverse) est trace sans redefinir l'avancement du cycle d'anonymisation.
# Voir scripts/SCHEMA-entretien.md.
#
# /!\ Etape sensible : une erreur = fuite de donnees. Relis toujours le
#     transcript anonymise avant tout envoi a une IA externe.
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)] [ValidateSet("detecter", "appliquer", "repersonnaliser")] [string]$Commande,
    [string]$Transcript,
    [string]$Rapport,
    [switch]$Court,
    [int]$Port = 8770,
    [switch]$NoBrowser
)

. "$PSScriptRoot\_commun.ps1"

if (-not $Commande) {
    Write-Echec "Precise la commande : 'detecter', 'appliquer' ou 'repersonnaliser'."
    Write-Info  "  ia analyser    puis    ia anonymiser    puis    ia repersonnaliser"
    exit 1
}

$repo   = Get-RepoHome
$python = Get-PythonExe -RepoHome $repo

# --- Resolution du transcript source (uniquement pour detecter/appliquer) -----
# 'repersonnaliser' ne part pas d'un transcript mais d'un RAPPORT : on saute
# cette resolution dans ce cas.
$src = $null; $srcItem = $null
if ($Commande -ne "repersonnaliser") {
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
}

# --- Resolution du perimetre (memoire_client.json par recherche ascendante) ---
$perim = Resolve-Perimetre
if ($perim.MemoireExiste) {
    Write-Info "Perimetre (memoire trouvee) : $($perim.Dir)"
} elseif ($perim.AncienAlias) {
    Write-Avert "Ancien format detecte (alias.yaml) sans memoire_client.json."
    Write-Info  "Migre-le une fois en memoire unique :"
    Write-Info  "  & `$python `"`$repo\tools\anonymisation\migrer.py`" --dir `"$($perim.Dir)`""
    Write-Avert "En attendant, une nouvelle memoire sera initialisee dans $($perim.Dir)"
} else {
    Write-Avert "Aucune memoire_client.json en remontant : un nouveau perimetre sera initialise dans $($perim.Dir)"
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

    Write-Etape "Analyse : detection des entites (NER local)"
    $pyArgs = @($detecter, $src, "--out", $etatOut)
    if ($perim.MemoireExiste) { $pyArgs += @("--memoire", $perim.MemoirePath) }
    $ignGlobal = Join-Path $repo "config\ignorer_global.json"
    if (Test-Path -LiteralPath $ignGlobal) { $pyArgs += @("--ignorer-global", $ignGlobal) }

    # 'detecter' est une SOUS-ETAPE de l'anonymisation : on trace la detection
    # (sous_etape = detecter) mais on NE finalise PAS le statut a 'fait' ici.
    # L'anonymisation n'est reellement terminee qu'apres 'appliquer'. A l'image
    # de taguer.ps1, on laisse le statut en 'en_cours' a la sortie (la validation
    # humaine + l'application restent a faire).
    $ctx = Start-Etape -Etape "anonymisation" -Details @{ sous_etape = "detecter"; transcript = $srcItem.Name }
    Write-Info "Log detaille : $($ctx.LogFile)"
    $code = Invoke-Logge -Contexte $ctx -Exe $python -Arguments $pyArgs
    if ($code -ne 0) {
        Complete-Etape -Contexte $ctx -Statut "echec" -Message "detecter.py a renvoye le code $code"
        Write-Echec "La detection a echoue (code $code). Voir le log : $($ctx.LogFile)"
        exit $code
    }
    if (-not (Test-Path -LiteralPath $etatOut)) {
        Complete-Etape -Contexte $ctx -Statut "echec" -Message "Etat de detection non produit"
        Write-Echec "Etat de detection non produit. Voir le log : $($ctx.LogFile)"
        exit 1
    }
    Write-Ok "Etat de detection : 3_anonymisation\$($srcItem.BaseName).etat.json"

    Write-Etape "Validation humaine — ouverture de l'editeur d'alias"
    Write-Info "Valide les entites, puis clique « Exporter la memoire »."
    Write-Info "La memoire sera ecrite ici : $($perim.MemoirePath)"
    Write-Info "Ferme l'onglet quand tu as termine (le serveur s'arrete seul)."

    # La detection a reussi mais l'anonymisation reste a faire : on remet
    # explicitement le statut en 'en_cours' (le statut ne ment pas sur
    # l'avancement reel). Le log de detection est conserve dans entretien.json.
    $projet = Read-Projet
    $projet.etapes.anonymisation.statut = "en_cours"
    Write-Projet $projet

    $srvArgs = @($serveur, "--etat", $etatOut, "--memoire", $perim.MemoirePath, "--editeur", $editeur, "--port", $Port)
    if ($NoBrowser) { $srvArgs += "--no-browser" }
    # Session serveur interactive : on la trace dans le meme log, sans en faire
    # une etape distincte (le statut reste 'en_cours').
    & $python @srvArgs 2>&1 | Tee-Object -FilePath $ctx.LogFile -Append | Out-Host
    Add-Content -LiteralPath $ctx.LogFile -Value "`r`n--- Session editeur d'alias terminee (serveur arrete) ---" -Encoding UTF8

    Write-Ok "Detection + validation terminees."
    Write-Info "Etape suivante : ia anonymiser"
    exit 0
}

# =============================================================================
# COMMANDE : appliquer
# =============================================================================
if ($Commande -eq "appliquer") {
    $appliquer = Get-Tool -RepoHome $repo "tools\anonymisation\appliquer.py"

    if (-not (Test-Path -LiteralPath $perim.MemoirePath)) {
        Write-Echec "memoire_client.json introuvable : $($perim.MemoirePath)"
        Write-Info  "Lance d'abord .\anonymiser.ps1 detecter et exporte la memoire."
        exit 1
    }

    Write-Etape "Anonymisation : application du remplacement"
    Write-Info "Memoire : $($perim.MemoirePath)"

    # appliquer.py ecrit transcript_anonymise + rapport dans --outdir, et
    # met a jour la memoire DIRECTEMENT au perimetre (--memoire-out).
    $ignGlobal = Join-Path $repo "config\ignorer_global.json"
    $pyArgs = @($appliquer, $src, "--memoire", $perim.MemoirePath, "--outdir", $anonDir,
                "--memoire-out", $perim.MemoirePath)
    if (Test-Path -LiteralPath $ignGlobal) { $pyArgs += @("--ignorer-global", $ignGlobal) }

    # 'appliquer' est l'action qui TERMINE l'anonymisation : c'est elle qui
    # porte le statut final 'fait'/'echec' de l'etape 'anonymisation'.
    $ctx = Start-Etape -Etape "anonymisation" -Details @{ sous_etape = "appliquer"; transcript = $srcItem.Name }
    Write-Info "Log detaille : $($ctx.LogFile)"
    $code = Invoke-Logge -Contexte $ctx -Exe $python -Arguments $pyArgs
    if ($code -ne 0) {
        Complete-Etape -Contexte $ctx -Statut "echec" -Message "appliquer.py a renvoye le code $code"
        Write-Echec "L'application a echoue (code $code). Voir le log : $($ctx.LogFile)"
        exit $code
    }

    Write-Ok "Memoire (LOCALE) mise a jour : $($perim.MemoirePath)"

    $anonFile = Join-Path $anonDir "$($srcItem.BaseName)_anonymise$($srcItem.Extension)"
    if (Test-Path -LiteralPath $anonFile) {
        Complete-Etape -Contexte $ctx -Statut "fait"
        Write-Ok "Transcript anonymise : 3_anonymisation\$($srcItem.BaseName)_anonymise$($srcItem.Extension)"
    } else {
        Complete-Etape -Contexte $ctx -Statut "echec" -Message "Transcript anonymise non produit"
        Write-Avert "Transcript anonymise attendu non trouve. Voir le log : $($ctx.LogFile)"
    }
    Write-Avert "RELIS le transcript anonymise avant tout envoi a une IA externe."
    Write-Avert "NE JAMAIS envoyer memoire_client.json (contient les vrais noms)."
    exit 0
}

# =============================================================================
# COMMANDE : repersonnaliser  (chemin inverse #12)
# =============================================================================
if ($Commande -eq "repersonnaliser") {
    $desanon = Get-Tool -RepoHome $repo "tools\anonymisation\desanonymiser.py"

    if (-not (Test-Path -LiteralPath $perim.MemoirePath)) {
        Write-Echec "memoire_client.json introuvable : $($perim.MemoirePath)"
        Write-Info  "La repersonnalisation a besoin de la memoire du perimetre (vrais noms)."
        exit 1
    }

    # Resolution du rapport a repersonnaliser : -Rapport explicite, sinon on
    # cherche un rapport plausible dans 3_anonymisation\ (les *_REPONSE / *.md).
    if ($Rapport) {
        if (-not (Test-Path -LiteralPath $Rapport)) { Write-Echec "Rapport introuvable : $Rapport"; exit 1 }
        $rep = (Resolve-Path -LiteralPath $Rapport).Path
    } else {
        $cand = @(Get-ChildItem -LiteralPath $anonDir -File -ErrorAction SilentlyContinue |
                  Where-Object { $_.Extension -in ".md", ".txt", ".docx", ".srt" -and
                                 $_.Name -notmatch "_anonymise|_rapport|\.etat\." } |
                  Sort-Object LastWriteTime -Descending)
        if ($cand.Count -eq 0) {
            Write-Echec "Aucun rapport a repersonnaliser dans 3_anonymisation\."
            Write-Info  "Precise le fichier : ia repersonnaliser -Rapport `"chemin\rapport.md`""
            exit 1
        }
        $rep = $cand[0].FullName
        Write-Info "Rapport (le plus recent) : $($cand[0].Name)"
    }

    Write-Etape "Repersonnalisation (reinjection des vrais noms)"
    Write-Info "Memoire : $($perim.MemoirePath)"

    $pyArgs = @($desanon, $rep, "--memoire", $perim.MemoirePath)
    if ($Court) { $pyArgs += "--court" }

    # 'repersonnaliser' est un POST-TRAITEMENT inverse (#12), posterieur au cycle
    # d'anonymisation : on le trace dans un log dedie (sous_etape) SANS ecraser
    # le statut 'fait' deja porte par 'appliquer'. On sauvegarde puis on restaure
    # le statut de l'etape anonymisation autour de l'execution loggee.
    $statutAvant = (Read-Projet).etapes.anonymisation.statut
    $ctx = Start-Etape -Etape "anonymisation" -Details @{ sous_etape = "repersonnaliser"; rapport = (Split-Path -Leaf $rep) }
    Write-Info "Log detaille : $($ctx.LogFile)"
    $code = Invoke-Logge -Contexte $ctx -Exe $python -Arguments $pyArgs
    if ($code -ne 0) {
        Complete-Etape -Contexte $ctx -Statut "echec" -Message "desanonymiser.py a renvoye le code $code"
        Write-Echec "La repersonnalisation a echoue (code $code). Voir le log : $($ctx.LogFile)"
        exit $code
    }
    # Succes : on cloture le log, puis on RESTAURE le statut anterieur de
    # l'anonymisation (la repersonnalisation ne doit pas redefinir l'avancement
    # du cycle d'anonymisation lui-meme).
    Complete-Etape -Contexte $ctx -Statut "fait"
    $projet = Read-Projet
    if ($statutAvant) { $projet.etapes.anonymisation.statut = $statutAvant }
    Write-Projet $projet

    Write-Avert "Le fichier *_REPERSONNALISE contient les VRAIS NOMS : usage LOCAL uniquement."
    Write-Avert "NE JAMAIS le renvoyer a une IA externe."
    exit 0
}
