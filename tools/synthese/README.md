# Outil : Synthèse multi-entretiens

Produit, à partir de **plusieurs entretiens anonymisés** d'une mission, une
**synthèse croisée** (thèmes, douleurs, attentes, divergences…) destinée à être
analysée par l'**API Claude**, puis re-personnalisée pour le client via l'outil
existant (`ia repersonnaliser`).

> **État : en cours.** Construit par incréments. Sont livrés : la **définition du
> périmètre** (manifeste), le **garde-fou anti-fuite**, et l'**appel à l'API
> Claude** (`ia synthese lancer`).

## Pourquoi ces fondations d'abord

La synthèse envoie du texte à une IA externe. Deux invariants de sûreté doivent
être garantis **avant** d'écrire la moindre ligne d'appel API :

1. **On choisit précisément ce qu'on analyse** — pas un dossier entier, mais une
   **sélection** d'entretiens (le « périmètre » d'analyse).
2. **Aucun vrai nom ne sort** — ni dans le contenu, ni via les **noms de
   fichiers** (qui portent souvent de vrais noms).

## Composants

| Fichier | Rôle |
|---------|------|
| `manifeste.py` | Définit le périmètre : `creer` (interactif) / `init` (modèle) / `valider` un `synthese.manifeste.json` |
| `garde_fou.py` | **Filet anti-fuite** : assemble le payload et le confronte à la mémoire client (LOCALE) |
| `lancer.py` | Appel à l'**API Claude** (garde-fou en barrière) → `4_synthese/synthese.md` |
| `gabarits/` | Trames de synthèse (défaut : `diagnostic_transfo_ia.md`) |
| `manifeste.example.json` | Modèle de manifeste commenté |

Pilotage via la commande `ia` :

```powershell
ia synthese creer [perimetre]       # crée le manifeste INTERACTIVEMENT (scan + questions)
ia synthese init [perimetre]        # modèle non interactif (scan récursif)
ia synthese verifier [manifeste]    # garde-fou anti-fuite (avant tout envoi IA)
ia synthese lancer [manifeste]      # synthèse via l'API Claude (anonyme + repersonnalisée)
```

## 1. Le manifeste = le périmètre d'analyse

La synthèse ne porte **pas** sur un répertoire : tu **désignes** les entretiens
dans un manifeste JSON. Le plus simple est **`ia synthese creer`** : il scanne le
périmètre (récursif) et te pose les questions (titre, nom de sortie, et par
entretien : inclure / rôle / interviewé — en te listant les pseudonymes connus).
`ia synthese init` produit le même fichier en **modèle** non interactif, à éditer
à la main.

```json
{
  "version": 1,
  "titre": "Diagnostic transfo IA — vague 1",
  "sortie": "rapport_acme",
  "memoire": "memoire_client.json",
  "entretiens": [
    { "id": "E1", "source": "dupont/3_anonymisation/dupont_coupe_anonymise.txt",
      "inclure": true, "role": "Direction financiere", "interviewe": "PERSONNE_1" }
  ]
}
```

| Champ | Envoyé à l'IA ? | Rôle |
|-------|:--:|------|
| `id` | **oui** | Label **neutre** (E1, E2…) qui remplace le nom de fichier dans tout le payload |
| `source` | **non** | Chemin **local** du transcript anonymisé (souvent un vrai nom dans le nom de fichier) — relatif au manifeste |
| `inclure` | — | Sélectionne l'entretien sans le supprimer de la liste |
| `role` | oui | Descripteur **neutre** facultatif (⚠ garder générique : « DAF de Toulouse » ré-identifie) |
| `interviewe` | oui | Pseudonyme principal (relie l'entretien à la mémoire → attribution cohérente + repersonnalisable) |

- `sortie` = **nom de base** des fichiers produits par `lancer` (sans extension).
  Les sorties sont écrites **au niveau de la mission** (à côté du manifeste), sans
  sous-dossier : `<sortie>.md`, `<sortie>_REPERSONNALISE.md`, `<sortie>.run.json`.
  Surchargeable en ligne de commande par `-Out`.
- `memoire` pointe la `memoire_client.json` du périmètre (recherche ascendante à
  la création). **Jamais envoyée** — elle sert au garde-fou en local.
- Un entretien sans transcript anonymisé est listé avec `inclure: false` et une
  note (lance `ia anonymiser` puis renseigne `source`).

## 2. Le garde-fou anti-fuite

`ia synthese verifier` assemble le **payload exact** qui partirait (uniquement
`id` / `role` / `interviewe` / **contenu anonymisé** — aucun chemin, aucun nom de
fichier) et le confronte à la mémoire client :

- les `variantes` / `canonique` de la mémoire **sont** les vrais noms ;
  l'anonymiseur les a tous remplacés. Le garde-fou **rejoue son matcher** (mêmes
  frontières `\b`, insensible à la casse) sur le texte déjà anonymisé : **toute**
  correspondance résiduelle = un raté d'anonymisation → **envoi bloqué** (code 2) ;
- protège donc à la fois contre les **noms de fichiers** (structurellement exclus
  du payload) **et** contre les **ratés de contenu** (surnom, nom mal transcrit
  resté en clair).

```powershell
ia synthese verifier
ia synthese verifier -Dump payload.local.json   # écrit le payload (LOCAL) pour inspection
```

> ⚠️ Si la mémoire est vide/absente, le garde-fou ne peut **rien** garantir et le
> signale (à corriger avant d'aller plus loin).

## Lien avec le reste du pipeline

```
... ia anonymiser (par entretien)
        │   3_anonymisation/<nom>_coupe_anonymise.txt   (pseudonymes)
        ▼
ia synthese init  →  édition du manifeste  →  ia synthese verifier   ← garde-fou
        ▼
ia synthese lancer  →  API Claude →  <sortie>.md                 (anonyme)
                                  +  <sortie>_REPERSONNALISE.md   (livrable, LOCAL)
```

Toute la boucle reste **en interne**, plus de copier-coller manuel.

## 3. La synthèse (`ia synthese lancer`)

Appelle l'**API Claude** (`claude-opus-4-8` par défaut) sur le corpus vérifié,
puis produit **deux versions au niveau de la mission** (nom de base = champ
`sortie` du manifeste ou `-Out`) + un journal `<sortie>.run.json` (modèle,
entrées, tokens) :

- `<sortie>.md` — **anonyme** (pseudonymes), trace de ce qui a été envoyé ;
- `<sortie>_REPERSONNALISE.md` — **le livrable** (vrais noms réinjectés), produit
  **automatiquement** (la version anonyme n'a pas d'usage propre). ⚠️ contient les
  vrais noms : usage **local**, ne jamais l'envoyer à une IA.

Détails :

- **Le garde-fou est rejoué en barrière** : `lancer` refuse d'envoyer si un vrai
  nom subsiste (ou mémoire/sources manquantes) — impossible de le court-circuiter.
- **Gabarit** configurable (`-Gabarit`), défaut `gabarits/diagnostic_transfo_ia.md`.
- **`-Court`** réinjecte les prénoms (variante courte) plutôt que les noms complets.
- **`-DryRun`** assemble le prompt et l'écrit en local (`synthese.prompt.txt`)
  **sans** appeler l'API — pour inspecter ce qui partirait.

```powershell
ia synthese lancer -DryRun                 # prompt local, aucun envoi
ia synthese lancer                         # appel réel -> anonyme + repersonnalisée
ia synthese lancer -Modele claude-opus-4-8 -MaxTokens 16000
```

## Prérequis

- `anthropic` (dans `requirements.txt`, installé par le bootstrap) ;
- **`ANTHROPIC_API_KEY`** dans `config/.env` (obtenir sur
  https://console.anthropic.com/settings/keys).

Les étapes `init` / `verifier` n'ont aucun prérequis (stdlib uniquement).
