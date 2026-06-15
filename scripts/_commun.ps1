# =============================================================================
# _commun.ps1 — Fonctions partagees par les wrappers IA-Powered-OS.
#
# N'est pas lance directement : il est importe (dot-sourced) par les autres
# scripts via :  . "$PSScriptRoot\_commun.ps1"
#
# Role : localiser le repo, l'interpreteur Python du venv, et fournir des
# helpers d'affichage + de rangement de fichiers dans l'arborescence d'entretien.
# =============================================================================

$ErrorActionPreference = "Stop"

# --- Affichage ---------------------------------------------------------------

function Write-Etape { param([string]$Msg) Write-Host "`n>>> $Msg" -ForegroundColor Cyan }
function Write-Info  { param([string]$Msg) Write-Host "    $Msg" -ForegroundColor Gray }
function Write-Ok    { param([string]$Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Avert { param([string]$Msg) Write-Host "/!\ $Msg" -ForegroundColor Yellow }
function Write-Echec { param([string]$Msg) Write-Host "[ERREUR] $Msg" -ForegroundColor Red }

# --- Localisation du repo IA-Powered-OS --------------------------------------
# Priorite : variable d'environnement IA_POWERED_OS_HOME (meme convention que
# transcribe_robuste.py), sinon remontee depuis l'emplacement de ce script.

function Get-RepoHome {
    $env_home = $env:IA_POWERED_OS_HOME
    if ($env_home -and (Test-Path -LiteralPath $env_home -PathType Container)) {
        return (Resolve-Path -LiteralPath $env_home).Path
    }
    # _commun.ps1 vit dans <repo>/scripts/ ; le repo est le parent.
    $repo = Split-Path -Parent $PSScriptRoot
    if (Test-Path -LiteralPath (Join-Path $repo "requirements.txt")) {
        return $repo
    }
    throw "Impossible de localiser le repo IA-Powered-OS. Definis la variable d'environnement IA_POWERED_OS_HOME."
}

# --- Interpreteur Python du venv ---------------------------------------------

function Get-PythonExe {
    param([string]$RepoHome)
    $venvPy = Join-Path $RepoHome ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) { return $venvPy }
    Write-Avert "venv introuvable ($venvPy) ; repli sur le 'python' du PATH."
    return "python"
}

# --- Chemins des outils ------------------------------------------------------

function Get-Tool {
    param([string]$RepoHome, [string]$RelPath)
    $p = Join-Path $RepoHome $RelPath
    if (-not (Test-Path -LiteralPath $p)) { throw "Outil introuvable : $p" }
    return $p
}

# --- Arborescence d'entretien ------------------------------------------------
# Toutes les commandes sont lancees DEPUIS le repertoire racine de l'entretien
# (celui qui contient l'audio). Ces helpers en derivent les sous-dossiers.

function Get-EntretienRoot { return (Get-Location).Path }

function Get-SousDossier {
    param([string]$Nom, [switch]$Creer)
    $d = Join-Path (Get-EntretienRoot) $Nom
    if ($Creer -and -not (Test-Path -LiteralPath $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
    return $d
}

# Repertoire parent (client/mission) : niveau du memoire_client.json.
function Get-ParentDir { return (Split-Path -Parent (Get-EntretienRoot)) }

# --- Recherche d'audio dans le repertoire courant ----------------------------

$AUDIO_EXTS = @(".m4a",".mp3",".wav",".mp4",".mkv",".webm",".flac",".ogg",".aac",".wma",".opus")

function Find-Audio {
    # Retourne l'unique audio du repertoire courant, ou leve une erreur si 0/plusieurs.
    $audios = Get-ChildItem -LiteralPath (Get-EntretienRoot) -File |
              Where-Object { $AUDIO_EXTS -contains $_.Extension.ToLower() }
    if ($audios.Count -eq 0) {
        throw "Aucun audio dans le repertoire courant. Extensions reconnues : $($AUDIO_EXTS -join ', ')"
    }
    if ($audios.Count -gt 1) {
        throw "Plusieurs audios trouves ($($audios.Count)). Garde un seul audio par repertoire d'entretien, ou precise le fichier."
    }
    return $audios[0]
}

# Deplace un fichier vers un sous-dossier (ecrase si deja present).
function Move-Vers {
    param([string]$Source, [string]$DossierCible)
    if (-not (Test-Path -LiteralPath $Source)) { return $false }
    $dest = Join-Path $DossierCible (Split-Path -Leaf $Source)
    Move-Item -LiteralPath $Source -Destination $dest -Force
    return $true
}

# --- Recherche ascendante memoire_client.json -------------------------------
# Refonte #14 : le perimetre d'anonymisation (= "client") est defini par
# l'emplacement de memoire_client.json (artefact UNIQUE remplacant alias.yaml +
# table_correspondance.json). On remonte les dossiers parents depuis l'entretien
# jusqu'a en trouver un. Le PREMIER trouve (le plus proche) gagne. Si aucun
# n'existe, on en initialisera un dans le parent immediat (gere par le wrapper).
#
# Compat : si aucune memoire mais un ancien alias.yaml est trouve, on le signale
# pour proposer la migration (migrer.py).

function Find-MemoireAscendant {
    # Retourne le chemin du memoire_client.json trouve en remontant, ou $null.
    $dir = Get-ParentDir   # on commence AU-DESSUS de l'entretien
    while ($dir -and (Test-Path -LiteralPath $dir)) {
        $cand = Join-Path $dir "memoire_client.json"
        if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
        $parent = Split-Path -Parent $dir
        if ($parent -eq $dir) { break }   # racine atteinte
        $dir = $parent
    }
    return $null
}

function Find-AncienAliasAscendant {
    # Detecte un ancien alias.yaml (pour proposer la migration). $null sinon.
    $dir = Get-ParentDir
    while ($dir -and (Test-Path -LiteralPath $dir)) {
        $cand = Join-Path $dir "alias.yaml"
        if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
        $parent = Split-Path -Parent $dir
        if ($parent -eq $dir) { break }
        $dir = $parent
    }
    return $null
}

# Resout le perimetre d'anonymisation : renvoie un objet avec
#   MemoirePath   : chemin du memoire_client.json (existant ou a creer)
#   Dir           : dossier du perimetre
#   MemoireExiste : $true si la memoire existait deja
#   AncienAlias   : chemin d'un ancien alias.yaml a migrer, ou $null
# Si aucune memoire n'est trouvee, on cible le parent IMMEDIAT de l'entretien.
function Resolve-Perimetre {
    $found = Find-MemoireAscendant
    if ($found) {
        $dir = Split-Path -Parent $found
        return [pscustomobject]@{
            MemoirePath   = $found
            Dir           = $dir
            MemoireExiste = $true
            AncienAlias   = $null
        }
    }
    $ancien = Find-AncienAliasAscendant
    $parent = if ($ancien) { Split-Path -Parent $ancien } else { Get-ParentDir }
    return [pscustomobject]@{
        MemoirePath   = (Join-Path $parent "memoire_client.json")
        Dir           = $parent
        MemoireExiste = $false
        AncienAlias   = $ancien
    }
}

# Retourne le transcript le plus AVANCE disponible pour l'anonymisation :
# priorite a 2_coupe\<stem>_coupe.srt, repli sur 1_transcription\<stem>.srt.
# Renvoie le chemin, ou $null.
function Find-TranscriptSource {
    $coupe = Get-SousDossier "2_coupe"
    $trans = Get-SousDossier "1_transcription"
    foreach ($d in @($coupe, $trans)) {
        if (Test-Path -LiteralPath $d) {
            $srt = Get-ChildItem -LiteralPath $d -File -Filter *.srt -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($srt) { return $srt.FullName }
        }
    }
    return $null
}
