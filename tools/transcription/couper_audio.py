#!/usr/bin/env python3
"""
couper_audio.py — Reconstruit un audio raccourci a partir d'un plan de coupe.

Le plan de coupe (plan_de_coupe.json) est genere par le tagueur (tagger.html) :
il decrit les intervalles de l'audio ORIGINAL a conserver. Ce script extrait
chaque intervalle et les concatene pour produire un nouvel audio, parfaitement
synchronise avec les .srt / .txt egalement exportes par le tagueur.

PRECISION : par defaut on REENCODE (precis a la milliseconde, pas de derive
cumulative). C'est volontaire — la copie de flux (-c copy) couperait aux
keyframes et desynchroniserait. Voir tools/transcription/README.md.

Usage :
    python tools/transcription/couper_audio.py plan_de_coupe.json
    python tools/transcription/couper_audio.py plan_de_coupe.json --audio "data/entretien.m4a"
    python tools/transcription/couper_audio.py plan_de_coupe.json --output "entretien_coupe.m4a"

- Sans --audio : le script utilise le champ "audio_source" du plan, cherche le
  fichier dans le repertoire courant puis a cote du plan.
- Sans --output : ecrit "<nom>_coupe<ext>" a cote de l'audio source.

Prerequis : ffmpeg dans le PATH (deja installe par bootstrap/setup-windows.ps1).
N'ecrase jamais l'audio original.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def die(msg, code=1):
    print(f"[ERREUR] {msg}", file=sys.stderr)
    sys.exit(code)


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        die("ffmpeg introuvable dans le PATH. Lance bootstrap/setup-windows.ps1 "
            "ou installe ffmpeg, puis rouvre le terminal.")
    return exe


def locate_audio(plan_path: Path, plan: dict, cli_audio: str | None) -> Path:
    """Trouve l'audio source : --audio prioritaire, sinon champ du plan."""
    if cli_audio:
        p = Path(cli_audio)
        if not p.exists():
            die(f"Audio introuvable : {p}")
        return p.resolve()

    src = plan.get("audio_source")
    if not src:
        die("Le plan ne contient pas 'audio_source'. Passe l'audio avec --audio.")

    # cherche dans le repertoire courant, puis a cote du plan, puis tel quel
    candidates = [Path.cwd() / src, plan_path.parent / src, Path(src)]
    for c in candidates:
        if c.exists():
            return c.resolve()
    die(f"Audio '{src}' introuvable (cherche dans le dossier courant et a cote du plan). "
        f"Passe-le explicitement avec --audio.")


def encoder_for(ext: str):
    """Renvoie les options d'encodage audio adaptees au format de sortie."""
    ext = ext.lower().lstrip(".")
    if ext in ("m4a", "mp4", "aac", "mov"):
        return ["-c:a", "aac", "-b:a", "192k"]
    if ext == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]
    if ext in ("wav",):
        return ["-c:a", "pcm_s16le"]
    if ext in ("ogg", "oga"):
        return ["-c:a", "libvorbis", "-q:a", "5"]
    if ext in ("flac",):
        return ["-c:a", "flac"]
    # defaut raisonnable
    return ["-c:a", "aac", "-b:a", "192k"]


def run(cmd):
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        sys.stderr.write(res.stderr.decode("utf-8", "replace"))
        die(f"ffmpeg a echoue (code {res.returncode}).")


def main():
    ap = argparse.ArgumentParser(description="Reconstruit un audio raccourci depuis un plan de coupe.")
    ap.add_argument("plan", help="Chemin du plan de coupe JSON (plan_de_coupe.json).")
    ap.add_argument("--audio", help="Audio source (sinon pris dans le plan).")
    ap.add_argument("--output", help="Fichier de sortie (sinon <nom>_coupe<ext>).")
    ap.add_argument("--copy", action="store_true",
                    help="Couper en copie de flux (rapide mais IMPRECIS, peut desynchroniser). "
                         "Deconseille ; par defaut on reencode.")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg()

    plan_path = Path(args.plan)
    if not plan_path.exists():
        die(f"Plan introuvable : {plan_path}")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"Plan JSON invalide : {e}")

    keep = plan.get("keep_intervals", [])
    if not keep:
        die("Le plan ne contient aucun intervalle a conserver ('keep_intervals' vide).")

    audio = locate_audio(plan_path, plan, args.audio)
    ext = audio.suffix or ".m4a"

    if args.output:
        out = Path(args.output).resolve()
    else:
        out = audio.with_name(f"{audio.stem}_coupe{ext}")

    if out.resolve() == audio.resolve():
        die("Le fichier de sortie serait identique a l'original. Choisis un autre --output.")

    reencode = plan.get("reencode", True) and not args.copy
    enc = encoder_for(ext) if reencode else ["-c", "copy"]

    n = len(keep)
    total = sum(i["end"] - i["start"] for i in keep)
    print(f"Audio source : {audio}")
    print(f"Sortie       : {out}")
    print(f"Intervalles a conserver : {n}  |  duree finale ~ {total:.1f}s")
    print(f"Mode : {'reencodage (precis)' if reencode else 'copie de flux (-c copy, imprecis)'}")
    if not reencode:
        print("  /!\\ La copie de flux peut decaler les coupes (keyframes). Synchro non garantie.")

    workdir = Path(tempfile.mkdtemp(prefix="coupe_"))
    parts = []
    try:
        # 1. Extraire chaque intervalle conserve
        for idx, iv in enumerate(keep):
            start = float(iv["start"])
            dur = float(iv["end"]) - start
            if dur <= 0:
                continue
            part = workdir / f"part_{idx:04d}{ext}"
            # -ss apres -i = coupe precise (decodage) quand on reencode ;
            # avec copy on met -ss avant -i pour la rapidite.
            if reencode:
                cmd = [ffmpeg, "-y", "-i", str(audio), "-ss", f"{start:.3f}",
                       "-t", f"{dur:.3f}", *enc, "-vn", str(part)]
            else:
                cmd = [ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", str(audio),
                       "-t", f"{dur:.3f}", *enc, "-vn", str(part)]
            print(f"  [{idx+1}/{n}] {start:.1f}s -> {start+dur:.1f}s")
            run(cmd)
            parts.append(part)

        if not parts:
            die("Aucun intervalle valide a extraire.")

        # 2. Concatener via le demuxeur concat
        listfile = workdir / "concat.txt"
        # ffmpeg concat exige des chemins echappes ; on reste en absolu
        listfile.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in parts),
            encoding="utf-8"
        )
        # Concatenation. Pour les formats a conteneur simple (wav), une copie de
        # flux ne reconstruit pas toujours un en-tete propre : on reencode alors
        # legerement a la jointure. Pour m4a/mp3/etc., la copie suffit (memes
        # parametres d'encodage sur tous les morceaux).
        out_ext = out.suffix.lower().lstrip(".")
        if out_ext == "wav":
            concat_codec = ["-c:a", "pcm_s16le"]
        else:
            concat_codec = ["-c", "copy"]
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0",
               "-i", str(listfile), *concat_codec, str(out)]
        print("  Concatenation...")
        run(cmd)

    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"\n[OK] Audio coupe ecrit : {out}")
    print("     Il est synchronise avec les .srt / .txt exportes par le tagueur.")
    print("     L'audio original n'a pas ete modifie.")


if __name__ == "__main__":
    main()
