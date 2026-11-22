import pytest

from audiobook.clean import (
    ensure_terminal, normalize, sentence_case, split_long, split_sentences,
)


@pytest.mark.parametrize("src, expected", [
    ("asi 35 % lidí", "asi 35 procent lidí"),
    ("jen 1 % a 3 % a 2,5 %", "jen 1 procento a 3 procenta a 2,5 procenta"),
    ("teplota 18,3 °C a 5 °F", "teplota 18,3 stupně Celsia a 5 stupňů Fahrenheita"),
    ("(+/– 3 °C)", "(plus minus 3 stupně Celsia)"),
    ("Spí atd. Pak", "Spí a tak dále. Pak"),
    ("např. Google a tj. firma", "například Google a to jest firma"),
    ("tzv. rezidenčních programů", "takzvaných rezidenčních programů"),
    ("tzv. jet lag", "takzvaný jet lag"),
    ("prášky vs. terapie", "prášky versus terapie"),
    ("(35–100 n. l.). Napsal", "(35 až 100 našeho letopočtu). Napsal"),
    ("řada 4–1–3–2", "řada 4, 1, 3, 2"),
    ("rychlostí 1 358 km/h", "rychlostí 1358 kilometrů za hodinu"),
    ("budík na 6.00 a v 5.58", "budík na 6 hodin a v 5 hodin 58 minut"),
    ("A > B", "A větší než B"),
    ("kořisti/predátora a/nebo X", "kořisti nebo predátora a nebo X"),
    ("Porovnáte- li hloubku", "Porovnáte-li hloubku"),
    ("viz https://example.com/a. Konec", "viz. Konec"),
    ("Go the F**k to Sleep", "Go the píp to Sleep"),
    ("Příklad č. 1", "Příklad číslo 1"),
    ("stojí $3 mil.", "stojí 3 miliony dolarů"),
    ("fáze NREM spánku", "fáze non-REM spánku"),
    ("Drsný & krutý", "Drsný a krutý"),
    ("studie dr. Ullricha Wagnera", "studie doktora Ullricha Wagnera"),
    ("poukázal Dr. Daniel Kripke,", "poukázal doktor Daniel Kripke,"),
])
def test_normalize(src, expected):
    assert normalize(src) == expected


def test_sentence_split_respects_abbreviations_and_initials():
    text = "Tým ze T. H. Chan School to zjistil. Diabetes 2. typu je vážný. Ano!"
    assert split_sentences(text) == [
        "Tým ze T. H. Chan School to zjistil.", "Diabetes 2. typu je vážný.", "Ano!"]


def test_split_long_keeps_limit():
    sentence = ", ".join(["slovo"] * 400) + "."
    parts = split_long(sentence, 300)
    assert all(len(p) <= 300 for p in parts)
    assert " ".join(parts).replace(" ", "") == sentence.replace(" ", "")


def test_sentence_case_keeps_acronyms():
    assert sentence_case("SPÁNEK A REM FÁZE", {"REM"}) == "Spánek a REM fáze"
    assert sentence_case("Už normální", set()) == "Už normální"


def test_ensure_terminal():
    assert ensure_terminal("Nadpis") == "Nadpis."
    assert ensure_terminal("Otázka?") == "Otázka?"
    assert ensure_terminal("Dvojtečka:") == "Dvojtečka."
