# IA-Powered-OS

Environnement de travail personnel pour le traitement de missions de conseil
assisté par IA. Regroupe des outils, scripts et configurations réutilisables et
redéployables sur n'importe quelle machine.

## Philosophie

Ce repo ne contient **pas** l'environnement installé, mais **la recette pour le
reconstruire**. Sur une nouvelle machine :

```
git clone <url>
cd IA-Powered-OS
# suivre bootstrap/setup-windows.ps1
```

## Structure

```
IA-Powered-OS/
├── bootstrap/        Scripts d'installation (prérequis système, venv)
├── tools/            Outils métier exécutables
│   ├── transcription/  Transcription d'entretiens (WhisperX) + tagueur + serveur
│   └── anonymisation/  Anonymisation locale des transcripts (Presidio) + éditeur + serveur
├── scripts/          Commande `ia` + wrappers (industrialisation du pipeline)
├── config/           Modèles de configuration (.env.example)
├── data/             Données locales (gitignoré : intermédiaires .chunks/)
└── requirements.txt  Dépendances Python
```

> Note : `tools/` contient **tes** outils métier exécutables. Les outils
> s'appellent depuis le dossier d'une mission (le répertoire courant) : les
> livrables y sont écrits, les intermédiaires restent dans `data/.chunks/`.

## Règles d'or

- **Aucun secret dans Git** : tokens et clés vont dans `config/.env`
  (gitignoré). Le modèle est `config/.env.example`.
- **Aucune donnée sensible dans Git** : tout `data/` est exclu.
- **Tout est reproductible** : tout binaire installé manuellement doit être
  documenté dans un script de `bootstrap/`.

## Outils disponibles

| Outil | Description | État |
|-------|-------------|------|
| `tools/transcription` | Transcription + diarisation d'entretiens (WhisperX, local) + tagueur | En cours |
| `tools/anonymisation` | Anonymisation locale des transcripts (Presidio/spaCy FR) avec pseudonymes cohérents et mémoire client unique réutilisable (+ dé-anonymisation) | En cours |

## Commande `ia` (industrialisation)

Le pipeline complet se pilote via une commande unique, lancée **depuis le
dossier d'un entretien** : `ia transcrire`, `ia taguer`, `ia couper`,
`ia analyser` / `ia anonymiser` / `ia repersonnaliser`. Installation : `.\scripts\installer-ia.ps1`.
Voir `scripts/GUIDE-USAGE.md`.

> L'orchestration par Claude Code (pilotage automatique du pipeline) sera
> ajoutée ultérieurement, sous `.claude/skills/`.

## Plateforme

Conçu et testé sous **Windows 11**. Les scripts d'install sont en PowerShell.
Portage Linux/macOS possible (ffmpeg + Python identiques, scripts à adapter).
