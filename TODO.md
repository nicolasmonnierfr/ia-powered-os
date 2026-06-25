# TODO — IA-Powered-OS

Tâches ponctuelles **à faire plus tard**. Les évolutions structurées (avec
numéro stable) vivent dans [`BACKLOG.md`](BACKLOG.md) ; ce qui est réalisé est
décrit dans [`CHANGELOG.md`](CHANGELOG.md).

- [ ] **Tester le workflow de synthèse de bout en bout sur un vrai ensemble.**
  Cible : **Clikit** (`D:\Nicolas\Documents\Missions IA\Clikit\Sources\Interviews`),
  dont toutes les transcriptions sont déjà anonymisées. Dérouler :
  `ia synthese creer` → `ia synthese verifier` → `ia synthese lancer`, puis
  relire le livrable `*_REPERSONNALISE.md`.
  - Vérifier à l'étape `creer` que **tous les entretiens pointés ont bien un
    transcript anonymisé** (couverture « M détectés sur N » : M doit = N).
  - Confirmer que `verifier` finit en `[OK] … SUR a envoyer` (sinon corriger le
    fichier `_anonymise.txt` signalé), puis que `lancer` produit les deux versions
    (anonyme + repersonnalisée) au niveau mission.
