# =============================================================================
# veille.ps1 — Surveillance + orchestration EN CONTINU.
#
# Deux usages complementaires :
#
#   1) BOUCLE TERMINAL (vision live, travail actif) sur UN perimetre :
#        .\veille.ps1 "D:\...\Interviews"              # tick toutes les 60 s
#        .\veille.ps1 "D:\...\Interviews" -Intervalle 30 -Clair
#      Ctrl+C pour arreter. Chaque tick = un appel a orchestrer.ps1.
#
#   2) TACHES PLANIFIEES WINDOWS (filet de securite, survit au redemarrage) qui
#      scannent un REGISTRE de repertoires (config\perimetres.json) :
#        .\veille.ps1 -Inscrire "D:\...\Interviews"    # inscrit + installe les taches au besoin
#        .\veille.ps1 -Desinscrire "D:\...\Interviews" # desinscrit
#        .\veille.ps1 -Lister                          # repertoires inscrits
#        .\veille.ps1 -Installer                       # (re)installe les taches (mode registre)
#        .\veille.ps1 -Desinstaller                    # retire les taches
#        .\veille.ps1 -Statut                          # etat des taches + registre
#
#      Les taches ne referencent PLUS un perimetre fige : elles lisent le registre
#      a chaque tick. Inscrire/desinscrire un dossier = editer ce registre, sans
#      toucher aux taches. DEUX taches INDEPENDANTES (pour que l'une ne bloque
#      jamais l'autre) :
#        - "Orchestrateur" (toutes les IntervalleMin, defaut 5) : pour CHAQUE
#          perimetre inscrit, sync + couper/anonymiser + transcription INLINE.
#        - "Etat" (toutes les IntervalleEtatMin, defaut 2) : regenere ETAT.md de
#          chaque perimetre (lecture seule, cf. _etat_tache.ps1). Toujours a jour,
#          MEME pendant une transcription.
#
# La boucle terminal et les taches partagent le meme tick idempotent et le meme
# verrou de transcription : les cumuler est redondant mais SANS danger.
# =============================================================================

[CmdletBinding(DefaultParameterSetName = "Boucle")]
param(
    [Parameter(Position = 0)] [string]$Perimetre = ".",
    # Boucle terminal
    [Parameter(ParameterSetName = "Boucle")] [int]$Intervalle = 60,   # secondes
    [Parameter(ParameterSetName = "Boucle")] [switch]$Clair,
    [Parameter(ParameterSetName = "Boucle")] [switch]$NoTranscribe,
    # Taches planifiees : cycle de vie
    [Parameter(ParameterSetName = "Install")]   [switch]$Installer,
    [Parameter(ParameterSetName = "Install")]   [int]$IntervalleMin = 5,
    [Parameter(ParameterSetName = "Install")]   [int]$IntervalleEtatMin = 2,
    [Parameter(ParameterSetName = "Desinstall")][switch]$Desinstaller,
    [Parameter(ParameterSetName = "Statut")]    [switch]$Statut,
    # Registre des perimetres
    [Parameter(ParameterSetName = "Inscrire")]   [switch]$Inscrire,
    [Parameter(ParameterSetName = "Desinscrire")][switch]$Desinscrire,
    [Parameter(ParameterSetName = "Lister")]     [switch]$Lister
)

. "$PSScriptRoot\_commun.ps1"

$TacheNom    = "IA-Powered-OS - Orchestrateur"   # transcription (inline, longue)
$TacheEtat   = "IA-Powered-OS - Etat"            # rafraichit ETAT.md (legere)
$orchestrer    = Join-Path $PSScriptRoot "orchestrer.ps1"
$lanceurTache  = Join-Path $PSScriptRoot "_tache.ps1"
$lanceurEtat   = Join-Path $PSScriptRoot "_etat_tache.ps1"
$shimSilencieux = Join-Path $PSScriptRoot "_silent.vbs"

# Resout l'executable PowerShell pour la tache planifiee. ATTENTION : sur une
# installation Store/MSIX, (Get-Command pwsh).Source pointe vers un chemin
# WindowsApps VERSIONNE (ex. ...Microsoft.PowerShell_7.6.2.0_x64...\pwsh.exe) qui
# DISPARAIT a chaque mise a jour de pwsh -> le chemin grave dans la tache devient
# introuvable (wscript : "chemin d'acces introuvable", 0x80070003). On prefere
# donc l'alias d'execution %LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe, stable
# d'une version a l'autre.
function Get-PsExe {
    $alias = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\pwsh.exe"
    if (Test-Path -LiteralPath $alias) { return $alias }
    if (Get-Command pwsh -ErrorAction SilentlyContinue) { return (Get-Command pwsh).Source }
    return (Get-Command powershell).Source
}

# Enregistre une tache planifiee : repetition indefinie toutes les N min, logon
# interactif, SANS blocage batterie. Avec -Silencieux : lance via wscript +
# _silent.vbs => AUCUNE fenetre, sans droits admin. Le lanceur ne recoit PLUS de
# perimetre : il lit le registre (config\perimetres.json) a chaque tick.
function Register-Tache {
    param([string]$Nom, [string]$Lanceur, [int]$IntervalleMin, [switch]$Silencieux)
    if ($Silencieux) {
        $exe = "$env:WINDIR\System32\wscript.exe"
        $argLine = '"{0}" "{1}" -NoProfile -ExecutionPolicy Bypass -File "{2}"' -f $shimSilencieux, (Get-PsExe), $Lanceur
    } else {
        $exe = Get-PsExe
        $argLine = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Lanceur`""
    }
    $action    = New-ScheduledTaskAction -Execute $exe -Argument $argLine -WorkingDirectory (Get-RepoHome)
    $trigger   = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
                   -RepetitionInterval (New-TimeSpan -Minutes $IntervalleMin)
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
    $settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    $settings.DisallowStartIfOnBatteries = $false
    $settings.StopIfGoingOnBatteries     = $false
    Register-ScheduledTask -TaskName $Nom -Action $action -Trigger $trigger `
                   -Principal $principal -Settings $settings -Force | Out-Null
}

function Test-TachesInstallees {
    foreach ($n in @($TacheNom, $TacheEtat)) {
        if (-not (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue)) { return $false }
    }
    return $true
}

function Install-Taches {
    param([int]$IntervalleMin, [int]$IntervalleEtatMin)
    # Deux taches independantes : la transcription (longue, inline) ne bloque pas
    # le rafraichissement de ETAT.md (tache "Etat", legere et frequente).
    Register-Tache -Nom $TacheNom  -Lanceur $lanceurTache -IntervalleMin $IntervalleMin     -Silencieux
    Register-Tache -Nom $TacheEtat -Lanceur $lanceurEtat  -IntervalleMin $IntervalleEtatMin -Silencieux
}

function Uninstall-Taches {
    # Retire les deux taches si presentes. Retourne le nombre effectivement retire.
    $n = 0
    foreach ($nom in @($TacheNom, $TacheEtat)) {
        if (Get-ScheduledTask -TaskName $nom -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $nom -Confirm:$false
            $n++
        }
    }
    return $n
}

function Show-Inscrits {
    $inscrits = @(Read-Perimetres)
    Write-Host ""
    Write-Host "Repertoires inscrits (scannes par les taches planifiees)" -ForegroundColor Cyan
    if (-not $inscrits.Count) {
        Write-Host "  (aucun)" -ForegroundColor DarkGray
        Write-Host "  Inscrire : ia veille -Inscrire <dossier>" -ForegroundColor Gray
    } else {
        $auMoinsUnManquant = $false
        foreach ($d in $inscrits) {
            if (Test-Path -LiteralPath $d) {
                Write-Host ("    {0}" -f $d) -ForegroundColor Gray
            } else {
                Write-Host ("  ! {0}" -f $d) -ForegroundColor Yellow
                $auMoinsUnManquant = $true
            }
        }
        if ($auMoinsUnManquant) { Write-Host "  (! = introuvable sur le disque)" -ForegroundColor DarkYellow }
    }
    Write-Host ("  Fichier : {0}" -f (Get-PerimetresPath)) -ForegroundColor DarkGray
    Write-Host ""
}

# =============================================================================
# REGISTRE : inscrire / desinscrire / lister
# =============================================================================
if ($Inscrire) {
    if (-not $PSBoundParameters.ContainsKey('Perimetre')) {
        Write-Echec "Precise le dossier a inscrire : ia veille -Inscrire <dossier>"; exit 1
    }
    try { $r = Add-Perimetre -Chemin $Perimetre } catch { Write-Echec $_; exit 1 }
    if ($r.Ajoute) { Write-Ok "Repertoire inscrit : $($r.Chemin)" }
    else           { Write-Info "Deja inscrit : $($r.Chemin)" }

    # Activation AUTO : si le registre etait vide (aucune tache), on (re)active la
    # surveillance. Sinon les taches tournent deja et prendront le dossier au tick.
    if (-not (Test-TachesInstallees)) {
        Write-Info "Activation de la surveillance (registre precedemment vide)..."
        Install-Taches -IntervalleMin $IntervalleMin -IntervalleEtatMin $IntervalleEtatMin
        Write-Ok "Taches planifiees activees (orchestrateur $IntervalleMin min, etat $IntervalleEtatMin min)."
    } else {
        Write-Info "Surveillance deja active : le dossier sera pris au prochain tick."
    }
    Show-Inscrits
    return
}

if ($Desinscrire) {
    if (-not $PSBoundParameters.ContainsKey('Perimetre')) {
        Write-Echec "Precise le dossier a desinscrire : ia veille -Desinscrire <dossier>"; exit 1
    }
    $r = Remove-Perimetre -Chemin $Perimetre
    if ($r.Retire) { Write-Ok "Repertoire desinscrit : $($r.Chemin)" }
    else {
        Write-Avert "Ce repertoire n'etait pas inscrit : $($r.Chemin)"
        Write-Info  "Voir la liste : ia veille -Lister"
    }
    # Desactivation AUTO : si c'etait le DERNIER repertoire, plus rien a scanner ->
    # on retire les taches planifiees (elles se reactiveront au prochain -Inscrire).
    if ($r.Reste.Count -eq 0) {
        $retires = Uninstall-Taches
        if ($retires) {
            Write-Avert "Dernier repertoire retire : surveillance DESACTIVEE (taches planifiees supprimees)."
            Write-Info  "Elle se reactivera automatiquement au prochain : ia veille -Inscrire <dossier>"
        } else {
            Write-Info "Plus aucun repertoire inscrit (aucune tache active)."
        }
    } else {
        Show-Inscrits
    }
    return
}

if ($Lister) {
    Show-Inscrits
    if (Test-TachesInstallees) { Write-Info "Taches planifiees : actives (ia veille -Statut pour le detail)." }
    else                       { Write-Avert "Taches planifiees : NON installees (ia veille -Inscrire <dossier> les installe)." }
    return
}

# =============================================================================
# TACHE PLANIFIEE : statut / desinstallation / installation
# =============================================================================
if ($Statut) {
    $trouve = $false
    foreach ($n in @($TacheNom, $TacheEtat)) {
        $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
        if (-not $t) { Write-Info "Aucune tache '$n'." ; continue }
        $trouve = $true
        $info = Get-ScheduledTaskInfo -TaskName $n
        Write-Host ""
        Write-Host "Tache       : $n" -ForegroundColor Cyan
        Write-Host "Etat        : $($t.State)   (repetition $($t.Triggers[0].Repetition.Interval))"
        Write-Host "Derniere    : $($info.LastRunTime)  (resultat $($info.LastTaskResult))"
        Write-Host "Prochaine   : $($info.NextRunTime)"
    }
    if (-not $trouve) { Write-Avert "Taches planifiees non installees (ia veille -Inscrire <dossier>)." }
    Show-Inscrits
    return
}

if ($Desinstaller) {
    $n = Uninstall-Taches
    if ($n) { Write-Ok "Taches planifiees desinstallees ($n)." }
    else    { Write-Avert "Aucune tache a desinstaller." }
    Write-Info "Le registre des perimetres est conserve (ia veille -Lister). Reactiver : ia veille -Inscrire <dossier>."
    return
}

if ($Installer) {
    # Optionnel : un perimetre passe explicitement est inscrit au passage
    # (retrocompat : `ia veille -Installer "D:\...\Interviews"`).
    if ($PSBoundParameters.ContainsKey('Perimetre') -and $Perimetre -ne ".") {
        try {
            $r = Add-Perimetre -Chemin $Perimetre
            if ($r.Ajoute) { Write-Ok "Repertoire inscrit : $($r.Chemin)" } else { Write-Info "Deja inscrit : $($r.Chemin)" }
        } catch { Write-Echec $_; exit 1 }
    }
    Install-Taches -IntervalleMin $IntervalleMin -IntervalleEtatMin $IntervalleEtatMin
    Write-Ok "Taches planifiees installees :"
    Write-Info "  '$TacheNom'  (transcription INLINE + couper/anonymiser) : toutes les $IntervalleMin min"
    Write-Info "  '$TacheEtat' (rafraichit ETAT.md, lecture seule)        : toutes les $IntervalleEtatMin min"
    Write-Info "Les taches scannent les repertoires INSCRITS (registre) :"
    Show-Inscrits
    if (-not (Read-Perimetres).Count) {
        Write-Avert "Aucun repertoire inscrit : les taches tournent a vide tant que tu n'inscris rien."
        Write-Info  "Inscris-en un : ia veille -Inscrire <dossier>"
    }
    Write-Info "Statut : ia veille -Statut    |    Retrait : ia veille -Desinstaller"
    Write-Avert "Transcription : une seule a la fois (verrou), longue, en arriere-plan."
    return
}

# =============================================================================
# BOUCLE TERMINAL (defaut)
# =============================================================================
if (-not (Test-Path -LiteralPath $Perimetre)) { Write-Echec "Perimetre introuvable : $Perimetre"; exit 1 }
$perim = (Resolve-Path -LiteralPath $Perimetre).Path

Write-Host ""
Write-Host "Veille IA-Powered-OS — boucle d'orchestration" -ForegroundColor Cyan
Write-Host "  Perimetre  : $perim" -ForegroundColor Gray
Write-Host "  Intervalle : $Intervalle s   (Ctrl+C pour arreter)" -ForegroundColor Gray
Write-Host ""

$passthru = @()
if ($NoTranscribe) { $passthru += "-NoTranscribe" }

try {
    while ($true) {
        if ($Clair) { Clear-Host }
        Write-Host ("===== Tick : {0} =====" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -ForegroundColor DarkCyan
        & $orchestrer $perim @passthru
        Write-Host ("(prochain tick dans {0} s — Ctrl+C pour arreter)" -f $Intervalle) -ForegroundColor DarkGray
        Start-Sleep -Seconds $Intervalle
    }
} finally {
    Write-Host ""
    Write-Info "Veille arretee."
}
