#!/usr/bin/env python3
"""
reconstruire_edition.py — Reconstruit le DOCUMENT DE TRAVAIL (edition.json) du
tagueur pour un entretien LEGACY qui n'en a pas encore.

Principe (cf. tagger.html / serveur_tagueur.py) : `2_coupe/<stem>.edition.json`
est la SOURCE DE VERITE unique du montage (timeline ORIGINALE, tous les segments,
parties cachees `cut`, noms de locuteurs, texte corrige). Les fichiers coupes
(`<stem>_coupe.srt/.txt`, audio coupe) en sont des SORTIES regenerees, jamais
editees a la main.

Les entretiens traites AVANT l'introduction de edition.json n'ont que les
artefacts derives. On reconstitue le document de travail a partir de :
  - 1_transcription/<stem>.srt   : transcript BRUT (timeline originale, etiquettes
                                   locales T<n>-X) -> fournit les segments CACHES
                                   (zones rognees/coupees) et la grille temporelle ;
  - 2_coupe/plan_de_coupe.json   : keep_intervals / cut_intervals (temps ORIGINAUX) ;
  - 2_coupe/<stem>_coupe.srt     : transcript COUPE (vrais noms, texte corrige,
                                   segments CONSERVES uniquement, timeline recalee).

Reconstruction (sans appariement flou) :
  - CONSERVES  : on prend les segments du .srt COUPE et on les « de-recale » vers
    la timeline originale via keep_intervals -> vrais noms + texte corrige, cut=False.
  - CACHES     : segments du .srt BRUT qui tombent dans une zone coupee
    (cut_intervals) -> cut=True (texte brut, etiquette locale, sans locuteur).
  - On fusionne et on trie par temps : les deux ensembles sont disjoints
    (conserves dans keep_intervals, caches dans cut_intervals).

Usage :
    python reconstruire_edition.py "<dossier_entretien>"
    python reconstruire_edition.py "<dossier_entretien>" --force   # ecrase un edition.json existant
"""

import argparse
import json
import re
import sys
from pathlib import Path

MAX_LOCUTEURS = 4
EPS = 1e-6


def _srt_time(t):
    m = re.match(r"\s*(\d+):(\d+):(\d+)[,.](\d+)", t)
    if not m:
        return None
    h, mi, s, ms = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def _split_label(text):
    m = re.match(r"^\s*\[([^\]]+)\]\s*", text)
    if m:
        return m.group(1).strip(), text[m.end():].strip()
    return None, text


def parse_srt(path: Path):
    """Liste de {start, end, text, label} (label = etiquette [..] de tete)."""
    raw = path.read_text(encoding="utf-8").replace("\r", "")
    out = []
    for chunk in re.split(r"\n\s*\n", raw):
        lines = [l for l in chunk.split("\n") if l.strip() != ""]
        if not lines:
            continue
        start = end = None
        body = []
        for l in lines:
            if re.fullmatch(r"\d+", l.strip()):
                continue
            if "-->" in l:
                g = l.split("-->")
                if len(g) == 2:
                    start, end = _srt_time(g[0]), _srt_time(g[1])
                continue
            body.append(l)
        if not body or start is None:
            continue
        label, text = _split_label(" ".join(body).strip())
        out.append({"start": start, "end": end, "text": text, "label": label})
    return out


def _decale_vers_original(keeps):
    """Construit f(t_recale) -> t_original a partir des keep_intervals (temps
    originaux, tries). Le transcript coupe est la concatenation des keeps : le
    temps recale 0 = debut du 1er keep, et chaque keep ajoute sa duree."""
    bornes = []  # (recale_debut, orig_debut, duree)
    acc = 0.0
    for k in keeps:
        d = max(0.0, k["end"] - k["start"])
        bornes.append((acc, k["start"], d))
        acc += d
    total = acc

    def f(rt):
        for (rd, od, d) in bornes:
            if rt <= rd + d + EPS:
                return od + max(0.0, rt - rd)
        # au-dela : caler sur la fin du dernier keep
        return keeps[-1]["end"] if keeps else rt

    return f, total


def _chevauche(seg, intervalles):
    for c in intervalles:
        if seg["end"] > c["start"] + EPS and seg["start"] < c["end"] - EPS:
            return True
    return False


def reconstruire(root: Path):
    coupe_dir = root / "2_coupe"
    trans_dir = root / "1_transcription"
    plan_path = coupe_dir / "plan_de_coupe.json"

    srt_coupe = next((f for f in sorted(coupe_dir.glob("*.srt"))), None) if coupe_dir.is_dir() else None
    if srt_coupe is None:
        return None, "aucun .srt coupe dans 2_coupe/"
    stem = re.sub(r"_coupe$", "", srt_coupe.stem, flags=re.IGNORECASE)

    srt_brut = trans_dir / f"{stem}.srt"
    if not srt_brut.is_file():
        srt_brut = next((f for f in sorted(trans_dir.glob("*.srt"))), None) if trans_dir.is_dir() else None
    if srt_brut is None or not srt_brut.is_file():
        return None, "aucun .srt brut dans 1_transcription/"
    if not plan_path.is_file():
        return None, "aucun plan_de_coupe.json dans 2_coupe/"

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    keeps = sorted(plan.get("keep_intervals", []), key=lambda k: k["start"])
    cuts = sorted(plan.get("cut_intervals", []), key=lambda c: c["start"])
    if not keeps:
        return None, "plan sans keep_intervals"

    brut = parse_srt(srt_brut)
    coupe = parse_srt(srt_coupe)
    f_orig, _ = _decale_vers_original(keeps)

    # CONSERVES : segments du coupe de-recales vers la timeline originale.
    conserves = []
    for c in coupe:
        os_, oe = f_orig(c["start"]), f_orig(c["end"])
        conserves.append({
            "start": round(os_, 3), "end": round(oe, 3),
            "text": c["text"], "label": c["label"], "cut": False,
        })

    # CACHES : segments bruts tombant dans une zone coupee.
    caches = []
    for b in brut:
        if _chevauche(b, cuts):
            caches.append({
                "start": round(b["start"], 3), "end": round(b["end"], 3),
                "text": b["text"], "label": b["label"], "cut": True,
            })

    segments = sorted(conserves + caches, key=lambda s: s["start"])

    # Locuteurs : vrais noms issus des segments CONSERVES, dans l'ordre d'apparition.
    noms = []
    for s in conserves:
        lab = s["label"]
        if lab and lab != "NON_AFFECTE" and lab not in noms:
            noms.append(lab)
    noms = noms[:MAX_LOCUTEURS]
    idx = {lab: i for i, lab in enumerate(noms)}
    n_speakers = min(max(len(noms) or 2, 2), MAX_LOCUTEURS)
    names = [noms[i] if i < len(noms) else f"Locuteur {i + 1}" for i in range(MAX_LOCUTEURS)]

    for s in segments:
        lab = s["label"]
        s["speaker"] = idx.get(lab) if (lab in idx and not s["cut"]) else None
        s["edited"] = False

    etat = {
        "version": 1,
        "kind": "etat-edition-tagueur",
        "reconstruit_depuis": [srt_brut.name, plan_path.name, srt_coupe.name],
        "audio_source": plan.get("audio_source") or f"{stem}.m4a",
        "n_speakers": n_speakers,
        "names": names,
        "segments": segments,
    }
    out = coupe_dir / f"{stem}.edition.json"
    out.write_text(json.dumps(etat, ensure_ascii=False, indent=2), encoding="utf-8")
    return out, (f"{len(segments)} segments ({len(conserves)} conserves, "
                 f"{len(caches)} caches), {len(noms)} locuteur(s) : {', '.join(noms) or '—'}")


def main():
    ap = argparse.ArgumentParser(description="Reconstruit edition.json (doc de travail du tagueur) pour un entretien legacy.")
    ap.add_argument("root", help="Dossier racine de l'entretien.")
    ap.add_argument("--force", action="store_true", help="Ecraser un edition.json deja present.")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[ERREUR] Dossier introuvable : {root}", file=sys.stderr); sys.exit(1)

    coupe_dir = root / "2_coupe"
    deja = next((f for f in coupe_dir.glob("*.edition.json")), None) if coupe_dir.is_dir() else None
    if deja and not args.force:
        print(f"edition.json deja present : {deja.name} (—force pour ecraser)")
        return

    out, info = reconstruire(root)
    if out is None:
        print(f"[ERREUR] Reconstruction impossible : {info}", file=sys.stderr); sys.exit(2)
    print(f"edition.json reconstruit : 2_coupe/{out.name}")
    print(f"  {info}")


if __name__ == "__main__":
    main()
