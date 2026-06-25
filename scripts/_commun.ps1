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

# =============================================================================
# REGISTRE DES PERIMETRES SURVEILLES (taches planifiees `ia veille`)
# =============================================================================
# Les taches planifiees ne scannent plus UN perimetre grave en dur dans leur
# action : elles lisent ce registre a chaque tick. On peut donc inscrire /
# desinscrire un repertoire sans toucher aux taches (ia veille -Inscrire / -Desinscrire / -Lister).
# Fichier LOCAL (chemins de missions client = sensibles) -> gitignore.

function Get-PerimetresPath { return (Join-Path (Get-RepoHome) "config\perimetres.json") }

function Read-Perimetres {
    # Tableau (eventuellement vide) des chemins inscrits, tels qu'enregistres.
    $p = Get-PerimetresPath
    if (-not (Test-Path -LiteralPath $p)) { return @() }
    try {
        $data = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
        return @($data.perimetres | Where-Object { $_ })
    } catch {
        Write-Avert "Registre des perimetres illisible ($p) : $_"
        return @()
    }
}

function Write-Perimetres {
    param([string[]]$Perimetres)
    $p   = Get-PerimetresPath
    $dir = Split-Path -Parent $p
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $obj = [pscustomobject]@{ version = 1; perimetres = [string[]]@($Perimetres) }
    $obj | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $p -Encoding UTF8
}

# Comparaison de chemins Windows : insensible a la casse + barre finale ignoree.
function Test-MemeChemin {
    param([string]$A, [string]$B)
    return ($A.TrimEnd('\') -eq $B.TrimEnd('\'))
}

function Add-Perimetre {
    # Inscrit un repertoire (resolu en absolu, dedoublonne). Retourne un objet
    # { Ajoute = $true/$false ; Chemin = <absolu> }.
    param([Parameter(Mandatory)][string]$Chemin)
    if (-not (Test-Path -LiteralPath $Chemin -PathType Container)) {
        throw "Repertoire introuvable : $Chemin"
    }
    $abs   = (Resolve-Path -LiteralPath $Chemin).Path
    $liste = @(Read-Perimetres)
    foreach ($e in $liste) { if (Test-MemeChemin $e $abs) { return [pscustomobject]@{ Ajoute = $false; Chemin = $abs } } }
    $liste += $abs
    Write-Perimetres -Perimetres $liste
    return [pscustomobject]@{ Ajoute = $true; Chemin = $abs }
}

function Remove-Perimetre {
    # Desinscrit un repertoire. Tolere un dossier deja supprime (pas de Resolve
    # bloquant). Retourne { Retire = $true/$false ; Chemin ; Reste = <tableau> }.
    param([Parameter(Mandatory)][string]$Chemin)
    $cible = $Chemin
    if (Test-Path -LiteralPath $Chemin) { try { $cible = (Resolve-Path -LiteralPath $Chemin).Path } catch {} }
    $liste = @(Read-Perimetres)
    $reste = @($liste | Where-Object { -not (Test-MemeChemin $_ $cible) })
    $retire = ($reste.Count -lt $liste.Count)
    if ($retire) { Write-Perimetres -Perimetres $reste }
    return [pscustomobject]@{ Retire = $retire; Chemin = $cible; Reste = $reste }
}

# =============================================================================
# LOGGING CENTRALISE + FICHIER PROJET (entretien.json)
# =============================================================================
# Deux niveaux (voir scripts/SCHEMA-entretien.md) :
#   - log verbeux  : <repo>\logs\<date>-<heure>-<entretien>-<etape>.log
#   - resume       : <entretien>\entretien.json (statut + horodatage par etape)

function Get-LogsDir {
    $d = Join-Path (Get-RepoHome) "logs"
    if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    return $d
}

function Now-Iso { return (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz") }

# --- Fichier projet ----------------------------------------------------------

function Get-ProjetPath { return (Join-Path (Get-EntretienRoot) "entretien.json") }

function Read-Projet {
    # Retourne l'objet projet (cree un squelette si absent/illisible).
    $p = Get-ProjetPath
    if (Test-Path -LiteralPath $p) {
        try { return (Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json) }
        catch { Write-Avert "entretien.json illisible, recreation." }
    }
    $audio = $null
    try { $audio = (Find-Audio).Name } catch { }
    $mk = { [pscustomobject]@{ statut = "a_faire"; debut = $null; fin = $null; duree_sec = $null; log = $null; details = [pscustomobject]@{}; message = $null } }
    return [pscustomobject]@{
        version   = 1
        entretien = (Split-Path -Leaf (Get-EntretienRoot))
        audio     = $audio
        cree_le   = (Now-Iso)
        maj_le    = (Now-Iso)
        etapes    = [pscustomobject]@{
            transcription = (& $mk)
            coupe         = (& $mk)
            anonymisation = (& $mk)
        }
    }
}

function Write-Projet {
    param([Parameter(Mandatory)] $Projet)
    $Projet.maj_le = (Now-Iso)
    $json = $Projet | ConvertTo-Json -Depth 8
    Set-Content -LiteralPath (Get-ProjetPath) -Value $json -Encoding UTF8
}

# Marque le DEBUT d'une etape : statut en_cours, ouvre le log centralise.
# Retourne un objet contexte a passer a Complete-Etape.
function Start-Etape {
    param(
        [Parameter(Mandatory)][ValidateSet("transcription","coupe","anonymisation")][string]$Etape,
        [hashtable]$Details
    )
    $projet = Read-Projet
    $horoFichier = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $entretien = (Split-Path -Leaf (Get-EntretienRoot))
    $logFile = Join-Path (Get-LogsDir) "$horoFichier-$entretien-$Etape.log"
    $logRel = "logs\" + (Split-Path -Leaf $logFile)

    $e = $projet.etapes.$Etape
    $e.statut = "en_cours"
    $e.debut  = (Now-Iso)
    $e.fin    = $null
    $e.duree_sec = $null
    $e.log    = $logRel
    $e.message = $null
    if ($Details) { $e.details = [pscustomobject]$Details }
    Write-Projet $projet

    # En-tete du log verbeux.
    $head = @(
        "==============================================================",
        " IA-Powered-OS — log d'execution",
        " Etape      : $Etape",
        " Entretien  : $entretien ($(Get-EntretienRoot))",
        " Debut      : $(Now-Iso)",
        "=============================================================="
    ) -join "`r`n"
    Set-Content -LiteralPath $logFile -Value $head -Encoding UTF8

    return [pscustomobject]@{
        Etape     = $Etape
        LogFile   = $logFile
        Debut     = (Get-Date)
    }
}

# Marque la FIN d'une etape : statut fait/echec, duree, message eventuel.
function Complete-Etape {
    param(
        [Parameter(Mandatory)] $Contexte,
        [Parameter(Mandatory)][ValidateSet("fait","echec")][string]$Statut,
        [string]$Message
    )
    $projet = Read-Projet
    $e = $projet.etapes.($Contexte.Etape)
    $e.statut    = $Statut
    $e.fin       = (Now-Iso)
    $e.duree_sec = [int]((Get-Date) - $Contexte.Debut).TotalSeconds
    if ($Message) { $e.message = $Message }
    Write-Projet $projet

    $foot = "`r`n--- Fin ($Statut) a $(Now-Iso), duree $($e.duree_sec)s ---"
    Add-Content -LiteralPath $Contexte.LogFile -Value $foot -Encoding UTF8
}

# Execute un programme externe en capturant sa sortie A LA FOIS a l'ecran ET
# dans le log verbeux (temps reel). Retourne UNIQUEMENT le code de sortie.
function Invoke-Logge {
    param(
        [Parameter(Mandatory)] $Contexte,
        [Parameter(Mandatory)][string]$Exe,
        [Parameter(Mandatory)][object[]]$Arguments
    )
    Add-Content -LiteralPath $Contexte.LogFile -Value "`r`n> $Exe $($Arguments -join ' ')`r`n" -Encoding UTF8
    # 2>&1 fusionne stderr ; Tee-Object affiche ET ecrit dans le log.
    # IMPORTANT : on encadre le pipeline pour que la sortie parte a l'ecran/log
    # mais NE soit PAS la valeur de retour de la fonction (sinon le code serait
    # pollue par tout le flux). On lit $LASTEXITCODE juste apres.
    & $Exe @Arguments 2>&1 | Tee-Object -FilePath $Contexte.LogFile -Append | Out-Host
    return $LASTEXITCODE
}
