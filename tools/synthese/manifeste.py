#!/usr/bin/env python3
"""
manifeste.py — Definition du PERIMETRE d'une synthese multi-entretiens.

La synthese ne porte PAS sur un repertoire entier mais sur une SELECTION
explicite d'entretiens, decrite dans un manifeste JSON (`synthese.manifeste.json`).
Ce module sait :
  - `init`    : pre-generer un manifeste en scannant un perimetre (recursif,
                reutilise le moteur d'etat de l'orchestrateur) ;
  - `valider` : charger + verifier un manifeste (sources lisibles, memoire la).

CONFIDENTIALITE (cf. garde_fou.py) : le manifeste contient des chemins LOCAUX
(les noms de fichiers portent souvent de vrais noms) qui ne sont JAMAIS envoyes.
Seuls partent vers l'IA : `id` (label neutre), `role`, `interviewe` (pseudonyme)
et le CONTENU anonymise des entretiens.

100% local, stdlib uniquement.

Usage :
    python manifeste.py init <perimetre> [--out synthese.manifeste.json]
    python manifeste.py valider <manifeste>
"""

import argparse
import json
import os
import sys
from pathlib import Path

_ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(_ICI.parent / "orchestrateur"))
sys.path.insert(0, str(_ICI.parent / "anonymisation"))
import etat as ETAT      # noqa: E402  (collecter_entretiens, trouver_ascendant)
import memoire as MEM    # noqa: E402  (NOM_MEMOIRE)

NOM_MANIFESTE = "synthese.manifeste.json"


def _relpath(cible: Path, base: Path) -> str:
    """Chemin de `cible` relatif a `base`, en slashs (portable, lisible)."""
    return os.path.relpath(str(cible), str(base)).replace("\\", "/")


def trouver_anonymise(entretien: Path):
    """Retourne le .txt anonymise le plus pertinent d'un entretien, ou None.

    Priorite a 3_anonymisation/*_anonymise.txt (lisible, regroupe par locuteur) ;
    on prefere la version issue de la coupe (`_coupe`) si elle existe.
    """
    d = entretien / "3_anonymisation"
    if not d.is_dir():
        return None
    cands = sorted(d.glob("*_anonymise.txt"))
    if not cands:
        return None
    coupe = [p for p in cands if "_coupe" in p.name]
    return (coupe or cands)[0]


def generer(perimetre: Path, base: Path) -> dict:
    """Construit un manifeste-modele pour `perimetre`. Les chemins sont relatifs
    a `base` (le dossier ou le manifeste sera ecrit)."""
    perimetre = perimetre.resolve()
    memoire = ETAT.trouver_ascendant(perimetre, MEM.NOM_MEMOIRE)
    entretiens = []
    for i, ent in enumerate(ETAT.collecter_entretiens(perimetre), start=1):
        anon = trouver_anonymise(ent)
        item = {
            "id": f"E{i}",
            "source": (_relpath(anon, base) if anon else ""),
            "inclure": anon is not None,
            "role": "",
            "interviewe": "",
        }
        if anon is None:
            item["_note"] = ("pas de transcript anonymise — lancer 'ia anonymiser' "
                             "sur cet entretien, puis renseigner 'source'.")
        entretiens.append(item)
    return {
        "version": 1,
        "titre": perimetre.name,
        "sortie": "synthese",   # nom de base des fichiers de sortie (editable)
        "memoire": (_relpath(Path(memoire), base) if memoire else MEM.NOM_MEMOIRE),
        "entretiens": entretiens,
    }


def charger(manifeste_path: Path) -> dict:
    """Charge un manifeste JSON. Leve ValueError si illisible/invalide."""
    data = json.loads(Path(manifeste_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("entretiens"), list):
        raise ValueError("manifeste invalide : objet attendu avec une liste 'entretiens'.")
    return data


def resoudre_source(manifeste_path: Path, source: str) -> Path:
    """Chemin absolu d'une source, relatif au dossier du manifeste."""
    return (Path(manifeste_path).parent / source).resolve()


def resoudre_memoire(manifeste_path: Path, data: dict) -> Path:
    return (Path(manifeste_path).parent / data.get("memoire", MEM.NOM_MEMOIRE)).resolve()


def valider(manifeste_path: Path) -> dict:
    """Verifie qu'un manifeste est exploitable. Retourne un rapport
    { ok, inclus, total, memoire_ok, problemes:[...] }."""
    data = charger(manifeste_path)
    problemes = []
    inclus = [e for e in data["entretiens"] if e.get("inclure", True)]

    mem_path = resoudre_memoire(manifeste_path, data)
    memoire_ok = mem_path.is_file()
    if not memoire_ok:
        problemes.append(f"memoire introuvable : {mem_path}")

    for e in inclus:
        eid = e.get("id", "?")
        src = e.get("source", "")
        if not src:
            problemes.append(f"{eid} : 'source' vide (entretien inclus mais sans transcript).")
            continue
        sp = resoudre_source(manifeste_path, src)
        if not sp.is_file():
            problemes.append(f"{eid} : source introuvable : {sp}")
        elif "anonymise" not in sp.name.lower():
            problemes.append(f"{eid} : la source ne semble PAS anonymisee "
                             f"(nom sans 'anonymise') : {sp.name} — risque de fuite.")
    if not inclus:
        problemes.append("aucun entretien inclus (inclure=true).")

    return {
        "ok": not problemes,
        "inclus": len(inclus),
        "total": len(data["entretiens"]),
        "memoire": str(mem_path),
        "memoire_ok": memoire_ok,
        "problemes": problemes,
    }


def _personnes_memoire(memoire_path: Path):
    """(pseudo, canonique) des entrees PERSONNE de la memoire — pour aider au
    choix de l'interviewe. Affichage LOCAL uniquement (jamais envoye)."""
    if not memoire_path or not Path(memoire_path).is_file():
        return []
    mem = MEM.charger_memoire(Path(memoire_path))
    out = []
    for e in mem.get("entrees", []):
        if e.get("type") == "PERSONNE":
            out.append((e.get("pseudo", ""), e.get("canonique") or ""))
    return out


def creer(perimetre: Path, out_path: Path):
    """Construit INTERACTIVEMENT un manifeste : scan du perimetre puis questions
    (titre, nom de sortie, et par entretien : inclure / role / interviewe).
    Lit les reponses sur l'entree standard (input())."""
    perimetre = Path(perimetre).resolve()
    base = out_path.parent
    modele = generer(perimetre, base)
    memoire_abs = (base / modele["memoire"]).resolve()
    personnes = _personnes_memoire(memoire_abs)

    print("\n=== Creation d'une configuration de synthese ===")
    print(f"Perimetre : {perimetre}")
    print(f"Memoire   : {modele['memoire']}  ({'OK' if memoire_abs.is_file() else 'ABSENTE'})")
    nb = len(modele["entretiens"])
    prets = sum(1 for e in modele["entretiens"] if e.get("inclure"))
    print(f"Entretiens detectes : {nb}  (dont {prets} avec transcript anonymise)\n")

    titre = input(f"Titre [{modele['titre']}] : ").strip() or modele["titre"]
    sortie = input("Nom de base des fichiers de sortie [synthese] : ").strip() or "synthese"

    if personnes:
        print("\nInterlocuteurs connus (pseudonyme = vrai nom, LOCAL) :")
        for ps, cano in personnes:
            print(f"  {ps}{(' = ' + cano) if cano else ''}")

    entretiens = []
    for e in modele["entretiens"]:
        eid = e["id"]
        src = e.get("source", "")
        print(f"\n--- {eid} : {src or '(pas de transcript anonymise)'}")
        if not src:
            print("    Non anonymise -> exclu (lance 'ia anonymiser' sur cet entretien puis relance).")
            e["inclure"] = False
            entretiens.append(e)
            continue
        rep = input("    Inclure dans la synthese ? [O/n] : ").strip().lower()
        e["inclure"] = not rep.startswith("n")
        if e["inclure"]:
            e["role"] = input("    Role (generique, facultatif) : ").strip()
            e["interviewe"] = input("    Interviewe (pseudonyme, facultatif) : ").strip()
        entretiens.append(e)

    data = {
        "version": 1,
        "titre": titre,
        "sortie": sortie,
        "memoire": modele["memoire"],
        "entretiens": entretiens,
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    inclus = sum(1 for e in entretiens if e.get("inclure"))
    print(f"\n[OK] Manifeste ecrit : {out_path}")
    print(f"     {inclus} entretien(s) inclus sur {nb}.")
    print("     Suite : ia synthese verifier   puis   ia synthese lancer")


# ---------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Manifeste de synthese multi-entretiens.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Pre-genere un manifeste depuis un perimetre.")
    p_init.add_argument("perimetre", help="Dossier contenant les entretiens (scan recursif).")
    p_init.add_argument("--out", help=f"Fichier de sortie (defaut : <perimetre>/{NOM_MANIFESTE}).")

    p_creer = sub.add_parser("creer", help="Cree INTERACTIVEMENT un manifeste (scan + questions).")
    p_creer.add_argument("perimetre", nargs="?", default=".", help="Dossier des entretiens (defaut: .).")
    p_creer.add_argument("--out", help=f"Fichier de sortie (defaut: <perimetre>/{NOM_MANIFESTE}).")

    p_val = sub.add_parser("valider", help="Verifie un manifeste (sources + memoire).")
    p_val.add_argument("manifeste", help=f"Chemin du {NOM_MANIFESTE}.")

    args = ap.parse_args()

    if args.cmd == "init":
        perimetre = Path(args.perimetre).resolve()
        if not perimetre.is_dir():
            print(f"[ERREUR] Perimetre introuvable : {perimetre}", file=sys.stderr)
            sys.exit(1)
        out = Path(args.out).resolve() if args.out else (perimetre / NOM_MANIFESTE)
        base = out.parent
        data = generer(perimetre, base)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        inclus = sum(1 for e in data["entretiens"] if e.get("inclure"))
        print(f"[OK] Manifeste ecrit : {out}")
        print(f"     {inclus}/{len(data['entretiens'])} entretien(s) avec transcript anonymise.")
        print(f"     Memoire : {data['memoire']}")
        print("     Edite-le : selectionne (inclure), renseigne role/interviewe, puis 'ia synthese verifier'.")
        return

    if args.cmd == "creer":
        perim = Path(args.perimetre).resolve()
        if not perim.is_dir():
            print(f"[ERREUR] Perimetre introuvable : {perim}", file=sys.stderr)
            sys.exit(1)
        out = Path(args.out).resolve() if args.out else (perim / NOM_MANIFESTE)
        if out.exists():
            rep = input(f"{out.name} existe deja. Ecraser ? [o/N] : ").strip().lower()
            if not rep.startswith("o"):
                print("Annule.")
                return
        creer(perim, out)
        return

    if args.cmd == "valider":
        mp = Path(args.manifeste).resolve()
        if not mp.is_file():
            print(f"[ERREUR] Manifeste introuvable : {mp}", file=sys.stderr)
            sys.exit(1)
        try:
            rap = valider(mp)
        except ValueError as ex:
            print(f"[ERREUR] {ex}", file=sys.stderr)
            sys.exit(1)
        print(f"Entretiens inclus : {rap['inclus']}/{rap['total']}")
        print(f"Memoire           : {rap['memoire']}  ({'OK' if rap['memoire_ok'] else 'ABSENTE'})")
        if rap["problemes"]:
            print("\nProblemes :")
            for p in rap["problemes"]:
                print(f"  - {p}")
            sys.exit(2)
        print("\n[OK] Manifeste valide.")


if __name__ == "__main__":
    main()
