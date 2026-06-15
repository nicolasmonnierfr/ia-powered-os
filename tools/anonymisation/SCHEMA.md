# Schéma des données — Anonymisation (v2, refonte #14)

Ce document fige le format des fichiers échangés par le pipeline. Il sert de
contrat entre les briques (détection, réconciliation CLI/HTML, application,
dé-anonymisation).

**Refonte #14 (15/06/2026)** : l'ancien couple `alias.yaml` (entrée) +
`table_correspondance.json` (sortie) est remplacé par un **artefact unique par
client**, `memoire_client.json`, plus un petit `ignorer_global.json` partagé.
La logique de lecture/écriture est centralisée dans `memoire.py`.

---

## 1. `memoire_client.json` (ARTEFACT UNIQUE — entrée ET sortie ET mémoire)

Un seul fichier par client (= « périmètre »), trouvé par recherche ascendante
depuis l'entretien. Il porte **tout** : pseudos, canoniques, variantes, types,
faux positifs propres au client, locuteurs génériques, réglages.

- **Produit / mis à jour** par l'éditeur HTML, `reconcilier.py`, `appliquer.py`.
- **Lu** par `detecter.py` (réutilisation des pseudos + faux positifs),
  `appliquer.py` (remplacement), `desanonymiser.py` (retour).
- **Gardé en local** : contient les vrais noms — **ne jamais l'envoyer**.
- **Éditable à la main** marginalement (JSON indenté, ordre de clés stable).

```json
{
  "version": 2,
  "client": "Acme",
  "compteurs": { "PERSONNE": 3, "ORG": 1, "PRODUIT": 1 },
  "entrees": [
    {
      "pseudo": "PERSONNE_1",
      "type": "PERSONNE",
      "canonique": "Jean Dupont",
      "variantes": ["Jean Dupont", "Jean", "M. Dupont"],
      "source": "ner"
    },
    {
      "pseudo": "CONSULTANT_1",
      "type": "PERSONNE",
      "canonique": "Marie Lefèvre",
      "variantes": ["Marie Lefèvre", "Marie"],
      "source": "alias"
    }
  ],
  "ignorer": ["Ancienneté", "Synergie"],
  "locuteurs_generiques": ["Interviewer", "Candidat"],
  "reglages": { "seuil_score": 0.5,
                "types": ["PERSON","LOCATION","ORGANIZATION","EMAIL_ADDRESS","PHONE_NUMBER"] }
}
```

### Champs d'une entrée

| Champ | Rôle |
|-------|------|
| `pseudo` | Pseudonyme, **unique** dans la mémoire. Peut être numéroté (`PERSONNE_1`) **ou parlant** (`SOCIETE`, `CONSULTANT_1`) — aucune contrainte de suffixe (corrige #8). |
| `type` | `PERSONNE` \| `LIEU` \| `ORG` \| `PRODUIT` \| `EMAIL` \| `TEL`. **Champ explicite** : il n'est plus déduit du préfixe du pseudo (corrige #13). |
| `canonique` | Forme de référence (la plus complète). Cible par défaut de la dé-anonymisation (#12). |
| `variantes` | **Toutes** les chaînes du texte à remplacer par ce pseudo. Mécanisme de regroupement (Thomas + Tom → un pseudo). Remplacement par longueur décroissante. |
| `source` | `ner` (auto) \| `alias` (forcé, priorité absolue sur le NER) \| `manuel` \| `etiquette`. Traçabilité. |

### Champs de premier niveau

| Champ | Rôle |
|-------|------|
| `version` | 2 (format unique). |
| `client` | Nom du client (libre). |
| `compteurs` | Plus grand numéro utilisé par type — garantit l'absence de collision à l'enrichissement. (Re)calculé à l'écriture. |
| `entrees` | Liste des entités connues (voir ci-dessus). |
| `ignorer` | Faux positifs **propres au client** (insensible à la casse). Mémorisés d'une séance à l'autre (gain #14.3). |
| `locuteurs_generiques` | Étiquettes `[Rôle]` génériques conservées telles quelles. |
| `reglages` | `seuil_score` (float 0..1) et `types` (entités Presidio détectées). |

### Règles

- Remplacement à l'aller : variantes **les plus longues d'abord** (« Jean Dupont »
  avant « Jean »), insensible à la casse, en `\b` mots entiers si alphanumérique.
- Retour (dé-anonymisation, #12) : remplacement **pseudo → canonique**, pseudos
  **les plus longs d'abord** (`PERSONNE_10` avant `PERSONNE_1`).
- Mapping type interne ↔ Presidio :
  `PERSONNE`=PERSON, `LIEU`=LOCATION, `ORG`=ORGANIZATION,
  `EMAIL`=EMAIL_ADDRESS, `TEL`=PHONE_NUMBER, `PRODUIT`=(alias only).

---

## 2. `ignorer_global.json` (faux positifs UNIVERSELS — partagé tous clients)

Un seul fichier (dans `config/`), chargé **en plus** des `ignorer` du client.
Pour les politesses et titres valables partout (« Bonjour », « Madame »…).

```json
{ "version": 1, "ignorer": ["Bonjour", "Merci", "Madame", "Monsieur"] }
```

---

## 3. État intermédiaire `<nom>.etat.json` (détection → validation)

Produit par `detecter.py`, consommé par la réconciliation (CLI/HTML). Format de
travail, non conservé.

```json
{
  "transcript": "fichier.srt",
  "memoire_source": "memoire_client.json",
  "candidats": [
    { "texte": "Thomas", "type": "PERSONNE", "occurrences": 12, "score": 0.85,
      "pseudo_propose": "PERSONNE_2", "source": "ner", "exemples": ["...Thomas s'occupe..."] }
  ]
}
```

---

## 4. Migration depuis l'ancien format

`migrer.py` convertit `alias.yaml` (+ `table_correspondance.json` éventuelle) en
`memoire_client.json`. Il **récupère les `ignorer`/`locuteurs_generiques`** de
l'alias, qui n'étaient pas mémorisés auparavant. Les outils Python lisent aussi
l'ancien format à la volée via `--alias`/`--table` (rétrocompatibilité), sans
réécriture.

> ⚠️ Limite migration : un ancien `alias.yaml` ne porte pas le `type`. Les
> pseudos parlants (`SOCIETE`, `CONSULTANT_1`) seront typés `PRODUIT` par défaut
> ; corrige le type dans l'éditeur après migration (le remplacement, lui, reste
> correct quel que soit le type).
