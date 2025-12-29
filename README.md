# Statistiky SDH

Nástroje pro analýzu a vizualizaci statistik událostí hasičů ze systému webohled.hzsmsk.cz.

## Přehled nástrojů

### 1. statistiky.py
Komplexní kalkulátor statistik hasičských událostí s podporou stahování dat z webu, různých analýz a exportů.

### 2. pravdepodobnost.py
Analyzátor pravděpodobnosti výskytu událostí podle dne v týdnu a části dne s vizualizací formou heatmapy.

---

## statistiky.py

### Funkce
- Stahování dat událostí z webového API
- Výpočet statistik podle:
  - typu události
  - podtypu události
  - měsíce
  - čtvrtletí
  - dne v týdnu
  - hodiny v dni
  - stavu události
  - ZOC (Zpráva o činnosti)
- Export dat do CSV, JSON
- Generování grafů (vyžaduje matplotlib)

### Použití

#### Stažení dat z webu a zobrazení statistik
```bash
python3 statistiky.py --from 2025-01-01 --to 2025-12-31 --unit 8102157
```

#### Stažení a uložení dat pro pozdější použití
```bash
python3 statistiky.py --from 2025-01-01 --to 2025-12-31 --unit 8102157 --save
```

#### Export statistik do CSV a vytvoření grafů
```bash
python3 statistiky.py --from 2025-01-01 --to 2025-12-31 --unit 8102157 --export-csv --export-plots
```

#### Použití lokálních JSON souborů
```bash
python3 statistiky.py --export-plots
```

### Parametry

**Stahování z webu:**
- `--from DATUM` - Počáteční datum (RRRR-MM-DD nebo RRRR-MM-DDTHH:MM:SS.SSSZ)
- `--to DATUM` - Koncové datum (RRRR-MM-DD nebo RRRR-MM-DDTHH:MM:SS.SSSZ)
- `--unit ID` - ID jednotky (např. 8102157)
- `--save` - Uložit stažená data do lokálních JSON souborů

**Lokální soubory:**
- `--events FILE` - JSON soubor s událostmi (výchozí: udalosti.json)
- `--types FILE` - JSON soubor s typy (výchozí: typy.json)
- `--subtypes FILE` - JSON soubor s podtypy (výchozí: podtypy.json)
- `--states FILE` - JSON soubor se stavy (výchozí: stavy.json)

**Export:**
- `--export-csv` - Exportovat statistiky do CSV souborů
- `--export-json` - Exportovat statistiky do JSON souboru
- `--export-plots` - Vygenerovat grafy jako PNG obrázky

### Výstupní soubory

**CSV soubory:**
- `stats_by_type.csv` - Statistiky podle typu
- `stats_by_subtype.csv` - Statistiky podle podtypu
- `stats_by_month.csv` - Měsíční statistiky
- `stats_by_hour.csv` - Hodinové statistiky
- `stats_by_state.csv` - Statistiky podle stavu

**PNG grafy:**
- `graf_typy.png` - Události podle typu (sloupcový graf)
- `graf_mesice.png` - Rozložení po měsících (čárový graf)
- `graf_ctvrtleti.png` - Rozložení po čtvrtletích (sloupcový graf)
- `graf_dny.png` - Rozložení po dnech v týdnu (sloupcový graf)
- `graf_hodiny.png` - Rozložení po hodinách (sloupcový graf)
- `graf_podtypy.png` - Top 15 podtypů (sloupcový graf)
- `graf_stavy.png` - Top 10 stavů (sloupcový graf)

**JSON soubor:**
- `statistics.json` - Všechny statistiky v JSON formátu

---

## pravdepodobnost.py

### Funkce
- Výpočet pravděpodobnosti události pro každou kombinaci:
  - Den v týdnu (Pondělí - Neděle)
  - Část dne (Noc, Ráno, Odpoledne, Večer)
- Zobrazení tabulky pravděpodobností v konzoli
- Generování heatmapy vizualizace (vyžaduje matplotlib)
- Identifikace nejrizikovějších a nejbezpečnějších časových oken

### Části dne
- **Noc:** 0:00 - 6:00
- **Ráno:** 6:00 - 12:00
- **Odpoledne:** 12:00 - 18:00
- **Večer:** 18:00 - 24:00

### Použití

#### Základní použití (s výchozím souborem udalosti.json)
```bash
python3 pravdepodobnost.py
```

#### S vlastním souborem událostí
```bash
python3 pravdepodobnost.py --events data/udalosti.json
```

#### S vlastním výstupním souborem pro heatmapu
```bash
python3 pravdepodobnost.py --output moje_heatmapa.png
```

### Parametry
- `--events FILE` - JSON soubor s událostmi (výchozí: udalosti.json)
- `--output FILE` - Výstupní soubor pro heatmapu (výchozí: heatmapa_pravdepodobnost.png)

### Výstupní soubory
- `heatmapa_pravdepodobnost.png` - Heatmapa pravděpodobnosti událostí

### Výstup v konzoli
- Tabulka pravděpodobností pro všechny kombinace dne a části dne
- Průměrná pravděpodobnost
- Top 5 nejrizikovějších kombinací
- Top 5 nejbezpečnějších kombinací

---

## Instalace závislostí

### Základní závislosti (součást Python 3.7+)
```bash
# Žádné další závislosti pro základní funkcionalitu
```

### Volitelné závislosti pro grafy
```bash
pip install matplotlib numpy
```

### Volitelné závislosti pro lepší zpracování časových zón (Python < 3.9)
```bash
pip install pytz
```

---

## Datové soubory

Oba nástroje pracují s JSON soubory obsahujícími data událostí:

- `udalosti.json` - Seznam událostí s časovými razítky a atributy
- `typy.json` - Číselník typů událostí
- `podtypy.json` - Číselník podtypů událostí
- `stavy.json` - Číselník stavů událostí

Tyto soubory lze získat:
1. **Stažením z webu** pomocí `statistiky.py --from ... --to ... --unit ... --save`
2. **Ručním exportem** ze systému webohled.hzsmsk.cz

---

## Příklady workflow

### Kompletní analýza za rok 2025
```bash
# 1. Stáhnout data a uložit lokálně
python3 statistiky.py --from 2025-01-01 --to 2025-12-31 --unit 8102157 --save

# 2. Vygenerovat kompletní statistiky s grafy
python3 statistiky.py --export-csv --export-json --export-plots

# 3. Vytvořit heatmapu pravděpodobností
python3 pravdepodobnost.py
```

### Rychlá analýza bez ukládání dat
```bash
# Stáhnout, analyzovat a zobrazit statistiky
python3 statistiky.py --from 2025-01-01 --to 2025-12-31 --unit 8102157
```

### Analýza existujících dat
```bash
# Pokud už máte uložené JSON soubory
python3 statistiky.py --export-plots
python3 pravdepodobnost.py
```

---

## Poznámky

### Časové zóny
- Skript `statistiky.py` automaticky provádí převody mezi českým místním časem a UTC
- Pro správné zpracování letního času doporučujeme Python 3.9+ (s modulem zoneinfo)

### Formát datumů
Datumy lze zadávat v těchto formátech:
- `RRRR-MM-DD` (např. 2025-01-01)
- `RRRR-MM-DDTHH:MM:SS.SSSZ` (ISO formát s časem)

Při použití formátu bez času:
- `--from` datum začíná od 00:00:00
- `--to` datum končí v 23:59:59

---

## Licence

MIT
