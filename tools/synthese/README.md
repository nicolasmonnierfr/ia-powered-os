# Outil : Synthèse multi-entretiens

Produit, à partir de **plusieurs entretiens anonymisés** d'une mission, une
**synthèse croisée** (thèmes, douleurs, attentes, divergences…) destinée à être
analysée par l'**API Claude**, puis re-personnalisée pour le client via l'outil
existant (`ia repersonnaliser`).

> **État : en cours.** Cet outil se construit par incréments. Le premier
> incrément, **livré ici**, pose les fondations *sans appel IA* : la **définition
> du périmètre** (manifeste) et le **garde-fou anti-fuite**. L'appel à l'API
> (`ia synthese lancer`) viendra ensuite.

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
| `manifeste.py` | Définit le périmètre : `init` (pré-génère) + `valider` un `synthese.manifeste.json` |
| `garde_fou.py` | **Filet anti-fuite** : assemble le payload et le confronte à la mémoire client (LOCALE) |
| `manifeste.example.json` | Modèle de manifeste commenté |

Pilotage via la commande `ia` :

```powershell
ia synthese init [perimetre]        # pré-génère synthese.manifeste.json (scan récursif)
ia synthese verifier [manifeste]    # garde-fou anti-fuite (avant tout envoi IA)
```

## 1. Le manifeste = le périmètre d'analyse

La synthèse ne porte **pas** sur un répertoire : tu **désignes** les entretiens
dans un manifeste JSON. `ia synthese init` le pré-remplit en scannant le
périmètre (récursif, même moteur que l'orchestrateur), puis **tu l'édites**.

```json
{
  "version": 1,
  "titre": "Diagnostic transfo IA — vague 1",
  "memoire": "../memoire_client.json",
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

- `memoire` pointe la `memoire_client.json` du périmètre (recherche ascendante à
  l'`init`). **Jamais envoyée** — elle sert au garde-fou en local.
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
[à venir] ia synthese lancer  →  4_synthese/synthese.md   (en pseudonymes, via API Claude)
        ▼
ia repersonnaliser  →  livrable client (vrais noms, LOCAL)
```

La synthèse sortira **en pseudonymes** : `ia repersonnaliser` la transforme en
livrable client — toute la boucle reste en interne, plus de copier-coller manuel.

## Prérequis

Aucun nouveau pour cet incrément (stdlib Python uniquement). L'appel API à venir
utilisera une clé Anthropic dans `config/.env`.
