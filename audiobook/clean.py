"""Text normalization for Czech text-to-speech.

Everything here works on already-extracted prose: it expands abbreviations,
symbols and number notations into words that a TTS voice reads naturally.
"""
from __future__ import annotations

import re

UPPER = "A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
LOWER = "a-záčďéěíňóřšťúůýž"
WORD = f"[{UPPER}{LOWER}]"

ORDINALS_F = [
    "", "první", "druhá", "třetí", "čtvrtá", "pátá", "šestá", "sedmá", "osmá", "devátá",
    "desátá", "jedenáctá", "dvanáctá", "třináctá", "čtrnáctá", "patnáctá", "šestnáctá",
    "sedmnáctá", "osmnáctá", "devatenáctá", "dvacátá", "dvacátá první", "dvacátá druhá",
    "dvacátá třetí", "dvacátá čtvrtá", "dvacátá pátá", "dvacátá šestá", "dvacátá sedmá",
    "dvacátá osmá", "dvacátá devátá", "třicátá",
]


def ordinal_f(n: int) -> str:
    return ORDINALS_F[n] if 0 < n < len(ORDINALS_F) else f"{n}."


def plural(num: str, one: str, few: str, many: str) -> str:
    """Czech noun form after a number written in digits ("18,3" -> few/genitive sg)."""
    if "," in num or "." in num:
        return few
    n = int(num.replace(" ", ""))
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


UNITS = {
    "%": ("procento", "procenta", "procent"),
    "‰": ("promile", "promile", "promile"),
    "°C": ("stupeň Celsia", "stupně Celsia", "stupňů Celsia"),
    "°F": ("stupeň Fahrenheita", "stupně Fahrenheita", "stupňů Fahrenheita"),
    "°": ("stupeň", "stupně", "stupňů"),
    "km/h": ("kilometr za hodinu", "kilometry za hodinu", "kilometrů za hodinu"),
    "km": ("kilometr", "kilometry", "kilometrů"),
    "kg": ("kilogram", "kilogramy", "kilogramů"),
    "mg": ("miligram", "miligramy", "miligramů"),
    "µg": ("mikrogram", "mikrogramy", "mikrogramů"),
    "ml": ("mililitr", "mililitry", "mililitrů"),
    "cm": ("centimetr", "centimetry", "centimetrů"),
    "mm": ("milimetr", "milimetry", "milimetrů"),
    "Hz": ("hertz", "hertzy", "hertzů"),
    "kcal": ("kilokalorie", "kilokalorie", "kilokalorií"),
    "hod.": ("hodina", "hodiny", "hodin"),
    "min.": ("minuta", "minuty", "minut"),
    "sek.": ("sekunda", "sekundy", "sekund"),
    "mil.": ("milion", "miliony", "milionů"),
    "mld.": ("miliarda", "miliardy", "miliard"),
    "tis.": ("tisíc", "tisíce", "tisíc"),
    "Kč": ("koruna", "koruny", "korun"),
    "$": ("dolar", "dolary", "dolarů"),
    "€": ("euro", "eura", "eur"),
}
_NUM = r"\d+(?:,\d+)?"
_UNIT_RE = re.compile(
    rf"({_NUM})\s?(" + "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True)) + rf")(?![{LOWER}{UPPER}])"
)
_CURRENCY_PREFIX_RE = re.compile(rf"([$€])\s?({_NUM})(\s(?:mil\.|mld\.|milion\w*|miliard\w*))?")

# (pattern, replacement). Applied in order, case-sensitive, at word boundaries.
ABBREVIATIONS = [
    (r"př\. ?n\. ?l\.", "před naším letopočtem"),
    (r"n\. ?l\.", "našeho letopočtu"),
    (r"např\.", "například"), (r"Např\.", "Například"),
    (r"tj\.", "to jest"), (r"Tj\.", "To jest"),
    (r"tzn\.", "to znamená"), (r"Tzn\.", "To znamená"),
    (r"atd\.", "a tak dále"), (r"apod\.", "a podobně"),
    (r"aj\.", "a jiné"), (r"mj\.", "mimo jiné"), (r"Mj\.", "Mimo jiné"),
    (r"resp\.", "respektive"), (r"popř\.", "popřípadě"), (r"event\.", "eventuálně"),
    (r"vs\.", "versus"), (r"cca\.?", "cirka"), (r"zvl\.", "zvláště"),
    (r"Mr\.", "mister"), (r"Mrs\.", "misis"),
    (r"sv\.", "svatý"), (r"stol\.", "století"), (r"str\.", "strana"),
    (r"obr\.", "obrázek"), (r"Obr\.", "Obrázek"), (r"kap\.", "kapitola"),
    (r"[čČ]\.(?= ?\d)", "číslo"), (r"s\.(?= ?\d)", "strana"), (r"r\.(?= ?\d{4})", "roku"),
]
_ABBR_RE = [(re.compile(rf"(?<![{LOWER}{UPPER}\.]){p}(?![{LOWER}{UPPER}])"), r) for p, r in ABBREVIATIONS]

# Expansions that may legitimately end a sentence ("... atd. Pak") keep the full stop.
SENTENCE_FINAL = {"a tak dále", "a podobně", "a jiné", "našeho letopočtu",
                  "před naším letopočtem", "století", "respektive"}

# Acronyms that read better spelled out or expanded.
ACRONYMS = {
    "NREM": "non-REM",
}


def _thousands(m: re.Match) -> str:
    return m.group(0).replace(" ", "").replace(" ", "")


def _unit(m: re.Match) -> str:
    num, unit = m.group(1), m.group(2)
    return f"{num} {plural(num, *UNITS[unit])}"


def _currency_prefix(m: re.Match) -> str:
    sym, num, mult = m.group(1), m.group(2), (m.group(3) or "")
    if mult:  # "$ 3 mil." -> "3 milionů dolarů"
        return f"{num}{mult} {UNITS[sym][2]}"
    return f"{num} {plural(num, *UNITS[sym])}"


def _time(m: re.Match) -> str:
    h, mm = int(m.group(2)), int(m.group(3))
    hours = f"{h} {plural(str(h), 'hodina', 'hodiny', 'hodin')}" if h else "0 hodin"
    if mm == 0:
        return f"{m.group(1)}{hours}"
    return f"{m.group(1)}{hours} {mm} {plural(str(mm), 'minuta', 'minuty', 'minut')}"


_TZV_ENDINGS = [  # adjective ending of the following word -> form of "takzvaný"
    ("ými", "takzvanými"), ("ími", "takzvanými"), ("ého", "takzvaného"), ("ího", "takzvaného"),
    ("ému", "takzvanému"), ("ímu", "takzvanému"), ("ých", "takzvaných"), ("ích", "takzvaných"),
    ("ým", "takzvaným"), ("ím", "takzvaným"), ("ou", "takzvanou"), ("ý", "takzvaný"),
    ("á", "takzvaná"), ("é", "takzvané"),
]


def _tzv(m: re.Match) -> str:
    nxt = m.group(2)
    word = re.sub(rf"[^{LOWER}{UPPER}]", "", nxt).lower()
    form = next((f for end, f in _TZV_ENDINGS if word.endswith(end)), "takzvaný")
    if m.group(1) == "T":
        form = form.capitalize()
    return f"{form} {nxt}"


def _title(m: re.Match) -> str:
    """'Dr. Ullricha Wagnera' -> 'doktora Ullricha Wagnera' (case from the name endings)."""
    base = "profesor" if m.group(1).lower() == "prof" else "doktor"
    if m.group(1) == "Prof":
        base = "Profesor"
    names = [n for n in (m.group(2), m.group(3)) if n]
    suffix = ""
    if len(names) == 2:
        for end, suf in (("ovi", "ovi"), ("em", "em"), ("a", "a")):
            if all(n.endswith(end) for n in names):
                suffix = suf
                break
    return " ".join([base + suffix, *names])


def normalize(text: str) -> str:
    t = text
    t = t.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    t = t.replace("", "").replace("\t", " ")
    t = re.sub(r"(?:https?://|www\.)\S+?(?=[.,;:!?)\]]*(?:\s|$))", "", t)
    t = re.sub(r"\.{3,}|…", "…", t)

    # Censored swear words ("F**k") would be read as letters and asterisks.
    t = re.sub(rf"{WORD}*\*{{2,}}{WORD}*", "píp", t)

    # Numbers: "1 358" -> "1358", "3 400 000" -> "3400000".
    t = re.sub(r"(?<![\d,])\d{1,3}(?:[  ]\d{3})+(?![\d,])", _thousands, t)
    # Clock times "6.00", "5.58" after a preposition.
    t = re.sub(r"(\b(?:v|ve|na|do|od|po|před|kolem|okolo|mezi|až|asi|času|a|zhruba|o)\s)([01]?\d|2[0-3])[.:]([0-5]\d)\b", _time, t)

    t = re.sub(r"\+\s?/\s?[-–]|±", "plus minus", t)
    t = _CURRENCY_PREFIX_RE.sub(_currency_prefix, t)
    t = _UNIT_RE.sub(_unit, t)
    t = re.sub(r"(\d)\s?x\s?(\d)", r"\1 krát \2", t)
    t = t.replace("×", " krát ")
    t = re.sub(r"\s*&\s*", " a ", t)
    t = re.sub(r"§\s?(\d)", r"paragraf \1", t)
    t = re.sub(r"\s>\s", " větší než ", t)
    t = re.sub(r"\s<\s", " menší než ", t)
    t = re.sub(r"\s=\s", " rovná se ", t)

    # Digit sequences "4–1–3–2–4" -> "4, 1, 3, 2, 4"; ranges "35–100" -> "35 až 100".
    t = re.sub(r"\d+(?:\s?[–-]\s?\d+){2,}", lambda m: ", ".join(re.split(r"\s?[–-]\s?", m.group(0))), t)
    t = re.sub(rf"({_NUM})\s?[–-]\s?({_NUM})(?![\d-])", r"\1 až \2", t)

    # Slashes between words.
    t = re.sub(r"\ba\s?/\s?nebo\b", "a nebo", t)
    t = re.sub(r",\s?/\s?", ", ", t)
    t = re.sub(rf"({WORD})\s?/\s?({WORD})", r"\1 nebo \2", t)

    t = re.sub(r"([Tt])zv\.\s+(\S+)", _tzv, t)
    t = re.sub(rf"\b(MUDr|PhDr|RNDr|Dr|dr|Prof|prof)\.\s+({WORD}+)(?:\s+({WORD}+))?", _title, t)
    for rx, rep in _ABBR_RE:
        mark = _ABBR_END if rep in SENTENCE_FINAL else ""
        t = rx.sub(lambda m, rep=rep, mark=mark: rep + mark, t)
    # An expanded abbreviation that ended the sentence must keep its full stop.
    t = re.sub(rf"{_ABBR_END}(?=\s*$|\s+[„\"({UPPER}])", ".", t)
    t = t.replace(_ABBR_END, "")

    for a, rep in ACRONYMS.items():
        t = re.sub(rf"\b{a}\b", rep, t)

    t = re.sub(rf"({WORD})- (li|nebo)\b", r"\1-\2", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    t = re.sub(r"[ ]{2,}", " ", t)
    return t.strip()


_ABBR_END = "⁣"  # invisible marker used during abbreviation expansion


def ensure_terminal(text: str) -> str:
    text = text.rstrip()
    if not text:
        return text
    if text[-1] in ".!?…:;\"“”»)":
        return text if text[-1] not in ":;" else text[:-1] + "."
    return text + "."


def sentence_case(heading: str, acronyms: set[str]) -> str:
    """'SPÁNEK A ADOLESCENCE' -> 'Spánek a adolescence', keeping known acronyms."""
    if not heading.isupper():
        return heading
    words = re.split(r"(\s+)", heading.lower())
    out = []
    for w in words:
        core = re.sub(rf"[^{LOWER}{UPPER}\d-]", "", w)
        if core.upper() in acronyms:
            w = w.replace(core, core.upper())
        out.append(w)
    s = "".join(out)
    return s[:1].upper() + s[1:]


def collect_acronyms(paragraphs: list[str]) -> set[str]:
    found = re.findall(rf"(?<![{LOWER}{UPPER}])[{UPPER}]{{2,6}}(?![{LOWER}{UPPER}])", " ".join(paragraphs))
    return {a for a in set(found)}


# --- sentence splitting ------------------------------------------------------

_SENT_END = re.compile(rf"(?<=[.!?…])[\"“”»)]*\s+(?=[„\"«(]?[{UPPER}\d])")


def split_sentences(text: str) -> list[str]:
    parts, start = [], 0
    for m in _SENT_END.finditer(text):
        end = m.start()
        # Do not split after a single capital initial ("T. H. Chan") or an ordinal ("2. Typu" is rare).
        before = text[max(0, end - 3):end]
        if re.search(rf"(?:^|\s)[{UPPER}]\.$", before):
            continue
        parts.append(text[start:m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def split_long(sentence: str, limit: int) -> list[str]:
    """Split an overlong sentence at ; : , or spaces as a last resort."""
    if len(sentence) <= limit:
        return [sentence]
    for sep in ("; ", ": ", " – ", ", ", " "):
        pieces = sentence.split(sep)
        if len(pieces) == 1:
            continue
        out, cur = [], ""
        for i, p in enumerate(pieces):
            add = p + (sep.rstrip() if i < len(pieces) - 1 else "")
            if cur and len(cur) + 1 + len(add) > limit:
                out.append(cur)
                cur = add
            else:
                cur = f"{cur} {add}".strip() if cur else add
        if cur:
            out.append(cur)
        if all(len(o) <= limit for o in out):
            return out
    return [sentence[i:i + limit] for i in range(0, len(sentence), limit)]
