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
│   └── transcription/  Transcription d'entretiens (WhisperX) + tagueur
├── scripts/          Glue technique, lanceurs, utilitaires courts
├── config/           Modèles de configuration (.env.example)
├── data/             Données locales (gitignoré : audios, transcriptions)
├── .claude/skills/   Pilotage par Claude Code (orchestration du pipeline)
└── requirements.txt  Dépendances Python
```

> Note : `tools/` contient **tes** outils métier. `.claude/skills/` est
> l'emplacement où **Claude Code** découvre ses skills (vocabulaire imposé par
> l'outil) — ce sont des instructions de pilotage qui appellent tes outils.

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

## Pilotage (Claude Code)

| Skill Claude Code | Rôle |
|-------------------|------|
| `orchestration-entretiens` | Découvre, lance, suit et range le pipeline de transcription |

## Plateforme

Conçu et testé sous **Windows 11**. Les scripts d'install sont en PowerShell.
Portage Linux/macOS possible (ffmpeg + Python identiques, scripts à adapter).
