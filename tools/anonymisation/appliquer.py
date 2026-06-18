#!/usr/bin/env python3
"""
appliquer.py — APPLICATION finale du pipeline d'anonymisation (local).

Prend un transcript taggé + la mémoire client (`memoire_client.json`) issue de
l'éditeur HTML, et produit :
  - <nom>_anonymise.<ext>      : transcript anonymisé (même format que l'entrée)
  - <nom>_anonymise.txt        : version LISIBLE (regroupée par locuteur, sans
                                 timecodes) — plus facile à analyser pour une IA
                                 (produite quand l'entrée est un .srt)
  - memoire_client.json        : mémoire mise à jour (À GARDER EN LOCAL)
  - <nom>_rapport.txt          : rapport de relecture (qui a été remplacé)

NOUVEAU FORMAT (refonte #14) : un seul artefact, `memoire_client.json`. Le TYPE
de chaque entité est lu DIRECTEMENT dans le champ `type` (corrige #13 : il n'est
plus déduit du préfixe du pseudo). Les pseudos parlants (SOCIETE, CONSULTANT_1)
sont pleinement supportés (corrige #8). Voir memoire.py pour le schéma.

Le remplacement applique les variantes les PLUS LONGUES d'abord (« Jean Dupont »
avant « Jean »), insensible à la casse, en préservant la structure du .srt et
les étiquettes de locuteurs génériques.

Rétrocompatibilité : --alias/--table (ancien format) sont migrés à la volée.

100% local. Voir tools/anonymisation/README.md et SCHEMA.md.

Usage :
    python appliquer.py exemple.srt --memoire memoire_client.json
    python appliquer.py exemple.srt --memoire memoire_client.json --client Acme
    python appliquer.py exemple.srt --memoire m.json --ignorer-global ig.json
    # rétrocompat :
    python appliquer.py exemple.srt --alias alias.yaml --table table.json
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memoire as M  # noqa: E402


# Console Windows en cp1252 : un print accentué/emoji (ex. « ⚠ ») planterait
# (UnicodeEncodeError) et ferait échouer l'anonymisation pour une raison purement
# cosmétique. On force stdout/stderr en UTF-8 (sans effet si déjà le cas).
for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8")
    except Exception:
        pass


def die(msg, code=1):
    print(f"[ERREUR] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Remplacement dans le texte (insensible à la casse, mots entiers si alpha)
# ---------------------------------------------------------------------------
def make_replacer(mapping, ignorer):
    ignorer_low = {x.lower() for x in ignorer}
    compiled = []
    for variante, pseudo in mapping:
        if not variante or variante.lower() in ignorer_low:
            continue
        left = r"\b" if variante[:1].isalnum() else ""
        right = r"\b" if variante[-1:].isalnum() else ""
        pat = re.compile(left + re.escape(variante) + right, flags=re.IGNORECASE)
        compiled.append((pat, pseudo))
    counts = {}

    def replace_in(text):
        for pat, pseudo in compiled:
            def _sub(m):
                counts[pseudo] = counts.get(pseudo, 0) + 1
                return pseudo
            text = pat.sub(_sub, text)
        return text
    return replace_in, counts


# ---------------------------------------------------------------------------
# Traitement du transcript en préservant la structure
# ---------------------------------------------------------------------------
def anonymize_transcript(path, replace_in, generiques):
    raw = path.read_text(encoding="utf-8")
    ext = path.suffix.lower()
    gen_low = {g.lower() for g in generiques}

    def handle_label_line(line):
        m = re.match(r"^(\s*\[)([^\]]+)(\]\s*)(.*)$", line)
        if not m:
            return replace_in(line)
        pre, label, post, rest = m.groups()
        if label.strip().lower() in gen_low:
            new_label = label
        else:
            new_label = replace_in(label)
        return pre + new_label + post + replace_in(rest)

    if ext == ".srt" or "-->" in raw:
        out_blocks = []
        for chunk in raw.replace("\r", "").split("\n\n"):
            lines = chunk.split("\n")
            new_lines = []
            for l in lines:
                if re.fullmatch(r"\s*\d+\s*", l) or "-->" in l:
                    new_lines.append(l)
                elif l.strip() == "":
                    new_lines.append(l)
                else:
                    new_lines.append(handle_label_line(l))
            out_blocks.append("\n".join(new_lines))
        return "\n\n".join(out_blocks)
    else:
        out = []
        for l in raw.replace("\r", "").split("\n"):
            out.append(handle_label_line(l) if l.strip() else l)
        return "\n".join(out)


def _srt_time_to_sec(t):
    m = re.match(r"\s*(\d+):(\d+):(\d+)[,.](\d+)", t)
    if not m:
        return None
    h, mi, s, ms = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def _fmt_mmss(t):
    if t is None:
        return None
    h, m, s = int(t // 3600), int((t % 3600) // 60), int(t % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def srt_vers_txt(srt_text):
    """Transforme un .srt (déjà anonymisé) en transcript LISIBLE : regroupé par
    tour de parole, sans indices ni timecodes parasites (une ligne d'en-tête
    [Locuteur] (m:ss) par changement de locuteur). Bien plus facile à analyser
    pour une IA. Même rendu que le .txt du tagueur."""
    out, cur = "", object()   # sentinelle != de tout locuteur (y compris None)
    for chunk in srt_text.replace("\r", "").split("\n\n"):
        lines = [l for l in chunk.split("\n") if l.strip() != ""]
        if not lines:
            continue
        start = None
        body = []
        for l in lines:
            if re.fullmatch(r"\s*\d+\s*", l):
                continue
            if "-->" in l:
                start = _srt_time_to_sec(l.split("-->")[0])
                continue
            body.append(l)
        if not body:
            continue
        text = " ".join(body).strip()
        m = re.match(r"^\s*\[([^\]]+)\]\s*(.*)$", text)
        speaker = m.group(1).strip() if m else "NON_AFFECTE"
        if m:
            text = m.group(2).strip()
        if speaker != cur:
            tc = _fmt_mmss(start)
            out += f"\n[{speaker}]" + (f" ({tc})" if tc else "") + "\n"
            cur = speaker
        if text:
            out += text + " "
    return out.strip() + "\n"


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Applique l'anonymisation et produit les sorties.")
    ap.add_argument("transcript", help="Fichier .txt ou .srt taggé.")
    ap.add_argument("--memoire", help=f"{M.NOM_MEMOIRE} (mémoire client, issue de l'éditeur).")
    ap.add_argument("--ignorer-global", help="ignorer_global.json (faux positifs universels).")
    ap.add_argument("--client", help="Nom du client (stocké dans la mémoire).")
    ap.add_argument("--outdir", help="Dossier de sortie pour le transcript+rapport (défaut : à côté du transcript).")
    ap.add_argument("--memoire-out", help=f"Où réécrire la mémoire (défaut : le --memoire d'entrée, sinon ./{M.NOM_MEMOIRE}).")
    ap.add_argument("--alias", help="[ancien] alias.yaml (migré à la volée).")
    ap.add_argument("--table", help="[ancien] table_correspondance.json (migré à la volée).")
    args = ap.parse_args()

    tpath = Path(args.transcript)
    if not tpath.exists():
        die(f"Transcript introuvable : {tpath}")

    # --- Charger la mémoire (nouveau format prioritaire) --------------------
    if args.memoire:
        mem = M.charger_memoire(Path(args.memoire))
        memoire_in = Path(args.memoire)
    elif args.alias or args.table:
        mem = M.migrer_depuis_ancien(
            Path(args.alias) if args.alias else None,
            Path(args.table) if args.table else None,
            client=args.client)
        memoire_in = None
    else:
        die("Fournis --memoire memoire_client.json (ou --alias/--table en rétrocompat).")

    if args.client:
        mem["client"] = args.client

    ignorer_global = M.charger_ignorer_global(
        Path(args.ignorer_global) if args.ignorer_global else None)
    ignorer = list(mem.get("ignorer", [])) + list(ignorer_global)

    # Canoniques + compteurs cohérents avant écriture. Le canonique sert de cible
    # à la repersonnalisation : on évite d'y figer une étiquette technique
    # (« NON_AFFECTE » / « Locuteur N »), qui réintroduirait un faux nom.
    def _placeholder(s):
        return (not s) or s == "NON_AFFECTE" or bool(re.match(r"(?i)\s*locuteur\s*\d+\s*$", s))
    for e in mem["entrees"]:
        if not e.get("canonique") and e.get("variantes"):
            vraies = [v for v in e["variantes"] if not _placeholder(v)]
            e["canonique"] = max(vraies or e["variantes"], key=len)
    mem["compteurs"] = M.compteurs_depuis_entrees(mem["entrees"])

    mapping = M.mapping_remplacement(mem)
    if not mapping:
        die("Aucune correspondance à appliquer (mémoire vide ?).")

    replace_in, counts = make_replacer(mapping, ignorer)
    anonymized = anonymize_transcript(
        tpath, replace_in, mem.get("locuteurs_generiques", []))

    outdir = Path(args.outdir) if args.outdir else tpath.parent
    outdir.mkdir(parents=True, exist_ok=True)
    out_transcript = outdir / f"{tpath.stem}_anonymise{tpath.suffix}"
    out_report = outdir / f"{tpath.stem}_rapport.txt"

    # Destination de la mémoire mise à jour.
    if args.memoire_out:
        out_memoire = Path(args.memoire_out)
    elif memoire_in:
        out_memoire = memoire_in
    else:
        out_memoire = outdir / M.NOM_MEMOIRE

    out_transcript.write_text(anonymized, encoding="utf-8")
    M.ecrire_memoire(out_memoire, mem)

    # Sortie LISIBLE en plus du .srt : transcript regroupé par locuteur, sans
    # indices/timecodes — bien plus facile à analyser pour une IA. Produit
    # uniquement quand l'entrée est un .srt (si l'entrée est déjà un .txt,
    # out_transcript EST déjà ce format).
    out_txt = None
    if tpath.suffix.lower() == ".srt" or "-->" in anonymized:
        out_txt = outdir / f"{tpath.stem}_anonymise.txt"
        out_txt.write_text(srt_vers_txt(anonymized), encoding="utf-8")

    # Rapport de relecture
    lines = ["RAPPORT D'ANONYMISATION", "=" * 40,
             f"Transcript      : {tpath.name}",
             f"Sortie (.srt)   : {out_transcript.name}"]
    if out_txt:
        lines.append(f"Sortie (.txt)   : {out_txt.name}   (lisible, pour analyse IA)")
    lines += [f"Client          : {mem.get('client') or '(non précisé)'}",
             f"Mémoire         : {out_memoire.name}",
             f"Entités         : {len(mem['entrees'])}", "",
             "Remplacements effectués (pseudo <- variantes) :"]
    for e in sorted(mem["entrees"], key=lambda x: x["pseudo"]):
        used = counts.get(e["pseudo"], 0)
        lines.append(f"  {e['pseudo']:14} [{e['type']}] <- {', '.join(e['variantes'])}   "
                     f"({used} remplacement(s) dans ce transcript)")
    jamais = [e["pseudo"] for e in mem["entrees"] if counts.get(e["pseudo"], 0) == 0]
    if jamais:
        lines += ["", "Pseudos de la mémoire non rencontrés dans ce transcript :",
                  "  " + ", ".join(jamais)]
    lines += ["", "⚠ RELECTURE RECOMMANDÉE : vérifier qu'aucune information",
              "  ré-identifiante (surnom, détail indirect) ne subsiste avant envoi.",
              "⚠ memoire_client.json contient les vrais noms : NE PAS l'envoyer."]
    out_report.write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] Transcript anonymisé : {out_transcript}")
    if out_txt:
        print(f"[OK] Version lisible .txt : {out_txt}")
    print(f"[OK] Mémoire (LOCALE)     : {out_memoire}")
    print(f"[OK] Rapport              : {out_report}")
    total = sum(counts.values())
    print(f"\n{total} remplacement(s) sur {len(mem['entrees'])} entité(s).")
    if jamais:
        print(f"Note : {len(jamais)} entité(s) de la mémoire absente(s) de ce transcript.")
    print("\n⚠ Relis le transcript anonymisé avant de l'envoyer. "
          "Garde memoire_client.json en local.")


if __name__ == "__main__":
    main()
