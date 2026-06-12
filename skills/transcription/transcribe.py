#!/usr/bin/env python3
"""
transcribe.py — Transcription + diarisation d'entretiens via WhisperX (local).

Usage :
    python skills/transcription/transcribe.py "data/entretien.m4a"
    python skills/transcription/transcribe.py "data/entretien.m4a" --no-diarize
    python skills/transcription/transcribe.py "data/entretien.m4a" --speakers 2

Sorties (dans data/transcriptions/ par defaut) :
    <nom>.txt   transcription lisible [locuteur] texte
    <nom>.json  donnees completes (segments, timestamps, locuteurs)

Concu pour CPU (sans GPU NVIDIA). Voir skills/transcription/README.md.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def load_config():
    """Charge config/.env si python-dotenv est dispo, sinon ignore."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Cherche config/.env en remontant depuis ce fichier
    here = Path(__file__).resolve()
    for parent in here.parents:
        env_path = parent / "config" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return
    # fallback : .env a la racine courante
    load_dotenv()


def fmt_timestamp(seconds):
    """Convertit des secondes en HH:MM:SS."""
    if seconds is None:
        return "??:??:??"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def fmt_srt_timestamp(seconds):
    """Convertit des secondes en HH:MM:SS,mmm (format SRT)."""
    if seconds is None:
        seconds = 0.0
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:  # arrondi limite
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def make_diarization_pipeline(hf_token, device):
    """
    Cree le pipeline de diarisation en absorbant les variantes d'API
    selon la version de whisperx installee.
    """
    import whisperx

    # Localisation de la classe (selon version : whisperx.* ou whisperx.diarize.*)
    Pipeline = getattr(whisperx, "DiarizationPipeline", None)
    if Pipeline is None:
        try:
            from whisperx.diarize import DiarizationPipeline as Pipeline
        except Exception as e:
            raise RuntimeError(
                "Impossible de trouver DiarizationPipeline dans whisperx. "
                "Verifie la version installee."
            ) from e

    # Nom du parametre du token (selon version : use_auth_token ou token)
    last_err = None
    for kwarg in ("use_auth_token", "token"):
        try:
            return Pipeline(**{kwarg: hf_token}, device=device)
        except TypeError as e:
            last_err = e
            continue
    raise RuntimeError(
        "Echec de creation du pipeline de diarisation (signature inattendue)."
    ) from last_err


def main():
    parser = argparse.ArgumentParser(description="Transcription d'entretiens (WhisperX, local).")
    parser.add_argument("audio", help="Fichier audio/video a transcrire")
    parser.add_argument("--model", default=os.getenv("WHISPER_MODEL", "large-v3"))
    parser.add_argument("--language", default=os.getenv("WHISPER_LANGUAGE", "fr"))
    parser.add_argument("--device", default=os.getenv("WHISPER_DEVICE", "cpu"))
    parser.add_argument("--compute-type", default=os.getenv("WHISPER_COMPUTE_TYPE", "int8"))
    parser.add_argument("--speakers", type=int, default=2, help="Nombre de locuteurs attendus")
    parser.add_argument("--no-diarize", action="store_true", help="Desactive la diarisation")
    parser.add_argument("--output-dir", default="data/transcriptions")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    load_config()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"[ERREUR] Fichier introuvable : {audio_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = audio_path.stem

    t0 = time.time()
    def elapsed():
        return f"[{time.time() - t0:6.1f}s]"

    import whisperx

    # --- 1. Chargement audio ---
    print(f"{elapsed()} 1. Chargement de l'audio : {audio_path.name}")
    audio = whisperx.load_audio(str(audio_path))

    # --- 2. Transcription ---
    print(f"{elapsed()} 2. Transcription (modele {args.model}, {args.device}/{args.compute_type})...")
    model = whisperx.load_model(
        args.model, args.device, compute_type=args.compute_type, language=args.language
    )
    result = model.transcribe(audio, batch_size=args.batch_size)
    detected_lang = result.get("language", args.language)
    print(f"{elapsed()}    Langue : {detected_lang}")

    # Liberation memoire
    import gc
    del model
    gc.collect()

    # --- 3. Alignement (timestamps mot-a-mot) ---
    print(f"{elapsed()} 3. Alignement des timestamps...")
    try:
        model_a, metadata = whisperx.load_align_model(language_code=detected_lang, device=args.device)
        result = whisperx.align(
            result["segments"], model_a, metadata, audio, args.device,
            return_char_alignments=False,
        )
        del model_a
        gc.collect()
    except Exception as e:
        print(f"{elapsed()}    [AVERTISSEMENT] Alignement ignore : {e}")

    # --- 4. Diarisation (qui parle) ---
    if not args.no_diarize:
        hf_token = os.getenv("HUGGINGFACE_TOKEN", "").strip()
        if not hf_token or hf_token.startswith("hf_xxxx"):
            print(f"{elapsed()}    [AVERTISSEMENT] Token HF absent/invalide. Diarisation ignoree.")
            print("                 Renseigne HUGGINGFACE_TOKEN dans config/.env")
        else:
            print(f"{elapsed()} 4. Diarisation (separation des locuteurs)... [LENT en CPU]")
            try:
                diarize_model = make_diarization_pipeline(hf_token, args.device)
                diarize_segments = diarize_model(
                    audio, min_speakers=args.speakers, max_speakers=args.speakers
                )
                result = whisperx.assign_word_speakers(diarize_segments, result)
                print(f"{elapsed()}    Diarisation terminee.")
            except Exception as e:
                print(f"{elapsed()}    [AVERTISSEMENT] Diarisation echouee : {e}")
                print("                 Verifie : token HF valide + licences pyannote acceptees.")
    else:
        print(f"{elapsed()} 4. Diarisation desactivee (--no-diarize).")

    # --- 5. Ecriture des sorties ---
    print(f"{elapsed()} 5. Ecriture des fichiers...")

    json_path = out_dir / f"{stem}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    txt_path = out_dir / f"{stem}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"# Transcription : {audio_path.name}\n")
        f.write(f"# Langue : {detected_lang} | Modele : {args.model}\n\n")
        current_speaker = None
        for seg in result.get("segments", []):
            speaker = seg.get("speaker", "LOCUTEUR_?")
            text = seg.get("text", "").strip()
            start = fmt_timestamp(seg.get("start"))
            if speaker != current_speaker:
                f.write(f"\n[{speaker}] ({start})\n")
                current_speaker = speaker
            f.write(f"{text} ")
        f.write("\n")

    # --- SRT : un sous-titre par segment, horodate, pour le tagueur ---
    srt_path = out_dir / f"{stem}.srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        index = 1
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            if not text:
                continue
            start = seg.get("start")
            end = seg.get("end")
            # Securite : si end manquant ou <= start, on met start + 1s
            if end is None or (start is not None and end <= start):
                end = (start or 0) + 1.0
            speaker = seg.get("speaker")  # peut etre None
            f.write(f"{index}\n")
            f.write(f"{fmt_srt_timestamp(start)} --> {fmt_srt_timestamp(end)}\n")
            # On prefixe le locuteur s'il existe (le tagueur pourra l'ignorer/ecraser)
            if speaker:
                f.write(f"[{speaker}] {text}\n\n")
            else:
                f.write(f"{text}\n\n")
            index += 1

    print(f"{elapsed()} Termine.")
    print(f"  -> {txt_path}")
    print(f"  -> {srt_path}")
    print(f"  -> {json_path}")


if __name__ == "__main__":
    main()
