# =============================================================================
# orchestrer.ps1 — UNE PASSE d'orchestration du pipeline (tick).
#
# Affiche le tableau d'avancement de tous les entretiens d'un PERIMETRE, puis
# realise automatiquement ce qui est automatisable :
#   - couper      (plan_de_coupe.json present, audio coupe manquant)   [rapide]
#   - anonymiser  (analyse VALIDEE + memoire presente, sortie manquante)[rapide]
#   - transcrire  (audio sans transcription)        [LONG -> arriere-plan serialise]
#
# Les etapes humaines (taguer, analyser) sont seulement SIGNALEES.
#
# Brique reutilisable : appelee une fois (a la main), en boucle (veille.ps1) ou
# par une tache planifiee Windows. Idempotente : relancable sans effet de bord.
#
# Usage :
#   .\orchestrer.ps1                       # perimetre = repertoire courant
#   .\orchestrer.ps1 "D:\...\Interviews"   # perimetre explicite
#   .\orchestrer.ps1 -DryRun               # affiche + liste sans rien executer
#   .\orchestrer.ps1 -NoTranscribe         # n'enclenche pas de transcription
#   .\orchestrer.ps1 -NoEtatMd             # n'ecrit pas ETAT.md au perimetre
#
# Sortie : tableau console + ETAT.md (au perimetre) + execution des etapes auto.
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Perimetre = ".",
    [switch]$DryRun,
    [switch]$NoTranscribe,
    [switch]$NoEtatMd,
    [switch]$TranscribeInline
)

. "$PSScriptRoot\_commun.ps1"

# IMPORTANT : la tache planifiee tourne en `pwsh -NoProfile`, dont l'encodage
# console par defaut est l'OEM (CP850) et NON UTF-8. La sortie JSON d'etat.py est
# en UTF-8 : sans cette ligne, les caracteres accentues des chemins sont corrompus
# (ex. "Presentation" -> "Pr├®sentation") et `Push-Location` echoue sur ces
# dossiers -> la transcription ne demarre jamais. On force donc UTF-8.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repo    = Get-RepoHome
$python  = Get-PythonExe -RepoHome $repo
$etatPy  = Get-Tool -RepoHome $repo "tools\orchestrateur\etat.py"
$syncPy  = Get-Tool -RepoHome $repo "tools\orchestrateur\sync.py"
$wTrans  = Join-Path $PSScriptRoot "transcrire.ps1"
$wCouper = Join-Path $PSScriptRoot "couper.ps1"
$wAnon   = Join-Path $PSScriptRoot "anonymisation.ps1"

# --- Auto-skip d'une transcription qui CASSE (ne se relance pas a l'infini) ---
# Une transcription qui meurt AVANT d'avoir produit le moindre troncon (process
# tue, sortie precoce...) bloquerait l'orchestrateur sur le meme fichier a chaque
# tick. On compte les tentatives DANS entretien.json (champ durable
# `tentatives_auto`, ignore par etat.py/sync.py) avec le nombre de troncons deja
# faits au moment du lancement (`progres_auto`). Au tick suivant, si le dernier
# lancement est mort :
#   - il a PROGRESSE (plus de troncons) -> vraie interruption, on laisse reprendre ;
#   - il n'a RIEN produit $MaxTentatives fois -> on marque `echec` (quarantaine) :
#     le fichier sort des candidats et l'orchestrateur passe au suivant.
$MaxTentatives = 2

function Read-ProjetAt {
    param([string]$Chemin)
    $p = Join-Path $Chemin "entretien.json"
    if (Test-Path -LiteralPath $p) {
        try { return (Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { }
    }
    return $null
}
function Write-ProjetAt {
    param([string]$Chemin, $Projet)
    $Projet.maj_le = (Now-Iso)
    ($Projet | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath (Join-Path $Chemin "entretien.json") -Encoding UTF8
}
function Set-Champ {
    param($Obj, [string]$Nom, $Valeur)
    if ($Obj.PSObject.Properties.Name -contains $Nom) { $Obj.$Nom = $Valeur }
    else { $Obj | Add-Member -NotePropertyName $Nom -NotePropertyValue $Valeur -Force }
}
function Get-Champ {
    param($Obj, [string]$Nom, $Defaut)
    if ($Obj.PSObject.Properties.Name -contains $Nom) { return $Obj.$Nom }
    return $Defaut
}
function Get-NbTroncons {
    # Nombre de troncons DEJA transcrits (chunk_*.json) pour un stem ; 0 si aucun.
    param([string]$Stem)
    if (-not $Stem) { return 0 }
    $root = Join-Path $repo "data\.chunks"
    if (-not (Test-Path -LiteralPath $root)) { return 0 }
    $rx = "^\d{8}-" + [regex]::Escape($Stem) + "$"
    $dirs = @(Get-ChildItem -LiteralPath $root -Directory -EA SilentlyContinue | Where-Object { $_.Name -match $rx })
    if (-not $dirs.Count) { return 0 }
    $d = ($dirs | Sort-Object LastWriteTime -Descending)[0]
    return @(Get-ChildItem -LiteralPath $d.FullName -Filter 'chunk_*.json' -EA SilentlyContinue).Count
}

if (-not (Test-Path -LiteralPath $Perimetre)) { Write-Echec "Perimetre introuvable : $Perimetre"; exit 1 }
$perim = (Resolve-Path -LiteralPath $Perimetre).Path

# --- 0) Sync : aligne les entretien.json sur la realite du disque (upgrade-only)
# La memoire « par projet » reflete ainsi les taches reellement faites, meme pour
# des etapes realisees hors orchestrateur (migration, version anterieure).
& $python $syncPy $perim | Out-Null

# --- 1) Tableau (console) ----------------------------------------------------
& $python $etatPy $perim --format table | Out-Host

# --- 2) Etat machine (JSON) pour les decisions -------------------------------
$rawJson = & $python $etatPy $perim --format json
try { $etat = $rawJson | ConvertFrom-Json }
catch { Write-Echec "Lecture de l'etat (JSON) impossible."; exit 1 }

# --- 3) ETAT.md au perimetre (vision permanente) -----------------------------
if (-not $NoEtatMd) {
    $etatMd = Join-Path $perim "ETAT.md"
    & $python $etatPy $perim --format md --out $etatMd | Out-Null
}

# --- Helper : execute une etape auto SYNCHRONE dans le dossier d'un entretien -
function Invoke-EtapeAuto {
    param([string]$Chemin, [string]$Libelle, [scriptblock]$Action)
    Write-Etape "AUTO [$Libelle] : $(Split-Path -Leaf $Chemin)"
    Push-Location -LiteralPath $Chemin
    try { & $Action }
    catch { Write-Echec "[$Libelle] $(Split-Path -Leaf $Chemin) : $_" }
    finally { Pop-Location }
}

# --- 4) Etapes RAPIDES : couper puis anonymiser ------------------------------
$aCouper = @($etat.entretiens | Where-Object { $_.action -eq "couper" })
$aAnon   = @($etat.entretiens | Where-Object { $_.action -eq "anonymiser" })

if ($DryRun) {
    Write-Avert "DryRun : aucune execution. Seraient lances :"
    foreach ($e in $aCouper) { Write-Info "  couper     -> $($e.dossier)" }
    foreach ($e in $aAnon)   { Write-Info "  anonymiser -> $($e.dossier)" }
} else {
    foreach ($e in $aCouper) {
        Invoke-EtapeAuto -Chemin $e.chemin -Libelle "couper" -Action { & $wCouper }
    }
    foreach ($e in $aAnon) {
        Invoke-EtapeAuto -Chemin $e.chemin -Libelle "anonymiser" -Action { & $wAnon appliquer }
    }
}

# --- 5) TRANSCRIPTION : longue -> 1 seule a la fois, en arriere-plan ----------
# Serialisation AUTO-REPARANTE. Invariant : toute transcription lancee par
# l'orchestrateur ecrit un VERROU portant son PID ; tant que ce PID vit, le
# verrou est "actif". Donc :
#   - "running" == verrou actif (PID vivant) — et RIEN d'autre.
#   - un statut 'en_cours' SANS verrou actif = run mort (process tue, terminal
#     ferme, crash) : il est PERIME et l'entretien redevient eligible (la
#     transcription REPREND aux troncons deja sauvegardes).
# On ne relance PAS un 'echec' (signale pour decision manuelle, pas de boucle de
# retry sur panne durable).
$lock = Join-Path (Get-LogsDir) ".transcription.lock"
$verrouActif = $false
$verrouDossier = $null
$exclure = @()                 # chemins mis en quarantaine pendant CE tick
if (Test-Path -LiteralPath $lock) {
    $info = $null
    try { $info = Get-Content -LiteralPath $lock -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
    if ($info -and $info.pid -and (Get-Process -Id $info.pid -ErrorAction SilentlyContinue)) {
        $verrouActif = $true
        $verrouDossier = $info.dossier
    } else {
        # Verrou perime : le DERNIER lancement est MORT. On "sonde" ce fichier.
        if ($info -and $info.chemin) {
            $mort = $etat.entretiens | Where-Object { $_.chemin -eq $info.chemin } | Select-Object -First 1
            if ($mort -and $mort.transcription -ne "fait") {
                $proj = Read-ProjetAt $info.chemin
                if ($proj) {
                    $tr = $proj.etapes.transcription
                    $tent = [int](Get-Champ $tr 'tentatives_auto' 0)
                    $progresAvant = [int](Get-Champ $tr 'progres_auto' 0)
                    $progresMaint = Get-NbTroncons -Stem $mort.stem
                    if ($progresMaint -gt $progresAvant) {
                        Set-Champ $tr 'tentatives_auto' 0      # a avance -> vraie interruption
                        Write-ProjetAt $info.chemin $proj
                        Write-Info "Transcription interrompue mais AVANCEE ($progresMaint troncons) : $($mort.dossier) — reprise au besoin."
                    } elseif ($tent -ge $MaxTentatives) {
                        $tr.statut  = "echec"
                        $tr.message = "Cassee $tent fois sans produire de troncon (process tue avant demarrage). Mise de cote auto ; relancer a la main : ia transcrire."
                        Write-ProjetAt $info.chemin $proj
                        $exclure += $info.chemin
                        Write-Avert "Transcription mise de cote (cassee $tent x sans progres) : $($mort.dossier). Passage au fichier suivant."
                    } else {
                        Write-Info "Derniere transcription morte sans progres ($($mort.dossier), tentative $tent/$MaxTentatives) — nouvel essai possible."
                    }
                }
            }
        }
        Remove-Item -LiteralPath $lock -Force -ErrorAction SilentlyContinue   # verrou perime
    }
}

$enEchec = @($etat.entretiens | Where-Object { $_.action -eq "transcrire" -and $_.transcription -eq "echec" })
foreach ($e in $enEchec) {
    Write-Avert "Transcription en ECHEC : $($e.dossier) — relancer a la main (ia transcrire) apres diagnostic du log."
}

# Candidats : a transcrire et statut 'a_faire' OU 'en_cours' perime (= reprise).
# (Sans verrou actif, un 'en_cours' ne peut etre qu'un run mort : on le reprend.)
$candidats = @($etat.entretiens | Where-Object {
    $_.action -eq "transcrire" -and $_.transcription -in @("a_faire", "en_cours") -and
    ($exclure -notcontains $_.chemin) })

if ($NoTranscribe) {
    if ($candidats.Count) { Write-Info "Transcription(s) en attente (non lancees, -NoTranscribe) : $($candidats.dossier -join ', ')" }
} elseif ($verrouActif) {
    Write-Info "Transcription deja en cours (verrou PID actif : $verrouDossier) — file : $($candidats.dossier -join ', ')"
} elseif ($candidats.Count -eq 0) {
    # rien a transcrire
} elseif ($DryRun) {
    Write-Avert "DryRun : transcription qui serait lancee -> $($candidats[0].dossier)"
} else {
    $cible = $candidats[0]
    $reprise = if ($cible.transcription -eq "en_cours") { " (REPRISE d'un run interrompu)" } else { "" }
    # Enregistrer la tentative AVANT le lancement : durable meme si le process
    # meurt avant Start-Etape. tentatives_auto++ et progres_auto = troncons deja
    # faits (pour mesurer un eventuel progres au tick suivant).
    $projC = Read-ProjetAt $cible.chemin
    if ($projC) {
        $trC = $projC.etapes.transcription
        Set-Champ $trC 'tentatives_auto' ([int](Get-Champ $trC 'tentatives_auto' 0) + 1)
        Set-Champ $trC 'progres_auto'    (Get-NbTroncons -Stem $cible.stem)
        if ($trC.statut -ne "en_cours") { Set-Champ $trC 'statut' "en_cours"; Set-Champ $trC 'debut' (Now-Iso) }
        Write-ProjetAt $cible.chemin $projC
    }
    if ($TranscribeInline) {
        # MODE TACHE PLANIFIEE : transcription SYNCHRONE dans CE process. Un
        # process detache (Start-Process) serait tue par le planificateur a la
        # fin du tick ; en inline, le tick DURE le temps de la transcription. Le
        # verrou porte le PID courant (une boucle veille concurrente le verra).
        # MultipleInstances=IgnoreNew empeche tout chevauchement de ticks.
        Write-Etape "AUTO [transcrire] (inline)$reprise : $($cible.dossier)"
        $verrou = [ordered]@{ pid = $PID; dossier = $cible.dossier; chemin = $cible.chemin; debut = (Now-Iso) }
        ($verrou | ConvertTo-Json) | Set-Content -LiteralPath $lock -Encoding UTF8
        Push-Location -LiteralPath $cible.chemin
        try { & $wTrans }
        catch { Write-Echec "[transcrire] $($cible.dossier) : $_" }
        finally { Pop-Location; Remove-Item -LiteralPath $lock -Force -ErrorAction SilentlyContinue }
        Write-Ok "Transcription terminee (inline) : $($cible.dossier)"
    } else {
        # MODE INTERACTIF (boucle veille / lancement manuel) : detache, pour que
        # le tableau continue de se rafraichir pendant la transcription.
        Write-Etape "AUTO [transcrire] (arriere-plan)$reprise : $($cible.dossier)"
        $psExe = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
        $cmd = "Set-Location -LiteralPath `"$($cible.chemin)`"; & `"$wTrans`"; Remove-Item -LiteralPath `"$lock`" -Force -ErrorAction SilentlyContinue"
        $proc = Start-Process -FilePath $psExe `
                    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cmd) `
                    -WindowStyle Hidden -PassThru
        $verrou = [ordered]@{ pid = $proc.Id; dossier = $cible.dossier; chemin = $cible.chemin; debut = (Now-Iso) }
        ($verrou | ConvertTo-Json) | Set-Content -LiteralPath $lock -Encoding UTF8
        Write-Ok "Transcription lancee en arriere-plan (PID $($proc.Id)). Suivi : ia etat (dans le dossier) ou logs\."
        if ($candidats.Count -gt 1) { Write-Info "En file : $(@($candidats | Select-Object -Skip 1).dossier -join ', ')" }
    }
}

Write-Host ""
Write-Info "Tick termine. (Relance pour rafraichir, ou utilise veille.ps1 / la tache planifiee.)"
