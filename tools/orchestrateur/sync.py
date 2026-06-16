#!/usr/bin/env python3
"""
sync.py — Reconcilie les `entretien.json` avec la realite du disque.

La memoire « par projet » (entretien.json, #15) n'est ecrite que par les
wrappers QUAND ils executent une etape. Resultat : un entretien dont une etape a
ete faite « avant » (autre version, traitement manuel, dossier migre) peut
afficher `a_faire` alors que le livrable existe. `ia etat` ment alors sur
l'avancement reel.

Ce script aligne `entretien.json` sur ce que le SYSTEME DE FICHIERS prouve, en
reutilisant le moteur d'etat (`etat.py`). Regle de sûrete : **UPGRADE
UNIQUEMENT** — une etape confirmee par le disque passe a `fait` si elle n'y
etait pas deja ; on ne retrograde JAMAIS un statut, on n'ecrase pas les
horodatages/logs deja presents (un run reel reste prioritaire). Idempotent.

Usage :
    python sync.py <perimetre>     # synchronise tous les entretiens du perimetre
    python sync.py <entretien> --un  # un seul dossier d'entretien

100% local, stdlib uniquement.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import etat as E  # noqa: E402

# Correspondance etape entretien.json -> champ FS calcule par etat.py.
# Une etape est « confirmee faite » par le disque quand son champ vaut "fait".
ETAPES = ("transcription", "coupe", "anonymisation")


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _squelette(dossier: Path, audio):
    mk = lambda: {"statut": "a_faire", "debut": None, "fin": None,
                  "duree_sec": None, "log": None, "details": {}, "message": None}
    return {
        "version": 1,
        "entretien": dossier.name,
        "audio": audio,
        "cree_le": _now(),
        "maj_le": _now(),
        "etapes": {e: mk() for e in ETAPES},
    }


def sync_un(dossier: Path) -> bool:
    """Synchronise un dossier d'entretien. Retourne True si modifie."""
    fs = E.etat_entretien(dossier)              # verite disque
    pj_path = dossier / "entretien.json"
    projet = E.charger_json(pj_path)
    cree = projet is None or not isinstance(projet, dict)
    if cree:
        projet = _squelette(dossier, fs.get("audio"))

    etapes = projet.setdefault("etapes", {})
    change = cree
    for nom in ETAPES:
        if fs.get(nom) != "fait":
            continue                            # le disque ne confirme pas -> on ne touche pas
        e = etapes.get(nom)
        if not isinstance(e, dict):
            e = {"statut": "a_faire", "debut": None, "fin": None,
                 "duree_sec": None, "log": None, "details": {}, "message": None}
            etapes[nom] = e
        if e.get("statut") == "fait":
            continue                            # deja a jour (horodatages preserves)
        # UPGRADE -> fait, sans inventer d'horodatage ; on marque l'origine.
        e["statut"] = "fait"
        e["message"] = None
        det = e.get("details")
        if not isinstance(det, dict):
            det = {}
        det["sync"] = True
        e["details"] = det
        change = True

    if change:
        projet["maj_le"] = _now()
        try:
            pj_path.write_text(json.dumps(projet, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        except OSError as e:
            print(f"[AVERT] Ecriture {pj_path} impossible : {e}", file=sys.stderr)
            return False
    return change


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Synchronise entretien.json avec le disque (upgrade-only).")
    ap.add_argument("cible", help="Perimetre (defaut) ou dossier d'entretien (--un).")
    ap.add_argument("--un", action="store_true", help="Traiter `cible` comme UN dossier d'entretien.")
    args = ap.parse_args()

    cible = Path(args.cible).resolve()
    if not cible.is_dir():
        print(f"[ERREUR] Dossier introuvable : {cible}", file=sys.stderr)
        sys.exit(1)

    if args.un:
        dossiers = [cible]
    else:
        dossiers = [p for p in sorted(cible.iterdir())
                    if p.is_dir() and E.trouver_audio(p) is not None]

    n = 0
    for d in dossiers:
        if sync_un(d):
            n += 1
            print(f"[sync] {d.name} : entretien.json mis a jour")
    print(f"[sync] {n} entretien(s) synchronise(s) sur {len(dossiers)}.")


if __name__ == "__main__":
    main()
