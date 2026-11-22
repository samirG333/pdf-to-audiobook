"""Build chapters from extracted elements and split them into TTS segments."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .clean import (
    collect_acronyms, ensure_terminal, normalize, ordinal_f, sentence_case,
    split_long, split_sentences,
)
from .extract import Element

MAX_CHARS = 3000
# Extra silence added on top of the ~0.9-1.2 s of trailing silence that every
# edge-tts clip already ends with (so the audible pause is roughly +1 s longer).
TITLE_PAUSE_MS = 800      # after the spoken chapter title  (~2 s audible)
PART_PAUSE_MS = 800       # after a spoken part title       (~2 s audible)
SUB_PAUSE_MS = 400        # before a sub-heading            (~1.4 s audible)


@dataclass
class Segment:
    kind: str             # "speech" | "pause"
    text: str = ""
    ms: int = 0


@dataclass
class Chapter:
    index: int                    # 1-based position in the audiobook
    title: str                    # display title (bookmark / file name)
    number: int | None = None
    subtitle: str = ""
    part: str = ""                # "Část druhá: Proč byste měli spát"
    is_front: bool = False
    start_page: int = 0
    end_page: int = 0
    blocks: list[tuple[str, str]] = field(default_factory=list)   # (kind, normalized text)
    segments: list[Segment] = field(default_factory=list)

    @property
    def display_title(self) -> str:
        return f"{self.number}. {self.title}" if self.number else self.title

    @property
    def chars(self) -> int:
        return sum(len(s.text) for s in self.segments if s.kind == "speech")

    @property
    def speech_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.kind == "speech"]

    def slug(self) -> str:
        ascii_ = unicodedata.normalize("NFKD", self.title).encode("ascii", "ignore").decode()
        ascii_ = re.sub(r"[^A-Za-z0-9]+", "_", ascii_).strip("_")
        return f"{self.index:02d}_{ascii_[:60].rstrip('_') or 'kapitola'}"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def build_chapters(elements: list[Element], min_front_chars: int = 400) -> list[Chapter]:
    acronyms = collect_acronyms([e.text for e in elements if e.kind == "para"])
    chapters: list[Chapter] = []
    front = Chapter(index=0, title="Úvod", is_front=True)
    cur = front
    pending_num: int | None = None
    pending_part = ""

    for e in elements:
        if e.kind == "chapnum":
            pending_num = int(e.text)
        elif e.kind == "part":
            label = e.meta.get("label", "")
            title = sentence_case(e.text, acronyms)
            pending_part = f"{_cap(sentence_case(label, set()))}: {title}" if label else title
        elif e.kind == "chapter":
            cur = Chapter(index=0, title=e.text.strip(), number=pending_num, part=pending_part,
                          start_page=e.page, end_page=e.page)
            chapters.append(cur)
            pending_num, pending_part = None, ""
        elif e.kind == "subtitle":
            cur.subtitle = (cur.subtitle + " " + e.text).strip()
        elif e.kind == "sub":
            text = sentence_case(e.text, acronyms)
            # A heading wrapped over two lines arrives as two consecutive "sub" elements.
            if cur.blocks and cur.blocks[-1][0] == "sub" and not re.search(r"[.!?:]$", cur.blocks[-1][1]):
                cur.blocks[-1] = ("sub", cur.blocks[-1][1] + " " + text[:1].lower() + text[1:])
            else:
                cur.blocks.append(("sub", text))
            cur.end_page = e.page
        elif e.kind == "para":
            text = e.text
            if e.meta.get("bullet"):
                text = ensure_terminal(text)
            cur.blocks.append(("para", text))
            cur.end_page = e.page

    front_chars = sum(len(t) for _, t in front.blocks)
    if front_chars >= min_front_chars:
        chapters.insert(0, front)

    # A heading with no text under it (e.g. the book title on its title page).
    chapters = [c for c in chapters if c.blocks]
    _infer_missing_numbers(chapters)
    for i, ch in enumerate(chapters, 1):
        ch.index = i
        ch.blocks = [(k, normalize(t)) for k, t in ch.blocks]
        ch.segments = _segments(ch)
    return chapters


def _infer_missing_numbers(chapters: list[Chapter]) -> None:
    """Chapter 1 often has no number page; infer it from the next numbered chapter."""
    body = [c for c in chapters if not c.is_front]
    for i, ch in enumerate(body):
        if ch.number is None and i + 1 < len(body) and body[i + 1].number == i + 2:
            ch.number = i + 1


def announcement(ch: Chapter) -> str:
    title = ensure_terminal(ch.title)
    head = f"Kapitola {ordinal_f(ch.number)}. {title}" if ch.number else title
    if ch.subtitle:
        head += " " + ensure_terminal(ch.subtitle)
    return normalize(head)


def _segments(ch: Chapter) -> list[Segment]:
    segs: list[Segment] = []
    if ch.part:
        segs.append(Segment("speech", normalize(ensure_terminal(ch.part))))
        segs.append(Segment("pause", ms=PART_PAUSE_MS))
    segs.append(Segment("speech", announcement(ch)))
    segs.append(Segment("pause", ms=TITLE_PAUSE_MS))

    buf: list[str] = []

    def flush():
        if buf:
            segs.append(Segment("speech", "\n".join(buf)))
            buf.clear()

    def size():
        return sum(len(b) + 1 for b in buf)

    for kind, text in ch.blocks:
        if kind == "sub":
            flush()
            if segs[-1].kind != "pause":
                segs.append(Segment("pause", ms=SUB_PAUSE_MS))
            buf.append(ensure_terminal(text))
            continue
        if size() + len(text) <= MAX_CHARS:
            buf.append(text)
            continue
        # Paragraph does not fit: fill up sentence by sentence.
        sentences = [p for s in split_sentences(text) for p in split_long(s, MAX_CHARS)]
        line: list[str] = []
        for s in sentences:
            cand = " ".join(line + [s])
            if size() + len(cand) > MAX_CHARS:
                if line:
                    buf.append(" ".join(line))
                    line = []
                flush()
            line.append(s)
        if line:
            buf.append(" ".join(line))
    flush()
    return segs


def build_sample(chapters: list[Chapter], max_chars: int = 1550) -> list[Segment]:
    """First ~2 minutes of the book: title announcement + opening sentences."""
    ch = next((c for c in chapters if c.blocks), chapters[0])
    segs = [Segment("speech", announcement(ch)), Segment("pause", ms=TITLE_PAUSE_MS)]
    out, total = [], 0
    for kind, text in ch.blocks:
        for s in split_sentences(text if kind == "para" else ensure_terminal(text)):
            if total + len(s) > max_chars:
                break
            out.append(s)
            total += len(s) + 1
        else:
            continue
        break
    segs.append(Segment("speech", " ".join(out)))
    return segs
