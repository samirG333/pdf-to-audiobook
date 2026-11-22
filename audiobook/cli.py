"""Command-line interface: PDF -> chapter MP3s + chaptered M4B audiobook."""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn,
)
from rich.table import Table

from . import assemble
from .chapters import Chapter, Segment, build_chapters, build_sample
from .extract import extract, render_cover
from .tts import Job, chunk_path, resolve_voice, run_jobs

console = Console()
CHARS_PER_MINUTE = 800   # measured speaking speed of the Czech neural voices at +0 %


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="audiobook",
        description="Převede PDF knihu na audioknihu (MP3 po kapitolách + M4B s kapitolami).")
    p.add_argument("pdf", type=Path, help="vstupní PDF")
    p.add_argument("-o", "--out", type=Path, help="výstupní složka (výchozí: out/<název PDF>)")
    p.add_argument("--voice", default="vlasta",
                   help="vlasta | antonin | libovolný edge-tts hlas (výchozí: vlasta)")
    p.add_argument("--rate", default="+0%", help="rychlost řeči, např. +0%%, -5%%, +10%% (výchozí: +0%%)")
    p.add_argument("--workers", type=int, default=4, help="počet souběžně generovaných kousků (výchozí: 4)")
    p.add_argument("--retries", type=int, default=6, help="počet pokusů na jeden kousek (výchozí: 6)")
    p.add_argument("--title", help="název knihy (výchozí: z metadat PDF)")
    p.add_argument("--author", help="autor (výchozí: z metadat PDF)")
    p.add_argument("--bitrate", default="64k", help="bitrate AAC v .m4b (výchozí: 64k)")
    p.add_argument("--dry-run", action="store_true",
                   help="jen vypsat kapitoly a uložit vyčištěný text, bez generování audia")
    p.add_argument("--sample", action="store_true", help="vygenerovat jen ukázku (~2 minuty)")
    p.add_argument("--no-m4b", action="store_true", help="nevytvářet .m4b, jen MP3 kapitol")
    p.add_argument("--no-cover", action="store_true", help="nevkládat obálku (1. strana PDF) do .m4b")
    return p.parse_args(argv)


def _book_meta(info: dict, args: argparse.Namespace, pdf: Path) -> tuple[str, str]:
    meta = info["metadata"]
    title = args.title or (meta.get("title") or "").strip() or pdf.stem
    author = (meta.get("author") or "").strip()
    if not author or "microsoft" in author.lower() or "word" in author.lower():
        author = "Neznámý autor"
    return title, args.author or author


def _minutes(chars: int) -> float:
    return chars / CHARS_PER_MINUTE


def print_chapters(chapters: list[Chapter]) -> None:
    table = Table(title="Nalezené kapitoly", show_lines=False)
    for col, kw in (("#", {"justify": "right"}), ("Kapitola", {}), ("Strany", {"justify": "right"}),
                    ("Znaků", {"justify": "right"}), ("Kousků", {"justify": "right"}),
                    ("≈ min", {"justify": "right"})):
        table.add_column(col, **kw)
    for ch in chapters:
        name = ch.display_title + (f"  [dim]({ch.part})[/]" if ch.part else "")
        table.add_row(str(ch.index), name, f"{ch.start_page + 1}–{ch.end_page + 1}",
                      f"{ch.chars:,}".replace(",", " "), str(len(ch.speech_segments)),
                      f"{_minutes(ch.chars):.0f}")
    total = sum(c.chars for c in chapters)
    table.add_section()
    table.add_row("", "[b]Celkem[/]", "", f"{total:,}".replace(",", " "),
                  str(sum(len(c.speech_segments) for c in chapters)),
                  f"{_minutes(total):.0f} (≈ {_minutes(total) / 60:.1f} h)")
    console.print(table)


def write_clean_text(chapters: list[Chapter], path: Path) -> None:
    lines: list[str] = []
    for ch in chapters:
        lines.append("=" * 78)
        lines.append(f"{ch.index:02d} | {ch.display_title} | strany {ch.start_page + 1}–{ch.end_page + 1}")
        lines.append("=" * 78)
        n = 0
        for seg in ch.segments:
            if seg.kind == "pause":
                lines.append(f"[pauza {seg.ms / 1000:.1f} s]")
                continue
            n += 1
            lines.append(f"--- kousek {n} ({len(seg.text)} znaků) ---")
            lines.append(seg.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _render(segments: list[Segment], prefix: str, work: Path, voice: str, rate: str) -> tuple[list[Path], list[Job]]:
    """Map segments to audio files; returns playlist and TTS jobs to run."""
    chunks = work / "chunks"
    files: list[Path] = []
    jobs: list[Job] = []
    n = 0
    for seg in segments:
        if seg.kind == "pause":
            files.append(assemble.silence(work, seg.ms))
            continue
        n += 1
        path = chunk_path(chunks, f"{prefix}_{n:03d}", seg.text, voice, rate)
        files.append(path)
        jobs.append(Job(seg.text, path))
    return files, jobs


def synthesize(jobs: list[Job], args: argparse.Namespace, voice: str, label: str) -> None:
    pending = [j for j in jobs if not j.done]
    done_chars = sum(len(j.text) for j in jobs if j.done)
    total_chars = sum(len(j.text) for j in jobs)
    if len(pending) < len(jobs):
        console.print(f"[green]Pokračuji:[/] {len(jobs) - len(pending)} z {len(jobs)} kousků už je hotových, přeskakuji.")
    if not pending:
        return
    progress = Progress(
        TextColumn("[bold]{task.description}"), BarColumn(), MofNCompleteColumn(),
        TextColumn("[dim]{task.fields[chars]}[/]"), TimeElapsedColumn(), TextColumn("zbývá"),
        TimeRemainingColumn(), console=console)
    with progress:
        task = progress.add_task(label, total=total_chars, completed=done_chars,
                                 chars=f"{done_chars // 1000}k/{total_chars // 1000}k znaků")

        def on_done(job: Job):
            nonlocal done_chars
            done_chars += len(job.text)
            progress.update(task, advance=len(job.text),
                            chars=f"{done_chars // 1000}k/{total_chars // 1000}k znaků")

        errors = asyncio.run(run_jobs(pending, voice, args.rate, args.workers, args.retries,
                                      on_done, lambda m: progress.console.print(m)))
    if errors:
        console.print(f"[red bold]{len(errors)} kousků se nepodařilo vygenerovat.[/] "
                      "Spusť stejný příkaz znovu – hotové části se přeskočí.")
        sys.exit(2)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    pdf: Path = args.pdf.expanduser()
    if not pdf.exists():
        console.print(f"[red]Soubor neexistuje:[/] {pdf}")
        sys.exit(1)
    out: Path = (args.out or Path("out") / pdf.stem).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    voice = resolve_voice(args.voice)

    with console.status("Čtu a čistím PDF…"):
        elements, info = extract(str(pdf))
        chapters = build_chapters(elements)
    title, author = _book_meta(info, args, pdf)
    console.print(f"[bold]{title}[/] – {author} · {info['pages']} stran"
                  + (f" · text do strany {info['stop_page']}" if info["stop_page"] else ""))

    if args.dry_run:
        print_chapters(chapters)
        txt = out / f"{pdf.stem}_clean.txt"
        write_clean_text(chapters, txt)
        console.print(f"Vyčištěný text: [cyan]{txt}[/]")
        return

    assemble.require_ffmpeg()
    work = out / "work"
    (work / "chunks").mkdir(parents=True, exist_ok=True)
    for stale in (work / "chunks").glob("*.part"):  # leftovers of an interrupted run
        stale.unlink()
    tag = voice.split("-")[-1].replace("Neural", "").lower()

    if args.sample:
        segs = build_sample(chapters)
        files, jobs = _render(segs, f"sample_{tag}", work, voice, args.rate)
        synthesize(jobs, args, voice, "Ukázka")
        sample = out / f"ukazka_{tag}.mp3"
        assemble.concat_mp3(files, sample, {"title": f"{title} – ukázka", "artist": author})
        console.print(f"Ukázka ({assemble.duration(sample) / 60:.1f} min): [cyan]{sample}[/]")
        return

    print_chapters(chapters)
    playlists: list[list[Path]] = []
    all_jobs: list[Job] = []
    for ch in chapters:
        files, jobs = _render(ch.segments, f"{ch.index:02d}", work, voice, args.rate)
        playlists.append(files)
        all_jobs.extend(jobs)

    started = time.time()
    synthesize(all_jobs, args, voice, "Generuji audio")

    mp3_dir = out / "mp3"
    chapter_files: list[Path] = []
    with console.status("Spojuji kapitoly…"):
        for ch, files in zip(chapters, playlists):
            dest = mp3_dir / f"{ch.slug()}.mp3"
            assemble.concat_mp3(files, dest, {
                "title": ch.display_title, "album": title, "artist": author,
                "album_artist": author, "track": f"{ch.index}/{len(chapters)}", "genre": "Audiobook"})
            chapter_files.append(dest)
    console.print(f"MP3 kapitol: [cyan]{mp3_dir}[/] ({len(chapter_files)} souborů)")

    if not args.no_m4b:
        cover = None
        if not args.no_cover:
            cover_path = work / "cover.jpg"
            if render_cover(str(pdf), str(cover_path)):
                cover = cover_path
        m4b = out / f"{pdf.stem}.m4b"
        with console.status("Kóduji .m4b s kapitolami…"):
            marks = assemble.build_m4b(chapter_files, [c.display_title for c in chapters], m4b,
                                       title=title, author=author, cover=cover, bitrate=args.bitrate,
                                       extra_meta={"comment": f"Hlas: {voice}"})
        total = sum(d for _, d in marks)
        console.print(f"Audiokniha: [cyan]{m4b}[/] · {len(marks)} kapitol · {total / 3600:.1f} h")
    console.print(f"[green bold]Hotovo[/] za {(time.time() - started) / 60:.0f} min.")


if __name__ == "__main__":
    main()
