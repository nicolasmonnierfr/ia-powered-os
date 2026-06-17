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
#   2) TACHES PLANIFIEES WINDOWS (filet de securite, survit au redemarrage) :
#        .\veille.ps1 "D:\...\Interviews" -Installer
#        .\veille.ps1 "D:\...\Interviews" -Installer -IntervalleMin 10 -IntervalleEtatMin 3
#        .\veille.ps1 -Desinstaller
#        .\veille.ps1 -Statut
#
#      DEUX taches INDEPENDANTES (pour que l'une ne bloque jamais l'autre) :
#        - "Orchestrateur" (toutes les IntervalleMin, defaut 5) : sync +
#          couper/anonymiser + transcription INLINE (longue). Reste bloquee
#          pendant une transcription -> ne peut pas rafraichir l'etat.
#        - "Etat" (toutes les IntervalleEtatMin, defaut 2) : regenere ETAT.md
#          SEUL (lecture seule, cf. _etat_tache.ps1). Toujours a jour, y compris
#          la progression "n/total" des troncons, MEME pendant une transcription.
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
    # Tache planifiee
    [Parameter(ParameterSetName = "Install")]   [switch]$Installer,
    [Parameter(ParameterSetName = "Install")]   [int]$IntervalleMin = 5,
    [Parameter(ParameterSetName = "Install")]   [int]$IntervalleEtatMin = 2,
    [Parameter(ParameterSetName = "Desinstall")][switch]$Desinstaller,
    [Parameter(ParameterSetName = "Statut")]    [switch]$Statut
)

. "$PSScriptRoot\_commun.ps1"

$TacheNom    = "IA-Powered-OS - Orchestrateur"   # transcription (inline, longue)
$TacheEtat   = "IA-Powered-OS - Etat"            # rafraichit ETAT.md (legere)
$orchestrer    = Join-Path $PSScriptRoot "orchestrer.ps1"
$lanceurTache  = Join-Path $PSScriptRoot "_tache.ps1"
$lanceurEtat   = Join-Path $PSScriptRoot "_etat_tache.ps1"
function Get-PsExe { if (Get-Command pwsh -ErrorAction SilentlyContinue) { (Get-Command pwsh).Source } else { (Get-Command powershell).Source } }

# Enregistre une tache planifiee : action = pwsh -Hidden -File <lanceur>
# -Perimetre, repetition indefinie toutes les N min, logon interactif, SANS
# blocage batterie (#19 : sinon DisallowStart/StopIfGoingOnBatteries=True par
# defaut -> la tache ne tourne pas / est tuee sur batterie).
function Register-Tache {
    param([string]$Nom, [string]$Lanceur, [string]$Perim, [int]$IntervalleMin)
    $argLine   = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Lanceur`" -Perimetre `"$Perim`""
    $action    = New-ScheduledTaskAction -Execute (Get-PsExe) -Argument $argLine -WorkingDirectory (Get-RepoHome)
    $trigger   = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
                   -RepetitionInterval (New-TimeSpan -Minutes $IntervalleMin)
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
    $settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    $settings.DisallowStartIfOnBatteries = $false
    $settings.StopIfGoingOnBatteries     = $false
    Register-ScheduledTask -TaskName $Nom -Action $action -Trigger $trigger `
                   -Principal $principal -Settings $settings -Force | Out-Null
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
    if ($trouve) { Write-Host "" }
    return
}

if ($Desinstaller) {
    $n = 0
    foreach ($nom in @($TacheNom, $TacheEtat)) {
        if (Get-ScheduledTask -TaskName $nom -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $nom -Confirm:$false
            Write-Ok "Tache '$nom' desinstallee."
            $n++
        }
    }
    if (-not $n) { Write-Avert "Aucune tache a desinstaller." }
    return
}

if ($Installer) {
    if (-not (Test-Path -LiteralPath $Perimetre)) { Write-Echec "Perimetre introuvable : $Perimetre"; exit 1 }
    $perim = (Resolve-Path -LiteralPath $Perimetre).Path
    # Deux taches independantes : la transcription (longue, inline) ne bloque pas
    # le rafraichissement de ETAT.md (tache "Etat", legere et frequente).
    Register-Tache -Nom $TacheNom  -Lanceur $lanceurTache -Perim $perim -IntervalleMin $IntervalleMin
    Register-Tache -Nom $TacheEtat -Lanceur $lanceurEtat  -Perim $perim -IntervalleMin $IntervalleEtatMin
    Write-Ok "Taches planifiees installees :"
    Write-Info "  '$TacheNom'  (transcription INLINE + couper/anonymiser) : toutes les $IntervalleMin min"
    Write-Info "  '$TacheEtat' (rafraichit ETAT.md, lecture seule)        : toutes les $IntervalleEtatMin min"
    Write-Info "Perimetre : $perim"
    Write-Info "Statut : .\veille.ps1 -Statut    |    Retrait : .\veille.ps1 -Desinstaller"
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
