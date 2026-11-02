"""TikTok Downloader local : vidéos sans filigrane en qualité max + MP3."""
import io
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

from flask import Flask, jsonify, render_template, request, send_file
import yt_dlp

app = Flask(__name__)

TIKTOK_RE = re.compile(r"^https?://([a-z0-9-]+\.)*tiktok\.com/", re.I)
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

# Le format "download" de TikTok porte le filigrane : on l'exclut partout.
NO_WM = "[format_id!*=download][format_note!*=?watermark]"
FORMATS = {
    # Meilleure résolution dispo (souvent H.265 / 1080p)
    "hd": f"best{NO_WM}",
    # H.264 : lisible partout (Windows, iPhone, montage…)
    "h264": f"best[vcodec^=h264]{NO_WM}/best[vcodec^=avc]{NO_WM}/best{NO_WM}",
}
# Le son est extrait de la vidéo elle-même (la piste "musique" séparée est souvent coupée/indispo)
FORMATS["mp3"] = FORMATS["h264"]

# Outils que les editeurs utilisent pour "contourner la compression TikTok" :
# ils bourrent le flux de faux paquets / tordent les métadonnées, et les lecteurs PC plantent.
PATCH_SIGNATURES = ("zilem", "compressbase", "patched", "bypass", "nocompress")


def base_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format_sort": ["res", "tbr"],
    }


def clean_url(raw):
    url = (raw or "").strip()
    if not TIKTOK_RE.match(url):
        raise ValueError("Colle un lien TikTok valide (tiktok.com ou vm.tiktok.com).")
    return url


def safe_name(text, fallback="tiktok"):
    text = re.sub(r'[\\/:*?"<>|\r\n]+', " ", text or "").strip()
    return (text[:80].strip() or fallback)


# ---------- Réparation des edits "patchés" ----------

def repair_reason(path):
    """Renvoie la raison pour laquelle la vidéo doit être réparée, ou None si elle est saine."""
    if not (FFMPEG and FFPROBE):
        return None
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-count_packets", "-of", "json",
             "-show_entries", "format_tags:stream=codec_type,nb_frames,nb_read_packets"
             ":stream_tags:stream_side_data=rotation", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        info = json.loads(out.stdout or "{}")
    except (subprocess.SubprocessError, ValueError):
        return None

    tags = " ".join(str(v) for v in (info.get("format", {}).get("tags") or {}).values()).lower()
    if any(sig in tags for sig in PATCH_SIGNATURES):
        return "edit patché anti-compression"

    for s in info.get("streams", []):
        if s.get("codec_type") != "video":
            continue
        frames = int(s.get("nb_frames") or 0)
        packets = int(s.get("nb_read_packets") or 0)
        if frames and packets > frames * 1.2:
            return "faux paquets dans le flux vidéo"
        if any(int(float(d.get("rotation") or 0)) for d in s.get("side_data_list") or []):
            return "rotation cachée"

    # Dernier filet : on décode les 3 premières secondes et on regarde s'il y a des erreurs.
    try:
        dec = subprocess.run(
            [FFMPEG, "-v", "error", "-t", "3", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
        if dec.stderr.count("\n") >= 3:
            return "flux vidéo corrompu"
    except subprocess.SubprocessError:
        pass
    return None


def remux(path):
    """Recopie les flux tels quels dans un MP4 neuf (sans perte, ~1 s).
    Corrige les en-têtes foireux que Windows refuse, ex. une durée "inconnue" (0xFFFF…)
    laissée par certains logiciels de montage. Renvoie le nouveau chemin ou None."""
    if not FFMPEG:
        return None
    out = path.with_name(path.stem + "_remux.mp4")
    cmd = [
        FFMPEG, "-v", "error", "-y", "-i", str(path),
        "-map", "0:v", "-map", "0:a?", "-dn", "-c", "copy",
        "-movflags", "+faststart", str(out),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
    except subprocess.SubprocessError:
        return None
    return out if out.exists() and out.stat().st_size > 0 else None


def repair(path):
    """Réencode en H.264/AAC propre (lisible partout). Renvoie le nouveau chemin ou None."""
    fixed = path.with_name(path.stem + "_fixed.mp4")
    cmd = [
        FFMPEG, "-v", "error", "-y",
        "-err_detect", "ignore_err", "-max_error_rate", "1.0",
        "-i", str(path),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "17",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(fixed),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600, check=True)
    except subprocess.SubprocessError:
        return None
    return fixed if fixed.exists() and fixed.stat().st_size > 0 else None


# ---------- Routes ----------

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/info")
def info():
    try:
        url = clean_url(request.json.get("url"))
        with yt_dlp.YoutubeDL(base_opts()) as ydl:
            data = ydl.extract_info(url, download=False)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except yt_dlp.utils.DownloadError as e:
        return jsonify(error=f"Impossible de lire cette vidéo : {e}"), 422

    videos = [
        f for f in data.get("formats", [])
        if f.get("vcodec") not in (None, "none")
        and "download" not in (f.get("format_id") or "")
        and "watermark" not in (f.get("format_note") or "")
    ]
    best = max(videos, key=lambda f: f.get("height") or 0, default={})
    h264 = [f for f in videos if (f.get("vcodec") or "").startswith(("h264", "avc"))]
    best_h264 = max(h264, key=lambda f: f.get("height") or 0, default={})

    return jsonify(
        title=data.get("title") or data.get("description") or "",
        author=data.get("uploader") or data.get("creator") or "",
        thumbnail=data.get("thumbnail"),
        duration=data.get("duration"),
        fps=best.get("fps"),
        hd_label=f"{best.get('height', '?')}p",
        hd_codec="H.265" if (best.get("vcodec") or "").startswith(("h265", "hev", "bytevc1")) else "H.264",
        h264_label=f"{best_h264.get('height', '?')}p" if best_h264 else None,
    )


@app.get("/api/download")
def download():
    kind = request.args.get("type", "hd")
    if kind not in FORMATS:
        return "Type inconnu", 400
    try:
        url = clean_url(request.args.get("url"))
    except ValueError as e:
        return str(e), 400

    tmp = Path(tempfile.mkdtemp(prefix="ttdl_"))
    opts = base_opts() | {
        "format": FORMATS[kind],
        "outtmpl": str(tmp / "%(id)s.%(ext)s"),
    }
    if kind == "mp3":
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }]
    else:
        opts["merge_output_format"] = "mp4"

    repaired = ""
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=True)
        files = [p for p in tmp.iterdir() if p.is_file()]
        if not files:
            return "Téléchargement échoué", 500
        path = max(files, key=lambda p: p.stat().st_size)

        if kind != "mp3":
            reason = repair_reason(path)
            # Edit trafiqué -> réencodage complet ; sinon remux sans perte pour assainir le conteneur.
            fixed = repair(path) if reason else remux(path)
            if fixed:
                path, repaired = fixed, (reason or "")

        payload = io.BytesIO(path.read_bytes())
    except yt_dlp.utils.DownloadError as e:
        return f"Erreur : {e}", 422
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    author = safe_name(data.get("uploader"), "tiktok")
    name = f"{author}_{data.get('id', 'video')}{'.mp3' if kind == 'mp3' else '.mp4'}"
    mime = "audio/mpeg" if kind == "mp3" else "video/mp4"
    resp = send_file(payload, mimetype=mime, as_attachment=True, download_name=name)
    resp.headers["X-Filename"] = quote(name)
    resp.headers["X-Repaired"] = quote(repaired)
    return resp


if __name__ == "__main__":
    print("\n  TikTok Downloader -> http://127.0.0.1:5050\n")
    app.run(host="127.0.0.1", port=5050, debug=False)
