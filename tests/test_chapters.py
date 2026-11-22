import re

from audiobook.chapters import MAX_CHARS, build_chapters
from audiobook.clean import ensure_terminal
from audiobook.extract import Element


def _book():
    sentence = "Toto je jedna docela obyčejná věta o spánku a jeho významu pro zdraví. "
    long_para = sentence * 120            # ~8 600 chars, must be split
    return [
        Element("chapnum", "2", 0),
        Element("chapter", "Kofein a melatonin", 1),
        Element("subtitle", "Jak to funguje", 1),
        Element("para", "Krátký úvodní odstavec.", 1),
        Element("sub", "MÁTE RYTMUS?", 2),
        Element("para", long_para.strip(), 2),
        Element("para", "Poslední odstavec kapitoly.", 3),
    ]


def test_chunks_are_bounded_and_end_on_sentence():
    ch = build_chapters(_book())[0]
    speech = ch.speech_segments
    assert speech[0].text == "Kapitola druhá. Kofein a melatonin. Jak to funguje."
    for seg in speech:
        assert len(seg.text) <= MAX_CHARS
        assert re.search(r"[.!?…]$", seg.text.strip()), seg.text[-40:]


def test_no_text_lost_or_duplicated():
    ch = build_chapters(_book())[0]
    spoken = " ".join(s.text for s in ch.speech_segments[1:])
    source = " ".join(t if k == "para" else ensure_terminal(t) for k, t in ch.blocks)
    assert re.sub(r"\s+", " ", spoken) == re.sub(r"\s+", " ", source)


def test_subheading_gets_pause_and_starts_new_chunk():
    ch = build_chapters(_book())[0]
    idx = next(i for i, s in enumerate(ch.segments) if s.text.startswith("Máte rytmus?"))
    assert ch.segments[idx - 1].kind == "pause"


def test_missing_first_chapter_number_is_inferred():
    els = [Element("chapter", "Úvodní kapitola", 0), Element("para", "Text.", 0),
           Element("chapnum", "2", 1), Element("chapter", "Druhá", 2), Element("para", "Text.", 2)]
    chs = build_chapters(els)
    assert [c.number for c in chs] == [1, 2]
