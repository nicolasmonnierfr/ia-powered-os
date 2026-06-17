#!/usr/bin/env python3
"""
serveur_tagueur.py — Serveur local pour le tagueur (tagger.html).

Sert le tagueur ET les fichiers du DOSSIER D'ENTRETIEN courant, pour que
l'outil charge automatiquement l'audio (racine) + le .srt (1_transcription/)
et ecrive ses exports dans 2_coupe/ sans selection manuelle dans le navigateur.

Le serveur tourne sur 127.0.0.1 uniquement (jamais expose au reseau).

Arret : HEARTBEAT. La page envoie /ping regulierement ; sans ping pendant
GRACE_SEC, le serveur s'arrete seul (onglet ferme = plus de ping = arret).
Ctrl+C dans la console fonctionne aussi.

Usage (lance par taguer.ps1 depuis le dossier d'entretien) :
    python serveur_tagueur.py --root "<dossier_entretien>" --tagger "<chemin tagger.html>" [--port 8765]

Routes :
    GET  /                      -> tagger.html (mode serveur)
    GET  /api/manifest          -> {audio, srt} : fichiers detectes dans le dossier
    GET  /api/audio             -> flux de l'audio (racine)
    GET  /api/srt               -> texte du .srt (1_transcription/ sinon racine)
    POST /api/export            -> ecrit plan + srt + txt dans 2_coupe/
    POST /api/ping              -> heartbeat (garde le serveur en vie)
"""

import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".mp4", ".mkv", ".webm", ".flac", ".ogg", ".aac", ".wma", ".opus"}
MIME_AUDIO = {
    ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".mp4": "video/mp4",
    ".mkv": "video/x-matroska", ".webm": "audio/webm", ".flac": "audio/flac",
    ".ogg": "audio/ogg", ".aac": "audio/aac", ".wma": "audio/x-ms-wma", ".opus": "audio/opus",
}
GRACE_SEC = 15.0          # arret si pas de ping pendant ce delai
CHECK_EVERY = 3.0         # frequence de verification du heartbeat


# ---------------------------------------------------------------------------
# Etat partage (dossier, dernier ping)
# ---------------------------------------------------------------------------
class Etat:
    def __init__(self, root: Path, tagger: Path):
        self.root = root
        self.tagger = tagger
        self.last_ping = time.time()
        self.lock = threading.Lock()

    def touch(self):
        with self.lock:
            self.last_ping = time.time()

    def idle(self) -> float:
        with self.lock:
            return time.time() - self.last_ping


def trouver_audio(root: Path):
    audios = sorted(f for f in root.iterdir()
                    if f.is_file() and f.suffix.lower() in AUDIO_EXTS)
    return audios[0] if audios else None


def trouver_srt(root: Path):
    # priorite : 1_transcription/, repli : racine
    sub = root / "1_transcription"
    if sub.is_dir():
        for f in sorted(sub.iterdir()):
            if f.is_file() and f.suffix.lower() == ".srt":
                return f
    for f in sorted(root.iterdir()):
        if f.is_file() and f.suffix.lower() == ".srt":
            return f
    return None


def trouver_memoire(depart: Path):
    """Recherche ascendante du memoire_client.json (marqueur de perimetre)."""
    cur = depart
    while True:
        cand = cur / "memoire_client.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            return None
        cur = cur.parent


def noms_locuteurs_connus(root: Path):
    """Noms de personnes deja connus du client (via memoire_client.json en
    ascendant), pour pre-remplir le nommage des locuteurs -> meme personne =
    meme nom = meme pseudo a l'anonymisation (coherence inter-entretiens)."""
    mp = trouver_memoire(root)
    if not mp:
        return []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "anonymisation"))
        import memoire as M
        return M.noms_personnes(M.charger_memoire(mp))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Handler HTTP
# ---------------------------------------------------------------------------
def make_handler(etat: Etat):
    class Handler(BaseHTTPRequestHandler):
        # silence : pas de log par requete (sauf erreurs)
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if extra:
                for k, v in extra.items():
                    self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        # --- GET -----------------------------------------------------------
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/" or path == "/index.html":
                return self._serve_tagger()
            if path == "/api/manifest":
                return self._manifest()
            if path == "/api/audio":
                return self._audio()
            if path == "/api/srt":
                return self._srt()
            self._json(404, {"error": "not found"})

        def _serve_tagger(self):
            try:
                html = etat.tagger.read_bytes()
            except OSError as e:
                return self._json(500, {"error": f"tagger.html illisible : {e}"})
            self._send(200, html, "text/html; charset=utf-8")

        def _manifest(self):
            audio = trouver_audio(etat.root)
            srt = trouver_srt(etat.root)
            self._json(200, {
                "root": str(etat.root),
                "audio": audio.name if audio else None,
                "srt": (srt.name if srt else None),
                "srt_dir": (str(srt.parent.relative_to(etat.root)) if srt else None),
                "locuteurs_connus": noms_locuteurs_connus(etat.root),
            })

        def _audio(self):
            audio = trouver_audio(etat.root)
            if not audio:
                return self._json(404, {"error": "aucun audio a la racine"})
            try:
                data = audio.read_bytes()
            except OSError as e:
                return self._json(500, {"error": str(e)})
            ctype = MIME_AUDIO.get(audio.suffix.lower(), "application/octet-stream")
            self._send(200, data, ctype, extra={"Accept-Ranges": "none"})

        def _srt(self):
            srt = trouver_srt(etat.root)
            if not srt:
                return self._json(404, {"error": "aucun .srt trouve"})
            try:
                txt = srt.read_text(encoding="utf-8")
            except OSError as e:
                return self._json(500, {"error": str(e)})
            self._send(200, txt.encode("utf-8"), "text/plain; charset=utf-8")

        # --- POST ----------------------------------------------------------
        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/ping":
                etat.touch()
                return self._json(200, {"ok": True})
            if path == "/api/export":
                return self._export()
            self._json(404, {"error": "not found"})

        def _read_body(self):
            n = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(n) if n else b""

        def _export(self):
            try:
                payload = json.loads(self._read_body().decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                return self._json(400, {"error": f"corps JSON invalide : {e}"})
            files = payload.get("files")
            if not isinstance(files, dict) or not files:
                return self._json(400, {"error": "champ 'files' attendu (dict nom->contenu)"})

            coupe = etat.root / "2_coupe"
            try:
                coupe.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return self._json(500, {"error": f"creation 2_coupe impossible : {e}"})

            ecrits = []
            for name, content in files.items():
                # garde-fou : pas de chemin, juste un nom de fichier
                safe = os.path.basename(str(name))
                if not safe or safe != str(name):
                    return self._json(400, {"error": f"nom de fichier invalide : {name}"})
                try:
                    (coupe / safe).write_text(str(content), encoding="utf-8")
                    ecrits.append(safe)
                except OSError as e:
                    return self._json(500, {"error": f"ecriture {safe} : {e}"})
            self._json(200, {"ok": True, "ecrits": ecrits, "dossier": str(coupe)})

    return Handler


# ---------------------------------------------------------------------------
# Boucle heartbeat
# ---------------------------------------------------------------------------
def watchdog(etat: Etat, httpd):
    # Laisse un delai initial pour que la page ait le temps de charger et pinger.
    time.sleep(GRACE_SEC)
    while True:
        if etat.idle() > GRACE_SEC:
            print(f"[serveur] Aucun ping depuis {GRACE_SEC:.0f}s -> arret.")
            threading.Thread(target=httpd.shutdown, daemon=True).start()
            return
        time.sleep(CHECK_EVERY)


def main():
    ap = argparse.ArgumentParser(description="Serveur local du tagueur.")
    ap.add_argument("--root", required=True, help="Dossier racine de l'entretien (sert l'audio + le .srt).")
    ap.add_argument("--tagger", required=True, help="Chemin de tagger.html.")
    ap.add_argument("--port", type=int, default=8765, help="Port (defaut 8765 ; repli auto si occupe).")
    ap.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir le navigateur.")
    ap.add_argument("--find", default="", help="Terme a rechercher : ouvre le tagueur sur ce passage (?find=).")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    tagger = Path(args.tagger).resolve()
    if not root.is_dir():
        print(f"[ERREUR] Dossier introuvable : {root}", file=sys.stderr); sys.exit(1)
    if not tagger.is_file():
        print(f"[ERREUR] tagger.html introuvable : {tagger}", file=sys.stderr); sys.exit(1)

    etat = Etat(root, tagger)
    Handler = make_handler(etat)

    # Bind 127.0.0.1 uniquement ; repli sur un port libre si 'port' est pris.
    port = args.port
    httpd = None
    for p in [port] + list(range(8766, 8786)):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        print("[ERREUR] Aucun port libre entre 8765 et 8785.", file=sys.stderr); sys.exit(1)

    url = f"http://127.0.0.1:{port}/"
    print(f"[serveur] Dossier d'entretien : {root}")
    print(f"[serveur] Tagueur servi sur   : {url}")
    print(f"[serveur] Ferme l'onglet pour arreter (auto apres {GRACE_SEC:.0f}s sans activite), ou Ctrl+C.")

    open_url = url + ("?find=" + quote(args.find) if args.find else "")
    threading.Thread(target=watchdog, args=(etat, httpd), daemon=True).start()
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(open_url)), daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serveur] Interruption clavier -> arret.")
    finally:
        httpd.server_close()
        print("[serveur] Arrete.")


if __name__ == "__main__":
    main()
