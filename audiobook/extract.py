"""Layout-aware text extraction from PDF using PyMuPDF.

The extractor classifies every text line by font size, weight and position
relative to the dominant body font, and emits a flat stream of structural
elements (parts, chapters, sub-headings, paragraphs). Running headers/footers,
page numbers, footnote reference marks, footnote bodies and figure captions are
dropped here, so the cleaning stage only has to deal with prose.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

# Section titles that mark the start of back matter (everything after is skipped).
BACK_MATTER_TITLES = (
    "poznámky", "poznámky pod čarou", "vysvětlivky", "zdroje", "zdroje ilustrací",
    "seznam zdrojů", "seznam literatury", "literatura", "použitá literatura",
    "bibliografie", "rejstřík", "jmenný rejstřík", "věcný rejstřík", "poděkování",
    "o autorovi", "ediční poznámka", "tiráž",
)
TOC_TITLES = {"obsah", "obsah knihy"}


def _fold(text: str) -> str:
    """Lowercase, strip accents and punctuation: 'Poznámky:' -> 'poznamky'."""
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]+", "", t).strip()


_BACK_MATTER = {_fold(t) for t in BACK_MATTER_TITLES}

BULLET_RE = re.compile(r"\s*[•▪◦‣⁃●]\s*")

MARGIN_RATIO = 0.08         # top/bottom band treated as header/footer zone
REPEAT_RATIO = 0.25          # a margin line repeated on >= 25 % pages is furniture


@dataclass
class Element:
    kind: str                # part | chapter | subtitle | sub | para | chapnum
    text: str
    page: int
    meta: dict = field(default_factory=dict)


@dataclass
class Line:
    text: str
    size: float
    bold: bool
    italic: bool
    x0: float
    y0: float
    y1: float
    page: int


def _norm_key(text: str) -> str:
    return re.sub(r"\d+", "#", text.strip().lower())


def _is_super(span: dict, body: float) -> bool:
    return bool(span["flags"] & 1) or span["size"] < body * 0.62


def _span_text(span: dict) -> str:
    return unicodedata.normalize("NFKC", span["text"]).replace("­", "")


def _collect_lines(doc: pymupdf.Document) -> tuple[list[Line], float]:
    sizes: Counter = Counter()
    raw_pages = []
    for page in doc:
        data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        raw_pages.append((page, data))
        for b in data["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s["text"].strip():
                        sizes[round(s["size"], 1)] += len(s["text"])
    body = sizes.most_common(1)[0][0] if sizes else 12.0

    lines: list[Line] = []
    for pno, (page, data) in enumerate(raw_pages):
        for b in data["blocks"]:
            if b.get("type", 0) != 0:
                continue
            for l in b["lines"]:
                spans = [s for s in l["spans"] if s["text"]]
                # Footnote reference marks: superscript / tiny digits glued to words.
                kept = [s for s in spans if not (_is_super(s, body) and re.fullmatch(r"[\d\s*,†‡–-]+", s["text"]))]
                text = "".join(_span_text(s) for s in kept)
                visible = [s for s in kept if s["text"].strip()]
                if not visible:
                    if not text.strip():
                        lines.append(Line("", body, False, False, l["bbox"][0], l["bbox"][1], l["bbox"][3], pno))
                    continue
                main = max(visible, key=lambda s: len(s["text"].strip()))
                lines.append(Line(
                    text=text,
                    size=round(main["size"], 1),
                    bold=all("bold" in s["font"].lower() or s["flags"] & 16 for s in visible),
                    italic=all("italic" in s["font"].lower() or s["flags"] & 2 for s in visible),
                    x0=min(s["bbox"][0] for s in visible),
                    y0=l["bbox"][1],
                    y1=l["bbox"][3],
                    page=pno,
                ))
    return _merge_visual_lines(lines), body


def _merge_visual_lines(lines: list[Line]) -> list[Line]:
    """Justified text is sometimes split into one fragment per word; glue
    fragments that share a baseline back into a single visual line."""
    merged: list[Line] = []
    for ln in lines:
        prev = merged[-1] if merged else None
        if (prev and ln.text.strip() and prev.text.strip() and prev.page == ln.page
                and abs(prev.y0 - ln.y0) < 2 and ln.x0 > prev.x0):
            sep = "" if prev.text.endswith((" ", "\t")) or ln.text.startswith(" ") else " "
            prev.text += sep + ln.text
            prev.bold = prev.bold and ln.bold
            prev.italic = prev.italic and ln.italic
            prev.y1 = max(prev.y1, ln.y1)
            continue
        if prev and not ln.text.strip() and prev.page == ln.page and abs(prev.y0 - ln.y0) < 2:
            continue  # whitespace fragment on the same line, not a blank line
        merged.append(ln)
    return merged


def _furniture_keys(lines: list[Line], doc: pymupdf.Document) -> set[str]:
    """Normalized texts of lines that repeat in the header/footer bands."""
    counts: Counter = Counter()
    for ln in lines:
        if not ln.text.strip():
            continue
        h = doc[ln.page].rect.height
        if ln.y1 < h * MARGIN_RATIO or ln.y0 > h * (1 - MARGIN_RATIO):
            counts[(_norm_key(ln.text))] += 1
    threshold = max(3, int(len(doc) * REPEAT_RATIO))
    return {k for k, c in counts.items() if c >= threshold}


def extract(pdf_path: str) -> tuple[list[Element], dict]:
    doc = pymupdf.open(pdf_path)
    lines, body = _collect_lines(doc)
    vocab = build_vocabulary([l.text for l in lines])
    furniture = _furniture_keys(lines, doc)
    left = Counter(round(l.x0) for l in lines if l.text.strip() and abs(l.size - body) < 0.5).most_common(1)[0][0]

    elements: list[Element] = []
    para: list[str] = []
    para_page = 0

    def flush():
        nonlocal para
        if para:
            text = join_lines(para, vocab).strip()
            is_bullet = text.startswith("• ")
            text = text.removeprefix("• ").strip()
            if text:
                elements.append(Element("para", text, para_page, {"bullet": True} if is_bullet else {}))
            para = []

    i = 0
    stop_page = None
    in_toc = False
    while i < len(lines):
        ln = lines[i]
        page_h = doc[ln.page].rect.height
        txt = ln.text.strip()

        if not txt:
            flush()
            i += 1
            continue

        in_margin = ln.y1 < page_h * MARGIN_RATIO or ln.y0 > page_h * (1 - MARGIN_RATIO)
        if in_margin and (_norm_key(txt) in furniture or re.fullmatch(r"[-–—\s]*\d{1,4}[-–—\s]*", txt)):
            i += 1
            continue

        rel = ln.size / body
        if in_toc and rel < 1.7:
            i += 1
            continue
        # Big headings (chapter / part titles), possibly wrapped over several lines.
        if rel >= 1.7:
            flush()
            parts = [txt]
            j = i + 1
            while j < len(lines) and lines[j].page == ln.page and lines[j].text.strip() \
                    and lines[j].size / body >= 1.7 and lines[j].bold == ln.bold \
                    and lines[j].y0 - lines[j - 1].y1 < ln.size:
                parts.append(lines[j].text.strip())
                j += 1
            title = " ".join(parts)
            if _fold(title) in _BACK_MATTER and elements:
                stop_page = ln.page
                break
            if _fold(title) in TOC_TITLES:
                in_toc = True      # table of contents: skip until the next big heading
                i = j
                continue
            in_toc = False
            # A part title stands alone on its page (no body text below it) and is
            # either set in capitals or introduced by "ČÁST DRUHÁ".
            label_m = None
            if elements and elements[-1].kind == "para":
                label_m = re.search(r"(?:^|\s)((?:ČÁST|DÍL)\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]+)\s*$", elements[-1].text)
            alone = not any(l.page == ln.page and l.text.strip() and abs(l.size - body) < 0.5
                            for l in lines[j:j + 60])
            kind = "part" if alone and (title.isupper() or label_m) else "chapter"
            if kind == "part" and ln.page == 0 and not label_m:
                i = j          # big lettering on the title page, not a part of the book
                continue
            label = ""
            if kind == "part":
                m = label_m
                if m:
                    label = m.group(1)
                    rest = elements[-1].text[:m.start()].strip()
                    if rest:
                        elements[-1].text = rest
                    else:
                        elements.pop()
            elements.append(Element(kind, title, ln.page, {"label": label} if label else {}))
            i = j
            continue

        # Stand-alone chapter number above the title ("2", "11 ").
        if rel >= 1.2 and re.fullmatch(r"\d{1,3}", txt):
            flush()
            elements.append(Element("chapnum", txt, ln.page))
            i += 1
            continue

        # Medium headings: italic right after a chapter title = subtitle, bold = sub-heading.
        if 1.05 <= rel < 1.7:
            flush()
            if ln.italic and elements and elements[-1].kind in ("chapter", "subtitle"):
                if elements[-1].kind == "subtitle":
                    elements[-1].text += " " + txt
                else:
                    elements.append(Element("subtitle", txt, ln.page))
            else:
                elements.append(Element("sub", txt, ln.page))
            i += 1
            continue

        # Small text: captions, footnote bodies, tiny stray glyphs. They do not end
        # the running paragraph, which may continue on the next page.
        if rel < 0.9:
            i += 1
            continue

        # Body text. Indented first line starts a new paragraph.
        bullet = BULLET_RE.match(ln.text)
        if bullet:
            flush()
            ln.text = ln.text[bullet.end():]
        elif ln.x0 > left + 8 and para and not para[-1].rstrip().endswith("-") \
                and not BULLET_RE.match(para[0]):
            flush()
        if bullet:
            ln.text = "• " + ln.text  # marker kept until the paragraph is built
        if not para:
            para_page = ln.page
        para.append(ln.text)
        i += 1
    flush()

    info = {
        "body_size": body,
        "pages": len(doc),
        "stop_page": stop_page,
        "metadata": doc.metadata or {},
    }
    return elements, info


_HYPHEN_END = re.compile(r"(\w)[-‐]\s*$")


_WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")


def build_vocabulary(texts: list[str]) -> set[str]:
    return {w.lower() for t in texts for w in _WORD_RE.findall(t)}


def _keep_hyphen(prefix_line: str, next_line: str, vocab: set[str]) -> bool:
    """Decide whether a hyphen at the end of a line is a real hyphen ("e-mail",
    "Porovnáte-li") or an automatic word break ("spán-kem")."""
    head = re.search(r"([^\W\d_]+)[-\u2010]\s*$", prefix_line)
    tail = re.match(r"([^\W\d_]+)", next_line)
    if not head or not tail:
        return True
    a, b = head.group(1).lower(), tail.group(1).lower()
    if b in ("li", "nebo", "že") or not next_line[:1].islower():
        return True
    if f"{a}-{b}" in vocab:
        return True
    if a + b in vocab:
        return False
    return len(a) <= 2  # unknown word: short prefixes (e-, x-) are real hyphens


def join_lines(lines: list[str], vocab: set[str] | None = None) -> str:
    """Merge wrapped lines into one paragraph, healing end-of-line hyphenation."""
    vocab = vocab or set()
    out = ""
    for raw in lines:
        line = raw.replace("\u00a0", " ")
        if not out:
            out = line.lstrip()
            continue
        nxt = line.lstrip()
        if _HYPHEN_END.search(out):
            if _keep_hyphen(out, nxt, vocab):
                out = out.rstrip() + nxt
            else:
                out = out.rstrip()[:-1] + nxt
        elif out.endswith((" ", "\t")):
            out += nxt
        else:
            out += " " + nxt
    return re.sub(r"[ \t]+", " ", out)


def render_cover(pdf_path: str, out_png: str, width: int = 1000) -> bool:
    """Render the first page as cover art (only if it is mostly an image)."""
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    if len(page.get_text().strip()) > 200:
        return False
    zoom = width / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    pix.save(out_png)
    return True
