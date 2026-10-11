"""Private file handling: UUID file names, metadata stripping, short-lived signed URLs."""
import mimetypes
import os
import re
import shutil
import subprocess
import uuid
import wave

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse
from rest_framework.exceptions import ValidationError

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
ALLOWED_EXT = {".webm", ".ogg", ".oga", ".opus", ".mp3", ".m4a", ".wav", ".mp4", ".aac"}
MIME_TO_EXT = {
    "audio/webm": ".webm", "video/webm": ".webm", "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
    "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/m4a": ".m4a", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "audio/wave": ".wav", "audio/aac": ".aac",
}


def _ext(upload):
    ext = os.path.splitext(upload.name or "")[1].lower()
    if ext in ALLOWED_EXT:
        return ext
    ctype = (upload.content_type or "").split(";")[0].lower()
    return MIME_TO_EXT.get(ctype, ext)


def _strip_id3(data: bytes) -> bytes:
    """Remove ID3v2 header and ID3v1 trailer from an mp3 byte string."""
    if data[:3] == b"ID3" and len(data) > 10:
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        data = data[10 + size:]
    if len(data) > 128 and data[-128:-125] == b"TAG":
        data = data[:-128]
    return data


def _probe_duration(path):
    if FFPROBE:
        try:
            out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of",
                                  "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=30)
            return round(float(out.stdout.strip()), 2)
        except Exception:
            return None
    if path.endswith(".wav"):
        try:
            with wave.open(path) as w:
                return round(w.getnframes() / float(w.getframerate()), 2)
        except Exception:
            return None
    return None


def new_path(folder, ext):
    return f"{folder}/{uuid.uuid4().hex}{ext}"


def process_audio(upload, folder, max_mb=None):
    """Validate + store an uploaded audio file under a random name with metadata stripped.

    With ffmpeg installed the file is converted to mp3 (all metadata dropped); without it the
    original container is kept (mp3 ID3 tags are still removed) and duration is best effort.
    Returns (relative_path, mime_type, duration_sec).
    """
    max_mb = max_mb or settings.MAX_UPLOAD_MB
    if upload.size > max_mb * 1024 * 1024:
        raise ValidationError({"file": [f"File too large (max {max_mb} MB)."]})
    ext = _ext(upload)
    if ext not in ALLOWED_EXT:
        raise ValidationError({"file": ["Unsupported format. Use webm, ogg, mp3, m4a or wav."]})
    data = upload.read()
    if len(data) < 100:
        raise ValidationError({"file": ["Audio file is empty."]})
    if ext == ".mp3":
        data = _strip_id3(data)
    if ext == ".wav" and data[:4] != b"RIFF":
        raise ValidationError({"file": ["Not a valid WAV file."]})

    raw_rel = default_storage.save(new_path(folder, ext), ContentFile(data))
    raw_abs = default_storage.path(raw_rel)
    if FFMPEG:
        out_rel = new_path(folder, ".mp3")
        out_abs = default_storage.path(out_rel)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        res = subprocess.run([FFMPEG, "-y", "-i", raw_abs, "-vn", "-map_metadata", "-1", "-c:a", "libmp3lame",
                              "-q:a", "4", out_abs], capture_output=True, timeout=300)
        default_storage.delete(raw_rel)
        if res.returncode != 0:
            if os.path.exists(out_abs):
                os.remove(out_abs)
            raise ValidationError({"file": ["Could not decode audio file."]})
        return out_rel, "audio/mpeg", _probe_duration(out_abs)
    mime = mimetypes.types_map.get(ext) or "audio/mpeg"
    if ext in (".m4a", ".mp4"):
        mime = "audio/mp4"
    return raw_rel, mime, _probe_duration(raw_abs)


def anonymised_copy(path, folder="anon"):
    """Copy a stored file to a new random UUID name (no identity in the path)."""
    ext = os.path.splitext(path)[1]
    new_rel = new_path(folder, ext)
    with default_storage.open(path, "rb") as src:
        default_storage.save(new_rel, ContentFile(src.read()))
    return new_rel


def delete_file(path):
    if path:
        try:
            default_storage.delete(path)
        except Exception:
            pass


def sign_media(path):
    return "/api/media/" + signing.dumps({"p": path}, salt="media") + "/"


def serve_media(request, token):
    try:
        payload = signing.loads(token, salt="media", max_age=settings.SIGNED_URL_TTL)
    except signing.BadSignature:
        raise Http404()
    path = payload["p"]
    if not default_storage.exists(path):
        raise Http404()
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if path.endswith(".m4a") or path.endswith(".mp4"):
        ctype = "audio/mp4"
    size = default_storage.size(path)
    rng = re.match(r"bytes=(\d*)-(\d*)", request.headers.get("Range", ""))
    if rng and (rng.group(1) or rng.group(2)):
        start = int(rng.group(1)) if rng.group(1) else max(size - int(rng.group(2)), 0)
        end = int(rng.group(2)) if rng.group(1) and rng.group(2) else size - 1
        end = min(end, size - 1)
        with default_storage.open(path, "rb") as f:
            f.seek(start)
            body = f.read(end - start + 1)
        resp = HttpResponse(body, status=206, content_type=ctype)
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
    else:
        resp = FileResponse(default_storage.open(path, "rb"), content_type=ctype)
    resp["Accept-Ranges"] = "bytes"
    resp["Content-Length"] = str(resp.get("Content-Length") or size) if resp.status_code == 200 else str(len(resp.content))
    resp["Cache-Control"] = "private, no-store"
    resp["Content-Disposition"] = 'inline; filename="audio"'
    return resp
