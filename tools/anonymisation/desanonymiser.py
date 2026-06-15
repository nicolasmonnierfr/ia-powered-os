#!/usr/bin/env python3
"""
desanonymiser.py — REPERSONNALISATION (chemin inverse de l'anonymisation, #12).

Les rapports d'analyse produits à partir d'un transcript anonymisé contiennent
les pseudos (PERSONNE_1, SOCIETE_1…). Pour les livrer au dirigeant, ce script
réinjecte les vrais noms à partir de la mémoire client (`memoire_client.json`).

Le retour est NON AMBIGU : chaque pseudo est unique -> un seul remplacement
possible (contrairement à l'aller, où plusieurs variantes -> un pseudo).

⚠️ SÉCURITÉ : le fichier produit CONTIENT À NOUVEAU LES VRAIS NOMS. Il ne doit
JAMAIS être renvoyé à une IA externe. La sortie est nommée «_REPERSONNALISE».

Cible du remplacement : par défaut le `canonique` (forme la plus complète).
Option --court pour viser la variante la plus courte.

Formats : .txt / .md / .srt traités nativement. .docx via le skill docx
(python-docx) si disponible.

100% local. Voir memoire.py (schéma) et BACKLOG.md #12.

Usage :
    python desanonymiser.py rapport.md --memoire memoire_client.json
    python desanonymiser.py rapport.txt --memoire m.json --court
    python desanonymiser.py rapport.docx --memoire m.json
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memoire as M  # noqa: E402


def die(msg, code=1):
    print(f"[ERREUR] {msg}", file=sys.stderr)
    sys.exit(code)


def construire_mapping(mem, court=False):
    """Liste (pseudo, remplacement), pseudos longs d'abord (PERSONNE_10 avant _1)."""
    out = []
    for e in mem.get("entrees", []):
        if court and e.get("variantes"):
            repl = min(e["variantes"], key=len)
        else:
            repl = e.get("canonique") or (e["variantes"][0] if e.get("variantes") else e["pseudo"])
        out.append((e["pseudo"], repl))
    out.sort(key=lambda t: -len(t[0]))
    return out


def make_replacer(mapping):
    compiled = []
    for pseudo, repl in mapping:
        # mot entier : le pseudo est alphanumérique + underscore
        pat = re.compile(r"\b" + re.escape(pseudo) + r"\b")
        compiled.append((pat, repl))
    counts = {}

    def replace_in(text):
        for pat, repl in compiled:
            def _sub(m, _r=repl, _p=pat.pattern):
                counts[_p] = counts.get(_p, 0) + 1
                return _r
            text = pat.sub(_sub, text)
        return text
    return replace_in, counts


# ---------------------------------------------------------------------------
# Traitement par format
# ---------------------------------------------------------------------------
def traiter_texte(path, replace_in):
    raw = path.read_text(encoding="utf-8")
    return replace_in(raw)


def traiter_docx(path, out_path, replace_in):
    """Remplace dans un .docx en préservant la mise en forme (run par run)."""
    try:
        from docx import Document
    except ImportError:
        die("python-docx requis pour les .docx (voir skill docx / bootstrap).")
    doc = Document(str(path))

    def process_paragraph(p):
        for run in p.runs:
            if run.text:
                run.text = replace_in(run.text)

    for p in doc.paragraphs:
        process_paragraph(p)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    process_paragraph(p)
    doc.save(str(out_path))


def main():
    ap = argparse.ArgumentParser(
        description="Repersonnalise un rapport anonymisé (réinjecte les vrais noms).")
    ap.add_argument("rapport", help="Fichier .txt/.md/.srt/.docx contenant des pseudos.")
    ap.add_argument("--memoire", required=True, help=f"{M.NOM_MEMOIRE} (table pseudo<->réel).")
    ap.add_argument("--court", action="store_true",
                    help="Remplacer par la variante la plus courte (défaut : canonique).")
    ap.add_argument("--out", help="Fichier de sortie (défaut : <nom>_REPERSONNALISE<ext>).")
    args = ap.parse_args()

    rpath = Path(args.rapport)
    if not rpath.exists():
        die(f"Rapport introuvable : {rpath}")
    mpath = Path(args.memoire)
    if not mpath.exists():
        die(f"Mémoire introuvable : {mpath}")

    mem = M.charger_memoire(mpath)
    if not mem.get("entrees"):
        die("La mémoire ne contient aucune entrée (rien à repersonnaliser).")

    mapping = construire_mapping(mem, court=args.court)
    replace_in, counts = make_replacer(mapping)

    out = Path(args.out) if args.out else rpath.with_name(
        f"{rpath.stem}_REPERSONNALISE{rpath.suffix}")

    ext = rpath.suffix.lower()
    if ext == ".docx":
        traiter_docx(rpath, out, replace_in)
    elif ext in (".txt", ".md", ".srt", ""):
        out.write_text(traiter_texte(rpath, replace_in), encoding="utf-8")
    else:
        die(f"Format non pris en charge : {ext}. Formats : .txt .md .srt .docx")

    total = sum(counts.values())
    print(f"[OK] Fichier repersonnalisé : {out}")
    print(f"     {total} pseudo(s) remplacé(s).")
    # pseudos jamais rencontrés
    vus = {p.replace("\\b", "").replace("\\", "") for p in counts}  # approximatif
    print("\n⚠ Ce fichier contient les VRAIS NOMS : ne JAMAIS l'envoyer à une IA externe.")


if __name__ == "__main__":
    main()
