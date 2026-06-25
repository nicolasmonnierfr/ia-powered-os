#!/usr/bin/env python3
"""
etat.py — Moteur d'etat de l'orchestrateur (vue par projet + vue globale).

SOURCE DE VERITE du tableau d'avancement. Lecture SEULE : il n'execute rien et
n'ecrit aucun livrable (sauf le rendu ETAT.md si --out). Il reconcilie deux
sources :
  - le SYSTEME DE FICHIERS (les livrables reellement presents) — autoritaire ;
  - le `entretien.json` de chaque entretien (#15) — pour enrichir d'un statut
    transitoire (`en_cours`/`echec`) quand le livrable n'est pas encore la.

Il calcule, par entretien, l'etat de chaque etape du pipeline ET la PROCHAINE
ACTION, en distinguant ce qui est AUTOMATISABLE (transcrire / couper /
anonymiser) de ce qui requiert l'HUMAIN (taguer / analyser).

Le declenchement de l'anonymisation depend d'une trace de validation ecrite
dans le `.etat.json` par le serveur d'edition a l'export de la memoire
(`validation.faite == true`) : l'analyse est la seule etape non automatisable,
on attend donc sa confirmation explicite.

Usage :
    python etat.py [perimetre] --format table        # console (defaut)
    python etat.py [perimetre] --format json          # pour orchestrer.ps1
    python etat.py [perimetre] --format md --out ETAT.md
    perimetre : dossier contenant les sous-dossiers d'entretien (defaut: .)

100% local, stdlib uniquement.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Doit rester aligne avec _commun.ps1 ($AUDIO_EXTS) et memoire.py (NOM_MEMOIRE).
AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".mp4", ".mkv", ".webm", ".flac",
             ".ogg", ".aac", ".wma", ".opus"}
NOM_MEMOIRE = "memoire_client.json"

# --- Scan RECURSIF des perimetres -------------------------------------------
# Un "entretien" est un sous-dossier contenant un audio. On le cherche
# RECURSIVEMENT sous le perimetre inscrit, jusqu'a PROFONDEUR_MAX niveaux
# (1 = enfants directs). Deux garde-fous :
#   - on NE descend jamais dans un entretien deja identifie (ses sous-dossiers de
#     pipeline contiennent p.ex. un *_coupe.m4a qui serait pris a tort pour un
#     nouvel entretien) ;
#   - on ignore les dossiers techniques (pipeline + intermediaires/outils).
PROFONDEUR_MAX = 4
DOSSIERS_PIPELINE = {"1_transcription", "2_coupe", "3_anonymisation"}
DOSSIERS_IGNORES = {".chunks", ".git", "__pycache__", ".venv", "venv",
                    "node_modules", ".idea", ".vscode"}

# Etiquettes courtes + qui realise chaque action.
ACTIONS = {
    "transcrire":  {"auto": True,  "qui": "auto", "label": "Transcrire"},
    "taguer":      {"auto": False, "qui": "toi",  "label": "Taguer (locuteurs + coupe)"},
    "couper":      {"auto": True,  "qui": "auto", "label": "Couper l'audio"},
    "identifier":  {"auto": True,  "qui": "auto", "label": "Identifier (detection NER)"},
    "analyser":    {"auto": False, "qui": "toi",  "label": "Analyser (valider les entites)"},
    "anonymiser":  {"auto": True,  "qui": "auto", "label": "Anonymiser"},
    "anonymiser_bloque": {"auto": False, "qui": "toi", "label": "Anonymiser (memoire manquante)"},
    "termine":     {"auto": None,  "qui": "-",    "label": "Termine"},
}


# ---------------------------------------------------------------------------
# Helpers systeme de fichiers
# ---------------------------------------------------------------------------
def charger_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def trouver_audio(d: Path):
    """Retourne le 1er audio du dossier (ordre alphabetique stable), ou None."""
    audios = sorted(p for p in d.iterdir()
                    if p.is_file() and p.suffix.lower() in AUDIO_EXTS)
    return audios[0] if audios else None


def trouver_ascendant(depart: Path, nom: str):
    """Remonte les parents depuis `depart` (inclus) et renvoie le 1er <nom>."""
    cur = depart
    while True:
        cand = cur / nom
        if cand.is_file():
            return cand
        if cur.parent == cur:
            return None
        cur = cur.parent


def existe_glob(d: Path, motif: str) -> bool:
    return d.is_dir() and any(d.glob(motif))


def premier_glob(d: Path, motif: str):
    if not d.is_dir():
        return None
    for p in sorted(d.glob(motif)):
        return p
    return None


def _resolve_repo_home() -> Path:
    """Localise IA-Powered-OS (pour atteindre data/.chunks).

    Priorite a IA_POWERED_OS_HOME ; repli : etat.py vit dans
    <repo>/tools/orchestrateur/, le repo est 2 niveaux au-dessus. Aligne sur
    transcribe_robuste.resolve_repo_home().
    """
    env = os.getenv("IA_POWERED_OS_HOME", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
    return Path(__file__).resolve().parents[2]


REPO_HOME = _resolve_repo_home()


def progression_transcription(stem):
    """(faits, total) des troncons d'une transcription EN COURS, ou None.

    Les intermediaires vivent cote IA-Powered-OS dans
    data/.chunks/<AAAAMMJJ>-<stem>/ (cf. transcribe_robuste.py) :
      - chunk_NNN.wav  : un troncon decoupe   -> total = nombre de .wav ;
      - chunk_NNN.json : ce troncon est transcrit (point de reprise)
                         -> faits = nombre de chunk_*.json
                         (le <stem>.json final fusionne est exclu par le motif).
    On retient le dossier le PLUS RECENT correspondant au stem (cas d'une reprise
    un autre jour, qui cree un nouveau dossier date). 100% lecture.
    """
    if not stem:
        return None
    racine = REPO_HOME / "data" / ".chunks"
    if not racine.is_dir():
        return None
    candidats = []
    for d in racine.iterdir():
        if not d.is_dir():
            continue
        parts = d.name.split("-", 1)
        if (len(parts) == 2 and len(parts[0]) == 8 and parts[0].isdigit()
                and parts[1] == stem):
            candidats.append(d)
    if not candidats:
        return None
    d = max(candidats, key=lambda p: p.stat().st_mtime)
    total = sum(1 for _ in d.glob("chunk_*.wav"))
    faits = sum(1 for _ in d.glob("chunk_*.json"))
    if total <= 0:
        return None
    return (faits, total)


# ---------------------------------------------------------------------------
# Calcul d'etat d'un entretien
# ---------------------------------------------------------------------------
def etat_entretien(d: Path):
    """Calcule l'etat complet d'un dossier d'entretien (qui contient un audio)."""
    audio = trouver_audio(d)
    stem = audio.stem if audio else None
    ext = audio.suffix if audio else ""

    d_trans = d / "1_transcription"
    d_coupe = d / "2_coupe"
    d_anon = d / "3_anonymisation"

    projet = charger_json(d / "entretien.json") or {}
    etapes_pj = projet.get("etapes", {}) if isinstance(projet, dict) else {}

    def statut_pj(nom):
        e = etapes_pj.get(nom)
        return e.get("statut") if isinstance(e, dict) else None

    # --- Transcription -----------------------------------------------------
    trans_srt = bool(stem) and (d_trans / f"{stem}.srt").is_file()
    if not trans_srt:
        trans_srt = existe_glob(d_trans, "*.srt")
    if trans_srt:
        transcription = "fait"
    else:
        sp = statut_pj("transcription")
        transcription = sp if sp in ("en_cours", "echec") else "a_faire"

    # Progression par troncon (uniquement quand ca tourne : evite tout I/O inutile)
    progression = progression_transcription(stem) if transcription == "en_cours" else None

    # --- Tag (plan de coupe genere par le tagueur) -------------------------
    plan = (d_coupe / "plan_de_coupe.json").is_file()
    tag = "fait" if plan else "a_faire"

    # --- Coupe (audio raccourci) -------------------------------------------
    coupe_audio = False
    if stem and ext:
        coupe_audio = (d_coupe / f"{stem}_coupe{ext}").is_file()
    if not coupe_audio:
        coupe_audio = any(existe_glob(d_coupe, f"*_coupe{e}") for e in AUDIO_EXTS)
    if coupe_audio:
        coupe = "fait"
    else:
        sp = statut_pj("coupe")
        coupe = sp if sp in ("en_cours", "echec") else "a_faire"

    # --- Analyse (detection + VALIDATION humaine tracee) -------------------
    etat_file = premier_glob(d_anon, "*.etat.json")
    analyse_validee = False
    if etat_file:
        data = charger_json(etat_file)
        if isinstance(data, dict):
            v = data.get("validation")
            analyse_validee = bool(isinstance(v, dict) and v.get("faite"))
    if analyse_validee:
        analyse = "valide"
    elif etat_file:
        analyse = "detecte"      # detection faite mais pas (encore) validee
    else:
        analyse = "a_faire"

    # --- Anonymisation (remplacement applique) -----------------------------
    anon_applique = existe_glob(d_anon, "*_anonymise.*")
    if anon_applique:
        anonymisation = "fait"
    else:
        sp = statut_pj("anonymisation")
        anonymisation = "a_faire"  # le statut pj 'en_cours' = detection faite, on l'ignore ici

    # --- Memoire du perimetre (recherche ascendante depuis le parent) ------
    memoire = trouver_ascendant(d.parent, NOM_MEMOIRE)

    # --- Prochaine action (modele lineaire du pipeline) --------------------
    # L'anonymisation appliquee est le livrable FINAL : si elle est la, tout est
    # fait (vrai aussi pour un entretien legacy dont le .etat.json n'a pas la
    # trace de validation recente). On teste donc ce cas terminal en premier.
    if anonymisation == "fait":
        action = "termine"
        note = ""
    elif transcription != "fait":
        action = "transcrire"
        if transcription == "en_cours":
            note = "transcription en cours"
            if progression:
                note += f" (troncon {progression[0]}/{progression[1]})"
        elif transcription == "echec":
            note = "echec precedent — relancable"
        else:
            note = ""
    elif not plan:
        action = "taguer"
        note = "identifier les locuteurs + marquer les coupes"
    elif coupe != "fait":
        action = "couper"
        note = "echec precedent — relancable" if coupe == "echec" else "plan present, audio a reconstruire"
    elif analyse == "a_faire":
        action = "identifier"
        note = "detection NER automatique (rapide)"
    elif analyse == "detecte":
        action = "analyser"
        note = "candidats detectes — valider les entites puis exporter la memoire"
    elif anonymisation != "fait":
        if memoire is not None:
            action = "anonymiser"
            note = "analyse validee — remplacement pret"
        else:
            action = "anonymiser_bloque"
            note = "analyse validee mais memoire introuvable au perimetre"
    else:
        action = "termine"
        note = ""

    meta = ACTIONS[action]
    return {
        "dossier": d.name,
        "chemin": str(d),
        "audio": audio.name if audio else None,
        "stem": stem,
        "transcription": transcription,
        "transcription_progression": list(progression) if progression else None,
        "tag": tag,
        "coupe": coupe,
        "analyse": analyse,
        # Deux etapes DISTINCTES (auto vs humaine), derivees de `analyse` :
        #   - identification (detection NER, auto) : faite des qu'un .etat.json existe ;
        #   - validation (analyse humaine)         : faite quand validation.faite est posee.
        "identification": "fait" if analyse in ("detecte", "valide") else "a_faire",
        "validation": "valide" if analyse == "valide" else "a_faire",
        "anonymisation": anonymisation,
        "action": action,
        "auto": meta["auto"],
        "qui": meta["qui"],
        "note": note,
    }


def collecter_entretiens(perimetre: Path, profondeur_max: int = PROFONDEUR_MAX):
    """Dossiers d'entretien sous `perimetre` (recursif, borne a profondeur_max).

    Un dossier est un entretien des qu'il contient un audio : on l'ajoute et on
    NE descend PAS dedans. Sinon on continue a descendre jusqu'a profondeur_max
    (1 = enfants directs). Renvoie une liste de chemins triee, stable.
    """
    trouves = []

    def descendre(d: Path, profondeur: int):
        try:
            sous = sorted(p for p in d.iterdir() if p.is_dir())
        except OSError:
            return
        for sub in sous:
            if sub.name in DOSSIERS_PIPELINE or sub.name in DOSSIERS_IGNORES:
                continue
            if trouver_audio(sub) is not None:
                trouves.append(sub)               # entretien : on s'arrete la
            elif profondeur < profondeur_max:
                descendre(sub, profondeur + 1)

    descendre(perimetre, 1)
    return sorted(trouves, key=lambda p: str(p).lower())


def scanner_perimetre(perimetre: Path):
    """Liste les entretiens du perimetre (recursif, cf. collecter_entretiens)."""
    entretiens = []
    for sub in collecter_entretiens(perimetre):
        e = etat_entretien(sub)
        # Etiquette non ambigue quand l'entretien est imbrique : chemin relatif
        # au perimetre (deux sous-arbres peuvent avoir un dossier de meme nom).
        rel = sub.relative_to(perimetre)
        if len(rel.parts) > 1:
            e["dossier"] = rel.as_posix()
        entretiens.append(e)
    memoire = trouver_ascendant(perimetre, NOM_MEMOIRE)
    alias_legacy = trouver_ascendant(perimetre, "alias.yaml") if memoire is None else None
    return {
        "perimetre": str(perimetre),
        "memoire": str(memoire) if memoire else None,
        "memoire_existe": memoire is not None,
        "alias_legacy": str(alias_legacy) if alias_legacy else None,
        "entretiens": entretiens,
    }


# ---------------------------------------------------------------------------
# Rendus
# ---------------------------------------------------------------------------
_SYM = {"fait": "OK", "a_faire": "--", "en_cours": "..", "echec": "!!",
        "valide": "OK", "detecte": "~~"}


def _cell(v):
    return _SYM.get(v, v)


def _cell_trans(e):
    """Cellule transcription : '..' enrichi de 'faits/total' quand ca tourne."""
    base = _cell(e["transcription"])
    pr = e.get("transcription_progression")
    if pr and e["transcription"] == "en_cours":
        base += f" {pr[0]}/{pr[1]}"
    return base


def rendre_entretien(e) -> str:
    """Vue DETAILLEE d'un seul entretien (pour `ia etat`), au niveau du workflow
    courant : l'etat 'Analyse' est ici eclate en Identification (auto, detection
    NER) + Analyse/validation (humaine)."""
    etapes = [
        ("Transcription",           _cell_trans(e)),
        ("Tag (locuteurs)",         _cell(e["tag"])),
        ("Coupe (audio)",           _cell(e["coupe"])),
        ("Identification (auto)",   _cell(e["identification"])),
        ("Analyse / validation",    _cell(e["validation"])),
        ("Anonymisation",           _cell(e["anonymisation"])),
    ]
    w = max(len(n) for n, _ in etapes)
    lignes = ["", f"=== Entretien : {e['dossier']} ===",
              f"Audio : {e['audio'] or '(aucun)'}", ""]
    for nom, val in etapes:
        lignes.append(f"  {nom.ljust(w)}   {val}")
    lignes.append("")
    prochaine = ACTIONS[e["action"]]["label"]
    qui = e["qui"]
    note = f"  — {e['note']}" if e.get("note") else ""
    lignes.append(f"  Prochaine action : {prochaine}"
                  + (f"  [{qui}]" if qui != "-" else "") + note)
    lignes.append("")
    lignes.append("  Legende : OK=fait  --=a faire  ..=en cours  !!=echec")
    lignes.append("")
    return "\n".join(lignes)


def rendre_table(rapport) -> str:
    ents = rapport["entretiens"]
    lignes = []
    lignes.append("")
    lignes.append("=== Tableau d'avancement des entretiens ===")
    lignes.append(f"Perimetre : {rapport['perimetre']}")
    if rapport["memoire_existe"]:
        lignes.append(f"Memoire client : {rapport['memoire']}")
    else:
        msg = "Memoire client : AUCUNE (sera creee a la 1re validation d'analyse)"
        if rapport["alias_legacy"]:
            msg += f"  [ancien alias.yaml detecte : {rapport['alias_legacy']} -> migrer.py]"
        lignes.append(msg)
    lignes.append("")

    if not ents:
        lignes.append("  (aucun entretien trouve dans ce perimetre)")
        return "\n".join(lignes)

    cols = ["Entretien", "Transcr", "Tag", "Coupe", "Identif", "Analyse", "Anonym", "Prochaine action (qui)"]
    rows = []
    for e in ents:
        prochaine = ACTIONS[e["action"]]["label"]
        qui = e["qui"]
        rows.append([
            e["dossier"],
            _cell_trans(e),
            _cell(e["tag"]),
            _cell(e["coupe"]),
            _cell(e["identification"]),
            _cell(e["validation"]),
            _cell(e["anonymisation"]),
            f"{prochaine}" + (f"  [{qui}]" if qui != "-" else ""),
        ])
    widths = [max(len(cols[i]), max(len(r[i]) for r in rows)) for i in range(len(cols))]
    fmt = "  " + "  ".join("{:<" + str(w) + "}" for w in widths)
    lignes.append(fmt.format(*cols))
    lignes.append("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        lignes.append(fmt.format(*r))

    # Resume des actions automatisables en attente.
    auto = [e for e in ents if e["auto"] is True]
    humain = [e for e in ents if e["auto"] is False]
    termine = [e for e in ents if e["action"] == "termine"]
    lignes.append("")
    lignes.append(f"  Legende : OK=fait  --=a faire  ..=en cours  !!=echec   (Identif=detection NER auto ; Analyse=validation humaine)")
    lignes.append(f"  Auto en attente : {len(auto)}   |   Te revient : {len(humain)}   |   Termine : {len(termine)}/{len(ents)}")
    if auto:
        lignes.append("  -> Automatisable : " + ", ".join(f"{e['dossier']} ({e['action']})" for e in auto))
    if humain:
        lignes.append("  -> A toi        : " + ", ".join(f"{e['dossier']} ({e['action']})" for e in humain))
    lignes.append("")
    return "\n".join(lignes)


def rendre_md(rapport) -> str:
    ents = rapport["entretiens"]
    out = ["# Tableau d'avancement des entretiens", ""]
    out.append(f"- **Perimetre** : `{rapport['perimetre']}`")
    if rapport["memoire_existe"]:
        out.append(f"- **Memoire client** : `{rapport['memoire']}`")
    else:
        out.append("- **Memoire client** : _aucune_ (creee a la 1re validation d'analyse)")
    out.append("")
    out.append("| Entretien | Transcr. | Tag | Coupe | Identif. | Analyse | Anonym. | Prochaine action | Qui |")
    out.append("|---|:--:|:--:|:--:|:--:|:--:|:--:|---|:--:|")
    for e in ents:
        out.append("| {dossier} | {tr} | {tag} | {co} | {id} | {va} | {anon} | {act} | {qui} |".format(
            dossier=e["dossier"], tr=_cell_trans(e), tag=_cell(e["tag"]),
            co=_cell(e["coupe"]), id=_cell(e["identification"]), va=_cell(e["validation"]),
            anon=_cell(e["anonymisation"]),
            act=ACTIONS[e["action"]]["label"], qui=e["qui"]))
    out.append("")
    out.append("> Legende : OK=fait · --=a faire · ..=en cours · !!=echec — "
               "**Identif.** = detection NER (auto) ; **Analyse** = validation humaine")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Etat d'avancement des entretiens d'un perimetre.")
    ap.add_argument("perimetre", nargs="?", default=".",
                    help="Dossier contenant les sous-dossiers d'entretien (defaut: .)")
    ap.add_argument("--format", choices=["table", "json", "md"], default="table")
    ap.add_argument("--out", help="Ecrire le rendu dans ce fichier (en plus de stdout).")
    args = ap.parse_args()

    perimetre = Path(args.perimetre).resolve()
    if not perimetre.is_dir():
        print(f"[ERREUR] Perimetre introuvable : {perimetre}", file=sys.stderr)
        sys.exit(1)

    # Mode ENTRETIEN : si le chemin contient lui-meme un audio, on detaille ce
    # seul entretien (pour `ia etat`), au niveau identifier/analyser.
    if trouver_audio(perimetre) is not None:
        e = etat_entretien(perimetre)
        rendu = (json.dumps(e, ensure_ascii=False, indent=2)
                 if args.format == "json" else rendre_entretien(e))
        print(rendu)
        if args.out:
            try:
                Path(args.out).write_text(rendu + "\n", encoding="utf-8")
            except OSError as ex:
                print(f"[AVERT] Ecriture {args.out} impossible : {ex}", file=sys.stderr)
        return

    rapport = scanner_perimetre(perimetre)

    if args.format == "json":
        rendu = json.dumps(rapport, ensure_ascii=False, indent=2)
    elif args.format == "md":
        rendu = rendre_md(rapport)
    else:
        rendu = rendre_table(rapport)

    print(rendu)
    if args.out:
        try:
            Path(args.out).write_text(rendu + "\n", encoding="utf-8")
        except OSError as e:
            print(f"[AVERT] Ecriture {args.out} impossible : {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
