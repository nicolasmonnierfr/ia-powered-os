# SCHÉMA — `entretien.json` (fichier projet par entretien)

Petit fichier d'état placé **à la racine du dossier d'entretien**. Il sert de
**mémoire de progression** : quelles étapes ont été faites, quand, avec quel
résultat, et où trouver le log détaillé correspondant.

- **Résumé** (horodatage des étapes) : ici, lu souvent, compact.
- **Log verbeux** (détail technique) : centralisé dans `IAPOS/logs/`, lu
  rarement (débogage). `entretien.json` ne stocke que le **chemin** vers lui.

Créé / mis à jour automatiquement par les wrappers (`ia transcrire`, `ia taguer`,
`ia couper`, `ia anonymiser …`). Lisible par `ia etat`.

---

## Structure

```json
{
  "version": 1,
  "entretien": "entretien_dupont",
  "audio": "entretien_dupont.m4a",
  "cree_le": "2026-06-16T22:14:03+02:00",
  "maj_le": "2026-06-17T01:42:19+02:00",
  "etapes": {
    "transcription": {
      "statut": "fait",
      "debut": "2026-06-16T22:14:05+02:00",
      "fin":   "2026-06-17T01:05:40+02:00",
      "duree_sec": 10235,
      "log": "logs/20260616-221405-entretien_dupont-transcription.log",
      "details": { "diarisation": true, "modele": "large-v3" },
      "message": null
    },
    "coupe":         { "statut": "a_faire" },
    "anonymisation": { "statut": "a_faire" }
  }
}
```

## Champs

| Champ | Type | Sens |
|-------|------|------|
| `version` | int | Version du schéma (1). |
| `entretien` | string | Nom du dossier d'entretien. |
| `audio` | string\|null | Nom du fichier audio source détecté. |
| `cree_le` / `maj_le` | ISO 8601 | Horodatage de création / dernière mise à jour. |
| `etapes` | objet | Une entrée par étape : `transcription`, `coupe`, `anonymisation`. |

### Chaque étape

| Champ | Type | Sens |
|-------|------|------|
| `statut` | string | `a_faire` \| `en_cours` \| `fait` \| `echec`. |
| `debut` / `fin` | ISO 8601\|null | Début / fin de la dernière exécution. |
| `duree_sec` | int\|null | Durée de la dernière exécution. |
| `log` | string\|null | Chemin (relatif au repo) du log verbeux centralisé. |
| `details` | objet | Infos spécifiques à l'étape (modèle, options…). |
| `message` | string\|null | Message d'erreur si `statut = echec`, sinon `null`. |

> **Anonymisation** : comporte deux sous-actions (`detecter`, `appliquer`).
> Le statut reflète la dernière action ; `details.sous_etape` indique laquelle.

## Statuts — cycle de vie

```
a_faire ──(lancement)──> en_cours ──(succès)──> fait
                              │
                              └────(erreur)────> echec
```

Au prochain lancement d'une étape en `echec` ou `fait`, elle repasse
`en_cours` (on réexécute proprement).

## Notes

- **Écriture** : lecture → modification → réécriture complète (pas de verrou).
  ⚠️ Limite connue : deux étapes simultanées sur le même entretien pourraient
  se télescoper. L'usage est séquentiel, donc sans risque en pratique.
- **Robustesse** : si `entretien.json` est absent ou illisible, les wrappers le
  (re)créent ; l'absence du fichier ne bloque jamais un traitement.
- Le fichier est **informatif** : le supprimer ne casse rien, il sera recréé
  (mais l'historique des horodatages est perdu).
```
