"""Extraction tests on a synthetic PDF with running headers, page numbers,
footnotes, superscript reference marks, hyphenation and back matter."""
from pathlib import Path

import pymupdf
import pytest

from audiobook.chapters import build_chapters
from audiobook.extract import extract

BODY = 11
LEFT = 72


def _page(doc, header=True, number=None):
    page = doc.new_page(width=595, height=842)
    if header:
        page.insert_text((LEFT, 30), "Kniha o spanku", fontsize=9, fontname="helv")
    if number is not None:
        page.insert_text((290, 815), str(number), fontsize=9, fontname="helv")
    return page


def _body(page, y, text, x=LEFT):
    page.insert_text((x, y), text, fontsize=BODY, fontname="tiro")
    return y + 15


@pytest.fixture(scope="module")
def pdf(tmp_path_factory) -> Path:
    doc = pymupdf.open()

    p = doc.new_page(width=595, height=842)
    p.insert_text((LEFT, 120), "Obsah", fontsize=24, fontname="hebo")
    _body(p, 170, "Prvni kapitola .......... 1")

    p = _page(doc, number=1)
    p.insert_text((LEFT, 120), "Prvni kapitola", fontsize=24, fontname="hebo")
    y = 170
    y = _body(p, y, "Lide v rozvinutych zemich nespi doporucenych osm hodin.", x=LEFT + 18)
    # superscript footnote reference glued to the word
    p.insert_text((LEFT + 300, y - 19), "1", fontsize=6, fontname="tiro")
    y = _body(p, y, "To vas jiste neprekvapuje. Dlouhe slovo se rozdeli na konci radku spán-")
    y = _body(p, y, "kem a pokracuje dal. Druhy radek odstavce konci tady.")
    y = _body(p, y, "Novy odstavec zacina odsazenim a ma dve vety. Tohle je ta druha.", x=LEFT + 18)
    p.insert_text((LEFT, 760), "1 Toto je poznamka pod carou, ktera se nema cist.", fontsize=8, fontname="tiro")

    p = _page(doc, number=2)
    y = _body(p, 80, "Pokracovani odstavce na dalsi strance bez odsazeni.")
    p.insert_text((LEFT, 140), "PODNADPIS V KAPITOLE", fontsize=13, fontname="hebo")
    y = _body(p, 170, "Text pod podnadpisem obsahuje 35 % lidi a e-", x=LEFT + 18)
    y = _body(p, y, "mail se nesmi spojit.")

    p = _page(doc, number=3)
    p.insert_text((LEFT, 120), "Druha kapitola", fontsize=24, fontname="hebo")
    _body(p, 170, "Text druhe kapitoly je kratky.", x=LEFT + 18)

    p = _page(doc, number=4)
    p.insert_text((LEFT, 120), "Poznamky", fontsize=24, fontname="hebo")
    _body(p, 170, "1 Zdroj: Nekdo, nejaka kniha, 2017.")

    path = tmp_path_factory.mktemp("pdf") / "kniha.pdf"
    doc.save(path)
    return path


def _paras(elements):
    return [e.text for e in elements if e.kind == "para"]


def test_headers_page_numbers_and_footnotes_removed(pdf):
    els, _ = extract(str(pdf))
    text = " ".join(e.text for e in els)
    assert "Kniha o spanku" not in text
    assert "poznamka pod carou" not in text
    for n in ("1", "2", "3", "4"):
        assert n not in text.split()


def test_footnote_reference_removed(pdf):
    els, _ = extract(str(pdf))
    first = _paras(els)[0]
    assert first.startswith("Lide v rozvinutych zemich nespi doporucenych osm hodin. To vas")
    assert "hodin.1" not in first


def test_paragraphs_and_hyphenation(pdf):
    paras = _paras(extract(str(pdf))[0])
    assert "spánkem a pokracuje" in paras[0]
    assert paras[1].startswith("Novy odstavec")
    # paragraph continues across the page break
    assert paras[1].endswith("Pokracovani odstavce na dalsi strance bez odsazeni.")
    assert "e-mail se nesmi spojit" in paras[2]


def test_chapters_headings_and_back_matter(pdf):
    els, info = extract(str(pdf))
    kinds = [(e.kind, e.text) for e in els if e.kind != "para"]
    assert kinds == [("chapter", "Prvni kapitola"), ("sub", "PODNADPIS V KAPITOLE"),
                     ("chapter", "Druha kapitola")]
    assert info["stop_page"] == 4
    text = " ".join(e.text for e in els)
    assert "Zdroj" not in text and "Obsah" not in text and "....." not in text  # TOC + back matter skipped

    chapters = build_chapters(els)
    assert [c.title for c in chapters] == ["Prvni kapitola", "Druha kapitola"]
    assert chapters[0].segments[0].text == "Prvni kapitola."
    assert chapters[0].segments[1].kind == "pause"
    body = " ".join(s.text for s in chapters[0].speech_segments)
    assert "Podnadpis v kapitole." in body
    assert "35 procent lidi" in body
