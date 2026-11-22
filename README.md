# Audio converter – PDF → audiokniha

Převede českou knihu v PDF (textové PDF, např. export z Wordu) na audioknihu:

- **MP3 pro každou kapitolu** (`01_Nazev_kapitoly.mp3`, …) s ID3 tagy,
- **jeden `.m4b`** s kapitolami (záložkami), názvem, autorem a obálkou – otevře se jako audiokniha v telefonu (Apple Books, Smart AudioBook Player, BookPlayer, …).

Hlas: Microsoft Edge neural TTS (`edge-tts`), výchozí **cs-CZ-VlastaNeural**, volitelně **cs-CZ-AntoninNeural**.

## Co nástroj dělá

1. **Extrakce s ohledem na layout** (PyMuPDF): každý řádek se klasifikuje podle velikosti, tučnosti a pozice písma vůči základnímu písmu textu.
   - zahodí záhlaví, zápatí a čísla stránek (opakující se řádky v horním/dolním okraji),
   - odstraní čísla poznámek pod čarou (horní indexy, `hodin.1` → `hodin.`),
   - vynechá poznámky pod čarou, popisky obrázků a vše od sekcí typu *Poznámky*, *Zdroje*, *Literatura*, *Rejstřík*, *Poděkování* na konci knihy,
   - spojí slova rozdělená na konci řádku, sloučí řádky do odstavců, opraví řádky zarovnaného textu rozsekané po slovech.
2. **Kapitoly** podle nadpisů (velké písmo = kapitola, tučné velké písmo = část knihy, střední tučné = podnadpis); číslo kapitoly nad nadpisem se přiřadí ke kapitole.
3. **Normalizace pro čtení nahlas**: `%` → *procent* (se správným tvarem: 1 procento / 2 procenta / 5 procent), `°C`, `+/–`, `>`, lomítka, rozsahy `35–100` → *35 až 100*, řady `4–1–3`, časy `6.00`, tisíce `1 358`, zkratky (*např., tj., tzv.* se shodou, *atd., apod., vs., n. l., č.* …), URL pryč, nadpisy VELKÝMI PÍSMENY → běžná věta (zkratky jako REM, DNA zůstanou).
4. **Dělení na kousky** max. ~3000 znaků, vždy na konci věty (s ochranou zkratek a iniciál).
5. **TTS** paralelně (výchozí 4 kousky najednou), retry s exponenciálním čekáním, **pokračování po pádu** – hotové kousky se přeskočí.
6. Na začátku kapitoly zazní její název („Kapitola šestá. Vaše mámy a Shakespeare… Blahodárné účinky spánku na mozek.“) a pauza (~2 s), před podnadpisy kratší pauza (~1,4 s).
7. **Sestavení přes ffmpeg**: kapitoly beze ztráty kvality (stream copy), `.m4b` jako AAC s kapitolami a metadaty.

## Instalace

Potřebuješ Python 3.10+ a ffmpeg.

```bash
# macOS
brew install ffmpeg
# Ubuntu/Debian: sudo apt install ffmpeg
# Windows: winget install Gyan.FFmpeg

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Generování audia potřebuje připojení k internetu (edge-tts volá službu Microsoftu, bez API klíče).

## Použití

### 1. Kontrola extrakce (doporučeno jako první krok)

```bash
python audiobook.py "kniha.pdf" --dry-run
```

Vypíše tabulku nalezených kapitol (strany, počet znaků, kousků, odhad délky) a uloží vyčištěný text do `out/<kniha>/<kniha>_clean.txt` – přesně to, co se bude číst, včetně hranic kousků a pauz.

### 2. Ukázka kvality (~2 minuty)

```bash
python audiobook.py "kniha.pdf" --sample
python audiobook.py "kniha.pdf" --sample --voice antonin
```

Vytvoří `out/<kniha>/ukazka_vlasta.mp3` (resp. `ukazka_antonin.mp3`).

### 3. Celá audiokniha

```bash
python audiobook.py "kniha.pdf"
python audiobook.py "kniha.pdf" --voice antonin --title "Proč spíme" --author "Matthew Walker"
```

Výstup:

```
out/<kniha>/
├── mp3/01_Spat_ci_nespat.mp3, 02_…      # kapitoly
├── <kniha>.m4b                            # audiokniha s kapitolami
└── work/                                  # mezivýsledky (kousky, ticho, obálka)
```

**Po pádu / přerušení** (Ctrl+C, výpadek sítě) stačí spustit stejný příkaz znovu – hotové kousky se přeskočí. Kousky jsou pojmenované podle hashe textu, hlasu a rychlosti, takže po změně textu nebo hlasu se přegenerují jen dotčené části. Složku `work/` můžeš po dokončení smazat.

### Volby

| Volba | Výchozí | Popis |
|---|---|---|
| `--dry-run` | – | jen kapitoly + vyčištěný text, bez audia |
| `--sample` | – | jen ukázka ~2 minuty |
| `--voice` | `vlasta` | `vlasta`, `antonin` nebo libovolný hlas edge-tts (`edge-tts --list-voices`) |
| `--rate` | `+0%` | rychlost řeči, např. `-5%`, `+10%` |
| `--workers` | `4` | kolik kousků se generuje souběžně (víc než ~6 může vést k omezení ze strany služby) |
| `--retries` | `6` | počet pokusů na kousek (čekání 2, 4, 8 … s) |
| `--title`, `--author` | z metadat PDF | metadata audioknihy |
| `--bitrate` | `64k` | bitrate AAC v `.m4b` |
| `--no-m4b` | – | vytvořit jen MP3 kapitol |
| `--no-cover` | – | nevkládat obálku (render 1. strany PDF, pokud je to obrázek) |
| `-o, --out` | `out/<název PDF>` | výstupní složka |

## Struktura projektu

```
audiobook.py            # vstupní bod (python audiobook.py …)
audiobook/
├── extract.py          # PyMuPDF: klasifikace řádků, záhlaví/zápatí, poznámky, odstavce
├── clean.py            # normalizace pro TTS, zkratky, čísla, dělení na věty
├── chapters.py         # kapitoly, ohlášení názvu, dělení na kousky ≤ 3000 znaků
├── tts.py              # edge-tts: paralelně, retry, pokračování
├── assemble.py         # ffmpeg: ticho, MP3 kapitol, M4B s kapitolami
└── cli.py              # argumenty, průběh v terminálu
```

## Přizpůsobení jiné knize

Heuristiky jsou relativní k základnímu písmu, takže by měly fungovat pro běžné knihy z Wordu. Když něco nesedí, podívej se do `--dry-run` výstupu a uprav:

- `BACK_MATTER_TITLES` v `extract.py` – nadpisy, od kterých se zbytek knihy přeskočí,
- `ABBREVIATIONS`, `UNITS`, `ACRONYMS` v `clean.py` – zkratky a symboly,
- `MAX_CHARS` a délky pauz v `chapters.py`.
