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

$repo    = Get-RepoHome
$python  = Get-PythonExe -RepoHome $repo
$etatPy  = Get-Tool -RepoHome $repo "tools\orchestrateur\etat.py"
$syncPy  = Get-Tool -RepoHome $repo "tools\orchestrateur\sync.py"
$wTrans  = Join-Path $PSScriptRoot "transcrire.ps1"
$wCouper = Join-Path $PSScriptRoot "couper.ps1"
$wAnon   = Join-Path $PSScriptRoot "anonymisation.ps1"

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
if (Test-Path -LiteralPath $lock) {
    $info = $null
    try { $info = Get-Content -LiteralPath $lock -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
    if ($info -and $info.pid -and (Get-Process -Id $info.pid -ErrorAction SilentlyContinue)) {
        $verrouActif = $true
        $verrouDossier = $info.dossier
    } else {
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
    $_.action -eq "transcrire" -and $_.transcription -in @("a_faire", "en_cours") })

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
