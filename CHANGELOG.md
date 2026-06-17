# Changelog — IA-Powered-OS

Évolutions notables du projet. Format inspiré de [Keep a Changelog](https://keepachangelog.com),
versionnage [SemVer](https://semver.org).

Ce qui reste **à faire** vit dans [`BACKLOG.md`](BACKLOG.md). Une fois un item
réalisé, il est décrit ici (avec son numéro de backlog d'origine entre
parenthèses) et retiré du backlog.

---

## [1.2.0] — 2026-06-17

### Ajouté / Modifié
- **Scission identification / analyse** de l'étape d'anonymisation (la
  pré-analyse automatique est désormais distincte de la validation humaine) :
  - `ia identifier` — **pré-analyse AUTOMATIQUE** : détection NER (`detecter.py`)
    → candidats dans `3_anonymisation/<x>.etat.json`. N'ouvre **plus** l'éditeur.
  - `ia analyser` — **validation HUMAINE seule** : éditeur d'alias sur les
    candidats déjà identifiés ; exige le `.etat.json` (sinon renvoie vers
    `ia identifier`). À l'export, `validation.faite=true` débloque l'anonymisation.

  Auparavant `ia analyser` enchaînait détection **et** éditeur d'un seul bloc.
- **Orchestrateur** : l'identification est exécutée automatiquement parmi les
  étapes rapides, **avant** la transcription (quick win) → les candidats sont
  prêts quand tu passes à la validation.
- **`etat.py`** : nouvelle action `identifier` (auto) distincte d'`analyser`
  (humain). Colonne *Analyse* : `--` à identifier (auto) · `~~` identifié, à
  valider (toi) · `OK` validé.

Outils touchés : `anonymisation.ps1`, `ia.ps1`, `orchestrer.ps1`, `etat.py`.

> Optimisation de cette étape (points durs) : à traiter ensuite.

---

## [1.1.0] — 2026-06-17

### Ajouté
- **Tâche planifiée « État » dédiée** — découple le rafraîchissement de `ETAT.md`
  de la transcription. La transcription reste *inline* (longue, bloquante) ; une
  2ᵉ tâche légère et **indépendante** (`scripts/_etat_tache.ps1`, toutes les 2 min,
  **lecture seule** sauf `ETAT.md`) régénère `ETAT.md` en continu. Résultat :
  l'état — y compris la **progression `n/total` des tronçons** (lue sur le disque
  par `etat.py`) — reste à jour **même pendant** une transcription qui dure des
  heures. Deux instances de tâches distinctes → l'une ne bloque jamais l'autre.
  `veille.ps1 -Installer` installe désormais les **deux** tâches (nouveau
  paramètre `-IntervalleEtatMin`, défaut 2 min).

### Corrigé
- **#19** — `veille.ps1 -Installer` débloque la batterie pour les tâches
  (`DisallowStartIfOnBatteries`/`StopIfGoingOnBatteries` = False). Auparavant, les
  défauts du Planificateur (True) empêchaient la tâche de tourner / la tuaient sur
  batterie ; le correctif n'était appliqué qu'à la main sur la tâche en service.

### Modifié
- `_tache.ps1` (tâche de transcription) passe `-NoEtatMd` : la tâche « État » est
  l'**unique rédactrice** de `ETAT.md` (évite une course d'écriture entre les deux
  tâches).

---

## [1.0.0] — 2026-06-17

Première version versionnée. Consolide le pipeline complet de traitement des
entretiens — **transcrire → taguer → couper → analyser → anonymiser →
repersonnaliser** — et son orchestration automatique sous Windows.

### Pipeline & industrialisation

- **Commande unique `ia`** (#4, 15/06) — dispatcher + fonction de profil
  PowerShell. Wrappers `transcrire` / `taguer` / `couper` / `anonymiser` dans
  `scripts/`. Arborescence constante par entretien (`1_transcription/`,
  `2_coupe/`, `3_anonymisation/`). `alias`/`table` partagés au niveau d'un
  « périmètre » trouvé par **recherche ascendante**. Les wrappers ciblent le
  `python.exe` du venv en absolu (`ia setenv` active le venv à la demande).
  Voir `scripts/GUIDE-USAGE.md`.
- **`entretien.json` + logging centralisé** (#15, 16/06) — fichier projet à la
  racine de chaque entretien (statut/horodatage/durée par étape + chemin du log),
  schéma dans `scripts/SCHEMA-entretien.md`. Log verbeux centralisé dans
  `<repo>/logs/` (stdout+stderr, temps réel via `Tee-Object`), résumé dans
  `entretien.json`. Tous les wrappers instrumentés ; commande `ia etat`.

### Transcription

- **`transcribe_robuste.py`** — découpage en tronçons (ffmpeg), transcription
  Whisper `large-v3` par tronçon avec **point de reprise** (saute les tronçons
  déjà faits), diarisation optionnelle (étiquettes locales à réconcilier dans le
  tagueur), fusion avec dédoublonnage des chevauchements. Option `--outdir`.
- **Serveurs locaux** `serveur_tagueur.py` / `serveur_editeur.py` (127.0.0.1,
  chargement auto audio+srt, arrêt par heartbeat à la fermeture de l'onglet) +
  repli File System Access API / fichier.

### Anonymisation — modèle de persistance unifié (#14 + #8 + #13 + #7 + #12 + #17, 16/06)

- **`memoire_client.json`** : artefact **unique par client** (remplace
  `alias.yaml` + `table_correspondance.json`) mémorisant pseudos + canoniques +
  variantes + types + faux positifs + locuteurs génériques. Édité/versionnable.
  `config/ignorer_global.json` partagé pour les faux positifs universels. Logique
  centralisée dans `tools/anonymisation/memoire.py`. Les `ignorer`/`generiques`
  **survivent désormais entre séances**.
- **`migrer.py`** — conversion ancien format → nouveau.
- **`desanonymiser.py`** (#12) — repersonnalisation des rapports (mapping inverse
  pseudo → canonique, pseudos longs d'abord ; `.txt`/`.md`/`.srt`/`.docx`).
  ⚠️ La sortie `_REPERSONNALISE` contient à nouveau les vraies données : ne jamais
  la renvoyer vers une IA externe.
- **Corrigé #8** — l'éditeur n'impose plus le suffixe `_<chiffre>` ; pseudos
  parlants (`SOCIETE`, `CONSULTANT_1`) valides. Export via `JSON.stringify` (fini
  le générateur YAML bricolé qui corrompait silencieusement les pseudos).
- **Corrigé #13** — le `type` est un champ explicite par entrée (écrit par
  l'éditeur, lu tel quel par `appliquer.py`) ; fini le « tout devient PRODUIT ».
- **Corrigé #7** — UI dédiée aux locuteurs génériques, inclus à l'export.
- **#17** — l'éditeur fusionne la mémoire existante du périmètre avec les
  nouvelles détections sans écraser les regroupements.

Outils touchés : `memoire.py`, `migrer.py`, `desanonymiser.py` (nouveaux),
`detecter.py`, `appliquer.py`, `reconcilier.py`, `editeur_alias.html`,
`serveur_editeur.py`, `anonymisation.ps1`, `_commun.ps1`, `SCHEMA.md`.
Rétrocompatibilité : `--alias`/`--table` encore acceptés (migration à la volée).

### Orchestration multi-entretiens (#18, 16-17/06)

- **`etat.py`** — moteur d'état **lecture seule** : scanne un périmètre, calcule
  par entretien l'état de chaque étape + la **prochaine action** (auto vs humain),
  en réconciliant le système de fichiers (autoritaire) avec `entretien.json`.
  Rendus `table` / `json` / `md` (`ETAT.md`). Affiche la **progression des
  tronçons** d'une transcription en cours (`.. 3/7`, 17/06).
- **`sync.py`** — aligne les `entretien.json` sur le disque (**upgrade-only**,
  idempotent).
- **`orchestrer.ps1`** — **tick** idempotent : sync + tableau + `ETAT.md` +
  exécution de l'automatisable. `couper`/`anonymiser` synchrones (rapides) ;
  `transcrire` **une seule à la fois** (verrou PID + reprise des `en_cours`
  périmés). Options `-DryRun`, `-NoTranscribe`, `-NoEtatMd`, `-TranscribeInline`.
- **`veille.ps1`** — surveillance continue : boucle terminal **et** tâche
  planifiée Windows (`-Installer`/`-IntervalleMin`/`-Desinstaller`/`-Statut`),
  fenêtre **masquée** (`-WindowStyle Hidden`, 17/06), intervalle par défaut
  **5 min** (17/06).
- **`_tache.ps1`** — lanceur de la tâche planifiée (journalise chaque tick,
  force le mode transcription **inline**).
- **`ia.ps1`** — commandes `ia tableau` / `ia orchestrer` / `ia veille`.
- **Déclenchement de l'anonymisation auto** : `serveur_editeur.py` estampille le
  `.etat.json` (`validation.faite=true`) à l'export réussi de la mémoire ; c'est
  cette trace de **validation humaine** qui autorise l'anonymisation auto.
- **Gotcha planificateur (résolu)** : un process *détaché* serait tué en fin de
  tick → la tâche transcrit **en inline** (synchrone) ; `MultipleInstances=IgnoreNew`
  empêche le chevauchement. Sérialisation **auto-réparante** (reprise aux
  tronçons sauvegardés après un kill).

### Corrigé (17/06)

- **Transcription cassée sur les dossiers accentués** — la tâche tourne en
  `pwsh -NoProfile`, dont `[Console]::OutputEncoding` par défaut est l'OEM
  (CP850) et non UTF-8 : le JSON UTF-8 d'`etat.py` était mal décodé, les chemins
  accentués corrompus (`Pr├®sentation`), et `Push-Location` échouait → la
  transcription ne démarrait jamais. Fix : `[Console]::OutputEncoding = UTF8` en
  tête d'`orchestrer.ps1`.
- **Auto-skip des fichiers qui cassent** — champs durables
  `tentatives_auto`/`progres_auto` dans `entretien.json` (écrits avant le
  lancement, survivent à `Start-Etape`/`sync`/`etat`). Si un fichier meurt sans
  produire de tronçon `$MaxTentatives` (2) fois → statut `echec` (quarantaine) →
  l'orchestrateur passe au suivant au lieu de boucler indéfiniment.

### Notes d'exploitation

- Tâche planifiée : intervalle **5 min**, fenêtre masquée, réglages batterie
  débloqués (`DisallowStartIfOnBatteries`/`StopIfGoingOnBatteries` = False) pour
  ne pas être bloquée/tuée sur batterie. ⚠️ Ces réglages batterie ne sont pas
  encore portés dans `veille.ps1 -Installer` (une réinstallation les remettrait
  par défaut).
- Validé sous Windows (16-17/06) : tableau, couper auto, sérialisation et reprise
  de transcription, sync, cycle install/désinstall de la tâche, transcriptions
  complètes (Nicolas, Cedric), correctif accents.

[1.2.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.2.0
[1.1.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.1.0
[1.0.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.0.0
