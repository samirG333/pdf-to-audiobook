# 🎧 Audio converter

**Převede českou knihu v PDF na audioknihu, kterou si pustíš v telefonu.**

Stačí jedno PDF (textové, např. export z Wordu). Nástroj z něj vytáhne čistý text, rozpozná kapitoly, upraví text pro čtení nahlas a nechá ho přečíst neuronovým hlasem. Výsledkem je:

- 📚 **`kniha.m4b`**: jedna audiokniha s kapitolami, názvem, autorem a obálkou (Apple Books, BookPlayer, Smart AudioBook Player…),
- 🎵 **`mp3/01_nazev_kapitoly.mp3`, …**: každá kapitola zvlášť jako MP3.

> Příklad: kniha *Proč spíme* (337 stran) → 18 kapitol, 14 hodin audia, vygenerováno za ~35 minut.

---

## Jak to funguje

```
PDF ──► extrakce ──► čištění ──► kapitoly ──► hlas (TTS) ──► MP3 + M4B
```

| Krok | Co se děje |
|---|---|
| **Extrakce** | PyMuPDF čte text i s pozicí a velikostí písma. Zahodí záhlaví, zápatí, čísla stránek, poznámky pod čarou (i čísla odkazů jako `hodin.1`), popisky obrázků, obsah a konec knihy (*Poznámky, Zdroje, Rejstřík…*). Spojí řádky do odstavců a rozdělená slova. |
| **Čištění** | Upraví text pro čtení nahlas: `35 %` → *35 procent*, `18 °C` → *18 stupňů Celsia*, `např.` → *například*, `1–2` → *1 až 2*, `6.00` → *6 hodin*, nadpisy z VELKÝCH PÍSMEN na běžnou větu… |
| **Kapitoly** | Pozná nadpisy kapitol, částí a podnadpisů podle písma. Každá kapitola začne přečtením názvu („Kapitola druhá. Kofein, jet lag a melatonin.“) a pauzou. Text dělí na kousky do 3000 znaků, vždy na konci věty. |
| **Hlas** | [edge-tts](https://github.com/rany2/edge-tts), hlas `cs-CZ-VlastaNeural` (nebo `AntoninNeural`). Generuje víc kousků najednou, při chybě to zkusí znovu a po pádu pokračuje tam, kde skončil. |
| **Sestavení** | ffmpeg spojí kousky do MP3 kapitol a vytvoří `.m4b` se záložkami kapitol. |

---

## Instalace

Potřebuješ **Python 3.10+**, **ffmpeg** a připojení k internetu (hlas běží přes službu Microsoftu, bez registrace a API klíče).

```bash
# 1. ffmpeg
brew install ffmpeg                # macOS
# sudo apt install ffmpeg          # Linux
# winget install Gyan.FFmpeg       # Windows

# 2. projekt a závislosti
git clone https://github.com/samirG333/Audio-converter.git
cd Audio-converter
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Převod knihy krok za krokem

**1. Zkontroluj, co se bude číst**

```bash
python audiobook.py ~/Desktop/kniha.pdf --dry-run
```

Vypíše tabulku nalezených kapitol (strany, délka, odhad času) a uloží vyčištěný text do `out/kniha/kniha_clean.txt`. Projdi ho, je to přesně to, co hlas přečte.

**2. Poslechni si ukázku (~2 minuty)**

```bash
python audiobook.py ~/Desktop/kniha.pdf --sample
python audiobook.py ~/Desktop/kniha.pdf --sample --voice antonin   # mužský hlas
```

**3. Vygeneruj celou audioknihu**

```bash
python audiobook.py ~/Desktop/kniha.pdf
```

V terminálu uvidíš průběh a odhad zbývajícího času. Když se převod přeruší (výpadek sítě, Ctrl+C), **spusť stejný příkaz znovu**: hotové části se přeskočí.

**4. Hotovo**

```
out/kniha/
├── kniha.m4b      ← tohle pošli do telefonu (AirDrop, Google Drive…)
├── mp3/           ← kapitoly zvlášť, pro přehrávače bez podpory .m4b
└── work/          ← mezivýsledky, po dokončení můžeš smazat
```

---

## Volby

| Volba | Výchozí | Popis |
|---|---|---|
| `--voice` | `vlasta` | `vlasta`, `antonin` nebo jakýkoli hlas z `edge-tts --list-voices` |
| `--rate` | `+0%` | rychlost řeči, např. `-5%`, `+10%` |
| `--title`, `--author` | z PDF | název a autor v metadatech audioknihy |
| `--workers` | `4` | kolik kousků se generuje najednou |
| `--no-m4b` | – | jen MP3 kapitol |
| `--no-cover` | – | bez obálky (jinak se použije 1. strana PDF, pokud je to obrázek) |
| `-o, --out` | `out/<název>` | výstupní složka |

Všechny volby: `python audiobook.py --help`

---

## Pro vývojáře

```
audiobook/
├── extract.py    # PDF → odstavce a nadpisy (PyMuPDF)
├── clean.py      # normalizace češtiny pro TTS
├── chapters.py   # kapitoly a dělení na kousky
├── tts.py        # edge-tts: paralelně, retry, pokračování
├── assemble.py   # ffmpeg: MP3 kapitol a M4B
└── cli.py        # příkazová řádka a průběh
```

```bash
pip install -r requirements-dev.txt
pytest
```

Jiná kniha se chová divně? Zkontroluj `--dry-run` a uprav seznamy `BACK_MATTER_TITLES` (`extract.py`) nebo `ABBREVIATIONS` / `UNITS` (`clean.py`).

> ⚠️ Audioknihu vytvořenou z knihy chráněné autorským právem používej jen pro vlastní potřebu.
