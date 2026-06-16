# =============================================================================
# veille.ps1 — Surveillance + orchestration EN CONTINU.
#
# Deux usages complementaires (tu as choisi « les deux ») :
#
#   1) BOUCLE TERMINAL (vision live, travail actif) :
#        .\veille.ps1 "D:\...\Interviews"              # tick toutes les 60 s
#        .\veille.ps1 "D:\...\Interviews" -Intervalle 30 -Clair
#      Ctrl+C pour arreter. Chaque tick = un appel a orchestrer.ps1.
#
#   2) TACHE PLANIFIEE WINDOWS (filet de securite, survit au redemarrage) :
#        .\veille.ps1 "D:\...\Interviews" -Installer            # toutes les 10 min
#        .\veille.ps1 "D:\...\Interviews" -Installer -IntervalleMin 15
#        .\veille.ps1 -Desinstaller
#        .\veille.ps1 -Statut                                   # etat de la tache
#
# La boucle et la tache partagent le meme tick idempotent (orchestrer.ps1) et
# le meme verrou de transcription : les lancer toutes les deux est redondant
# mais SANS danger (jamais deux transcriptions en parallele).
# =============================================================================

[CmdletBinding(DefaultParameterSetName = "Boucle")]
param(
    [Parameter(Position = 0)] [string]$Perimetre = ".",
    # Boucle terminal
    [Parameter(ParameterSetName = "Boucle")] [int]$Intervalle = 60,   # secondes
    [Parameter(ParameterSetName = "Boucle")] [switch]$Clair,
    [Parameter(ParameterSetName = "Boucle")] [switch]$NoTranscribe,
    # Tache planifiee
    [Parameter(ParameterSetName = "Install")]   [switch]$Installer,
    [Parameter(ParameterSetName = "Install")]   [int]$IntervalleMin = 10,
    [Parameter(ParameterSetName = "Desinstall")][switch]$Desinstaller,
    [Parameter(ParameterSetName = "Statut")]    [switch]$Statut
)

. "$PSScriptRoot\_commun.ps1"

$TacheNom = "IA-Powered-OS - Orchestrateur"
$orchestrer = Join-Path $PSScriptRoot "orchestrer.ps1"
$lanceurTache = Join-Path $PSScriptRoot "_tache.ps1"
function Get-PsExe { if (Get-Command pwsh -ErrorAction SilentlyContinue) { (Get-Command pwsh).Source } else { (Get-Command powershell).Source } }

# =============================================================================
# TACHE PLANIFIEE : statut / desinstallation / installation
# =============================================================================
if ($Statut) {
    $t = Get-ScheduledTask -TaskName $TacheNom -ErrorAction SilentlyContinue
    if (-not $t) { Write-Info "Aucune tache planifiee '$TacheNom'." ; return }
    $info = Get-ScheduledTaskInfo -TaskName $TacheNom
    Write-Host ""
    Write-Host "Tache       : $TacheNom" -ForegroundColor Cyan
    Write-Host "Etat        : $($t.State)"
    Write-Host "Derniere    : $($info.LastRunTime)  (resultat $($info.LastTaskResult))"
    Write-Host "Prochaine   : $($info.NextRunTime)"
    Write-Host ""
    return
}

if ($Desinstaller) {
    $t = Get-ScheduledTask -TaskName $TacheNom -ErrorAction SilentlyContinue
    if (-not $t) { Write-Avert "Aucune tache '$TacheNom' a desinstaller." ; return }
    Unregister-ScheduledTask -TaskName $TacheNom -Confirm:$false
    Write-Ok "Tache planifiee '$TacheNom' desinstallee."
    return
}

if ($Installer) {
    if (-not (Test-Path -LiteralPath $Perimetre)) { Write-Echec "Perimetre introuvable : $Perimetre"; exit 1 }
    $perim = (Resolve-Path -LiteralPath $Perimetre).Path
    $psExe = Get-PsExe
    # Action : le lanceur _tache.ps1 (tick INLINE + journalisation). On passe par
    # un lanceur dedie car (1) la transcription doit etre synchrone sous le
    # planificateur, (2) la tache n'a pas de console -> log dans logs\.
    # -WindowStyle Hidden : pas de console visible pendant les ticks (la
    # transcription inline dure plusieurs minutes -> sinon une fenetre reste
    # ouverte tout du long). Un bref flash au demarrage du tick reste possible
    # sous le planificateur ; pour le supprimer totalement il faudrait un shim
    # wscript/conhost --headless (non retenu ici pour rester simple/reversible).
    $argLine = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$lanceurTache`" -Perimetre `"$perim`""
    $action  = New-ScheduledTaskAction -Execute $psExe -Argument $argLine -WorkingDirectory (Get-RepoHome)
    # Declencheur : repetition indefinie toutes les N minutes (a partir de maintenant).
    $debut   = (Get-Date).AddMinutes(1)
    $trigger = New-ScheduledTaskTrigger -Once -At $debut `
                 -RepetitionInterval (New-TimeSpan -Minutes $IntervalleMin)
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
    $settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
                 -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $TacheNom -Action $action -Trigger $trigger `
                 -Principal $principal -Settings $settings -Force | Out-Null
    Write-Ok "Tache planifiee installee : '$TacheNom'"
    Write-Info "Perimetre : $perim"
    Write-Info "Frequence : toutes les $IntervalleMin min (1re execution vers $($debut.ToString('HH:mm')))."
    Write-Info "Statut : .\veille.ps1 -Statut    |    Retrait : .\veille.ps1 -Desinstaller"
    Write-Avert "La transcription (longue) est lancee en arriere-plan par les ticks ; un seul a la fois."
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
