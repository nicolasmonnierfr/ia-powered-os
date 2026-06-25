# =============================================================================
# _etat_tache.ps1 — Rafraichit ETAT.md SEUL (action de la tache planifiee "Etat").
#
# Volontairement decouple de la transcription : la tache d'orchestration tourne
# en INLINE et reste donc bloquee pendant toute une transcription (des heures),
# ce qui figeait ETAT.md. Cette tache-ci, INDEPENDANTE et legere, regenere
# ETAT.md a frequence rapide -> l'etat (y compris la progression "n/total" des
# troncons, lue sur le disque par etat.py) reste toujours a jour.
#
# Parcourt le REGISTRE des perimetres inscrits (config\perimetres.json) et
# regenere un ETAT.md par perimetre. -Perimetre <chemin> force UN perimetre.
#
# Surete : etat.py est LECTURE SEULE et n'ecrit QUE ETAT.md. Aucune ecriture de
# entretien.json ici -> pas de course avec la tache de transcription (qui, elle,
# ecrit entretien.json + livrables). On NE lance PAS sync.py pour la meme raison.
# =============================================================================

[CmdletBinding()]
param(
    [string]$Perimetre
)

. "$PSScriptRoot\_commun.ps1"

# Cf. orchestrer.ps1 : sous `pwsh -NoProfile`, la console est en OEM (CP850), pas
# UTF-8. Inoffensif ici (etat.py ecrit ETAT.md lui-meme en UTF-8) mais on aligne.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repo   = Get-RepoHome
$python = Get-PythonExe -RepoHome $repo
$etatPy = Get-Tool -RepoHome $repo "tools\orchestrateur\etat.py"

$perims = if ($Perimetre) { @($Perimetre) } else { @(Read-Perimetres) }
if (-not $perims -or $perims.Count -eq 0) { exit 0 }

$rc = 0
foreach ($p in $perims) {
    if (-not (Test-Path -LiteralPath $p)) { continue }
    $perim  = (Resolve-Path -LiteralPath $p).Path
    $etatMd = Join-Path $perim "ETAT.md"
    & $python $etatPy $perim --format md --out $etatMd | Out-Null
    if ($LASTEXITCODE -ne 0) { $rc = $LASTEXITCODE }
}
exit $rc
