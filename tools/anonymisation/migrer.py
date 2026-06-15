#!/usr/bin/env python3
"""
migrer.py — Convertit l'ancien format (alias.yaml + table_correspondance.json)
vers le nouvel artefact unique `memoire_client.json` (refonte #14).

À lancer UNE FOIS par périmètre existant. Ne supprime rien : il lit l'ancien et
écrit le nouveau à côté. Tu peux ensuite archiver l'ancien alias.yaml.

Récupère notamment les `ignorer` / `locuteurs_generiques` de l'alias.yaml, qui
n'étaient PAS mémorisés d'une séance à l'autre dans l'ancien système.

100% local. Voir memoire.py (schéma) et SCHEMA.md.

Usage :
    python migrer.py --alias alias.yaml --table table_correspondance.json
    python migrer.py --alias alias.yaml                       # table absente
    python migrer.py --table table_correspondance.json        # alias absent
    python migrer.py --alias a.yaml --table t.json --out memoire_client.json
    python migrer.py --dir "D:\\Missions\\Acme"   # cherche alias+table dans ce dossier
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memoire as M  # noqa: E402


def die(msg, code=1):
    print(f"[ERREUR] {msg}", file=sys.stderr)
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser(
        description="Migration ancien format -> memoire_client.json.")
    ap.add_argument("--alias", help="Ancien alias.yaml.")
    ap.add_argument("--table", help="Ancien table_correspondance.json.")
    ap.add_argument("--dir", help="Dossier contenant alias.yaml et/ou table_correspondance.json.")
    ap.add_argument("--client", help="Nom du client (sinon repris de la table).")
    ap.add_argument("--out", help=f"Sortie (défaut: <dir>/{M.NOM_MEMOIRE}).")
    ap.add_argument("--force", action="store_true",
                    help="Écraser une mémoire existante.")
    args = ap.parse_args()

    alias_path = Path(args.alias) if args.alias else None
    table_path = Path(args.table) if args.table else None
    base_dir = Path(args.dir) if args.dir else None

    # Résolution via --dir si fourni.
    if base_dir:
        if not base_dir.is_dir():
            die(f"Dossier introuvable : {base_dir}")
        if not alias_path:
            cand = base_dir / "alias.yaml"
            alias_path = cand if cand.exists() else None
        if not table_path:
            cand = base_dir / "table_correspondance.json"
            table_path = cand if cand.exists() else None

    if not alias_path and not table_path:
        die("Rien à migrer : fournis --alias et/ou --table (ou --dir les contenant).")

    if alias_path and not alias_path.exists():
        die(f"alias introuvable : {alias_path}")
    if table_path and not table_path.exists():
        die(f"table introuvable : {table_path}")

    # Destination : à côté de l'alias, sinon de la table, sinon --dir.
    if args.out:
        out = Path(args.out)
    else:
        anchor = (alias_path or table_path).parent if (alias_path or table_path) else base_dir
        out = anchor / M.NOM_MEMOIRE

    if out.exists() and not args.force:
        die(f"{out} existe déjà. Relance avec --force pour écraser.")

    mem = M.migrer_depuis_ancien(alias_path, table_path, client=args.client)
    M.ecrire_memoire(out, mem)

    n_ent = len(mem["entrees"])
    n_ign = len(mem["ignorer"])
    n_gen = len(mem["locuteurs_generiques"])
    print(f"[OK] Mémoire client écrite : {out}")
    print(f"     {n_ent} entrée(s), {n_ign} faux positif(s) mémorisé(s), "
          f"{n_gen} locuteur(s) générique(s).")
    if alias_path and (n_ign or n_gen):
        print("     -> Les 'ignorer'/'locuteurs_generiques' de l'alias sont "
              "désormais réutilisables d'une séance à l'autre (gain de la refonte).")
    print("\nÉtape suivante : tu peux archiver l'ancien alias.yaml. Le pipeline "
          f"utilise maintenant {M.NOM_MEMOIRE}.")


if __name__ == "__main__":
    main()
