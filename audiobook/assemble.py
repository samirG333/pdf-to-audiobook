"""Audio assembly with ffmpeg: silences, chapter MP3s and the final M4B."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

SAMPLE_RATE = 24000   # edge-tts default output: 24 kHz mono MP3, 48 kbit/s
MP3_BITRATE = "48k"


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise FFmpegError(f"'{tool}' nebyl nalezen. Nainstaluj ffmpeg (macOS: brew install ffmpeg).")


def _run(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip() or f"ffmpeg failed: {args}")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def silence(folder: Path, ms: int) -> Path:
    path = folder / f"silence_{ms}ms.mp3"
    if not path.exists():
        _run(["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", f"{ms / 1000:.3f}",
              "-c:a", "libmp3lame", "-b:a", MP3_BITRATE, "-ar", str(SAMPLE_RATE), "-ac", "1", str(path)])
    return path


def _concat_list(files: list[Path], list_path: Path) -> Path:
    lines = []
    for f in files:
        escaped = str(f.resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_path


def concat_mp3(files: list[Path], out: Path, tags: dict[str, str] | None = None) -> None:
    """Join MP3 pieces losslessly (same codec parameters) and tag the result."""
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = _concat_list(files, out.with_suffix(".concat.txt"))
    meta = [arg for k, v in (tags or {}).items() for arg in ("-metadata", f"{k}={v}")]
    tmp = out.with_name(out.stem + ".tmp.mp3")
    try:
        _run(["-f", "concat", "-safe", "0", "-i", str(lst), "-map", "0:a", "-c", "copy",
              "-id3v2_version", "3", *meta, str(tmp)])
        tmp.replace(out)
    finally:
        lst.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


def _ffmeta_escape(value: str) -> str:
    for ch in ("\\", "=", ";", "#", "\n"):
        value = value.replace(ch, "\\" + ch)
    return value


def build_m4b(chapter_files: list[Path], titles: list[str], out: Path, *, title: str,
              author: str, cover: Path | None = None, bitrate: str = "64k",
              extra_meta: dict[str, str] | None = None) -> list[tuple[str, float]]:
    """Encode all chapters into one AAC .m4b with chapter markers and metadata."""
    out.parent.mkdir(parents=True, exist_ok=True)
    durations = [duration(f) for f in chapter_files]

    meta = [";FFMETADATA1",
            f"title={_ffmeta_escape(title)}",
            f"album={_ffmeta_escape(title)}",
            f"artist={_ffmeta_escape(author)}",
            f"album_artist={_ffmeta_escape(author)}",
            "genre=Audiobook"]
    for k, v in (extra_meta or {}).items():
        meta.append(f"{k}={_ffmeta_escape(v)}")
    start = 0
    for t, d in zip(titles, durations):
        end = start + int(round(d * 1000))
        meta += ["", "[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}",
                 f"title={_ffmeta_escape(t)}"]
        start = end
    meta_path = out.with_suffix(".ffmeta.txt")
    meta_path.write_text("\n".join(meta) + "\n", encoding="utf-8")
    lst = _concat_list(chapter_files, out.with_suffix(".concat.txt"))
    tmp = out.with_name(out.stem + ".tmp.m4b")

    args = ["-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(meta_path)]
    if cover:
        args += ["-i", str(cover)]
    args += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
    if cover:
        args += ["-map", "2:v", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
    args += ["-c:a", "aac", "-b:a", bitrate, "-ac", "1", "-ar", str(SAMPLE_RATE),
             "-movflags", "+faststart", "-brand", "M4B ", "-f", "ipod", str(tmp)]
    try:
        _run(args)
        tmp.replace(out)
    finally:
        meta_path.unlink(missing_ok=True)
        lst.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
    return list(zip(titles, durations))
