# Schéma des données — Anonymisation

Ce document fige le format des fichiers échangés par le pipeline. Il sert de
contrat entre les briques (détection, réconciliation CLI/HTML, application).

---

## 1. `alias.yaml` (ENTRÉE, rempli à la main)

Voir `alias.example.yaml` pour un modèle commenté. Structure :

| Clé | Type | Rôle |
|-----|------|------|
| `forcer` | dict `{pseudo: [variantes]}` | Termes forcés, priorité absolue sur le NER. Regroupe les variantes d'une même entité (ex. Thomas/Tom). |
| `ignorer` | liste de chaînes | Termes à ne jamais anonymiser (faux positifs). Insensible à la casse. |
| `locuteurs_generiques` | liste de chaînes | Étiquettes `[Locuteur]` génériques conservées telles quelles. |
| `reglages.seuil_score` | float 0..1 | Score minimal pour retenir une détection auto. |
| `reglages.types` | liste | Types d'entités détectés automatiquement. |

---

## 2. `table_correspondance.json` (SORTIE + MÉMOIRE réutilisable)

C'est le pivot du système. Elle est :
- **produite** par un traitement,
- **gardée en local** (clé de ré-identification — ne jamais l'envoyer),
- **rechargée en entrée** au traitement suivant du même client, pour réutiliser
  les pseudonymes déjà attribués et ne questionner que les entités nouvelles.

```json
{
  "version": 1,
  "client": "Acme",
  "compteurs": { "PERSONNE": 2, "LIEU": 1, "ORG": 1, "PRODUIT": 1, "EMAIL": 1, "TEL": 1 },
  "entrees": [
    {
      "pseudo": "PERSONNE_1",
      "type": "PERSONNE",
      "canonique": "Jean Dupont",
      "variantes": ["Jean Dupont", "Jean", "M. Dupont"],
      "source": "ner"
    },
    {
      "pseudo": "PRODUIT_1",
      "type": "PRODUIT",
      "canonique": "Projet Hélios",
      "variantes": ["Projet Hélios", "Hélios"],
      "source": "alias"
    }
  ]
}
```

### Champs d'une entrée

| Champ | Rôle |
|-------|------|
| `pseudo` | Le pseudonyme typé (`PERSONNE_1`…). Unique dans la table. |
| `type` | `PERSONNE` \| `LIEU` \| `ORG` \| `PRODUIT` \| `EMAIL` \| `TEL`. |
| `canonique` | La forme « de référence » de l'entité (la plus complète). |
| `variantes` | **Toutes** les chaînes du texte qui doivent devenir ce pseudo. Mécanisme de regroupement (Thomas + Tom → un seul pseudo). Le remplacement se fait sur ces chaînes. |
| `source` | `alias` (forcé) \| `ner` (auto) \| `manuel` (ajouté en réconciliation). Traçabilité pour la relecture. |

### Règles

- Le remplacement applique les `variantes` les plus **longues d'abord** (éviter
  que « Jean » remplace avant « Jean Dupont »).
- `compteurs` donne le prochain numéro libre par type (pas de collision à
  l'enrichissement).
- Mapping type interne ↔ type Presidio :
  `PERSONNE`=PERSON, `LIEU`=LOCATION, `ORG`=ORGANIZATION,
  `EMAIL`=EMAIL_ADDRESS, `TEL`=PHONE_NUMBER, `PRODUIT`=(alias only).

---

## 3. État intermédiaire (entre détection et application)

Produit par l'étape de détection, consommé par la réconciliation (CLI/HTML).
Format de travail, non destiné à être conservé :

```json
{
  "transcript": "fichier.srt",
  "candidats": [
    { "texte": "Thomas", "type": "PERSONNE", "occurrences": 12, "score": 0.85,
      "pseudo_propose": "PERSONNE_2", "source": "ner", "exemples": ["...Thomas s'occupe..."] }
  ],
  "ambiguites": [
    { "a": "Thomas", "b": "Tom", "raison": "proximité", "meme_entite": null }
  ]
}
```
