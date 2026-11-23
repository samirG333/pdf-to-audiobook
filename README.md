# 🎧 pdf-to-audiobook

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Language](https://img.shields.io/badge/language-Czech%20only-red)
![TTS](https://img.shields.io/badge/TTS-edge--tts-informational)

**Turns a Czech book in PDF into a chaptered audiobook you can listen to on your phone.**

Point it at a text-based PDF (e.g. exported from Word). It extracts clean text, detects chapters, prepares the text for reading aloud and has it narrated by a Czech neural voice. You get:

- 📚 **`book.m4b`**: one audiobook file with chapters, title, author and cover art (Apple Books, BookPlayer, Smart AudioBook Player…)
- 🎵 **`mp3/01_chapter_name.mp3`, …**: every chapter as a separate MP3

> **Real-world run:** *Proč spíme* (337 pages) → 18 chapters, 14 hours of audio, generated in ~35 minutes.

> [!IMPORTANT]
> **Czech books only.** Text normalization (numbers, units, abbreviations, grammatical agreement), chapter announcements (“Kapitola druhá…”) and the default voices are built for Czech. Other languages would be read with Czech rules and pronunciation.

---

## How it works

```
PDF ──► extraction ──► cleanup ──► chapters ──► voice (TTS) ──► MP3 + M4B
```

| Step | What happens |
|---|---|
| **Extraction** | PyMuPDF reads each line with its position and font. Running headers, footers, page numbers, footnotes (including reference marks like `hodin.1`), figure captions, the table of contents and back matter (*Poznámky, Zdroje, Rejstřík…*) are dropped. Lines are merged into paragraphs and hyphenated words rejoined. |
| **Cleanup** | Text is normalized for Czech speech: `35 %` → *35 procent*, `18 °C` → *18 stupňů Celsia*, `např.` → *například*, `1–2` → *1 až 2*, `6.00` → *6 hodin*, ALL-CAPS headings → sentence case… |
| **Chapters** | Chapter, part and sub-heading titles are detected from font size and weight. Each chapter opens with its spoken title followed by a pause. Text is split into chunks of up to 3000 characters, always at a sentence boundary. |
| **Voice** | [edge-tts](https://github.com/rany2/edge-tts) with `cs-CZ-VlastaNeural` (female) or `cs-CZ-AntoninNeural` (male). Chunks are generated in parallel, failures are retried with backoff and an interrupted run resumes where it stopped. |
| **Assembly** | ffmpeg joins the chunks into chapter MP3s and builds an `.m4b` with chapter markers and metadata. |

---

## Installation

Requires **Python 3.10+**, **ffmpeg** and an internet connection (the voice runs on Microsoft's Edge TTS service, no account or API key needed).

```bash
# 1. ffmpeg
brew install ffmpeg                # macOS
# sudo apt install ffmpeg          # Linux
# winget install Gyan.FFmpeg       # Windows

# 2. project and dependencies
git clone https://github.com/samirG333/pdf-to-audiobook.git
cd pdf-to-audiobook
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Converting a book step by step

**1. Check what will be read**

```bash
python audiobook.py ~/Desktop/book.pdf --dry-run
```

Prints a table of detected chapters (pages, length, estimated duration) and saves the cleaned text to `out/book/book_clean.txt`, exactly what the voice will read.

**2. Listen to a sample (~2 minutes)**

```bash
python audiobook.py ~/Desktop/book.pdf --sample
python audiobook.py ~/Desktop/book.pdf --sample --voice antonin   # male voice
```

**3. Generate the whole audiobook**

```bash
python audiobook.py ~/Desktop/book.pdf
```

The terminal shows progress and the estimated time left. If the run is interrupted (network outage, Ctrl+C), **run the same command again**: finished parts are skipped.

**4. Done**

```
out/book/
├── book.m4b       ← send this to your phone (AirDrop, iCloud Drive…)
├── mp3/           ← separate chapters for players without .m4b support
└── work/          ← intermediate files, safe to delete when finished
```

---

## Options

| Option | Default | Description |
|---|---|---|
| `--voice` | `vlasta` | `vlasta`, `antonin` or any Czech voice from `edge-tts --list-voices` |
| `--rate` | `+0%` | speaking rate, e.g. `-5%`, `+10%` |
| `--title`, `--author` | from PDF | audiobook title and author metadata |
| `--workers` | `4` | number of chunks generated in parallel |
| `--no-m4b` | – | chapter MP3s only |
| `--no-cover` | – | no cover art (otherwise the first PDF page is used if it is an image) |
| `-o, --out` | `out/<name>` | output folder |

All options: `python audiobook.py --help`

---

## Limitations

- **Text-based PDFs only.** Scanned books need OCR first.
- Chapter detection relies on headings being set in a larger or bold font, which is typical for Word exports.
- Pronunciation is up to the TTS voice; rare names and foreign words may sound off.

---

## Project structure

```
audiobook/
├── extract.py    # PDF → paragraphs and headings (PyMuPDF)
├── clean.py      # Czech text normalization for TTS
├── chapters.py   # chapters and chunking
├── tts.py        # edge-tts: parallel, retries, resume
├── assemble.py   # ffmpeg: chapter MP3s and M4B
└── cli.py        # command line and progress
tests/            # pytest suite, incl. a synthetic PDF with headers, footnotes and back matter
```

```bash
pip install -r requirements-dev.txt
pytest
```

A book behaves oddly? Check the `--dry-run` output and adjust `BACK_MATTER_TITLES` (`extract.py`) or `ABBREVIATIONS` / `UNITS` (`clean.py`).

> ⚠️ Use audiobooks made from copyrighted books for personal use only.
