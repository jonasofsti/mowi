# Fôrprognose – regelbasert vurdering (Vest & Midt)

Lokalt, gjenbrukbart verktøy som leser Excel-eksport av fôrprognose-cuben og gir
**grafer + regelbaserte anbefalinger** for lakseoppdrett i region Vest og Midt.

> Holder mennesket i løkka: verktøyet **flagger og forklarer** – du bestemmer. Ingen autopilot.

## Kjøring – ingen installasjon, ingen admin

1. Last ned hele mappa (inkl. `vendor/`-mappa) til PC-en.
2. **Dobbeltklikk `index.html`** – den åpnes i nettleseren (Chrome/Edge/Firefox).
3. Klikk **«Velg prognose-fil (.xlsx)»** og pek på `prognose_fôr.xlsx`.

Alt skjer i nettleseren. Ingen Node, npm, Python, server eller Docker.
Bibliotekene (SheetJS + Chart.js) er buntet lokalt i `vendor/`, så verktøyet
virker **offline uten internett/CDN**. `file://` fungerer (FileReader, ingen server).

> Vil du heller bruke en lokal server (helt valgfritt, kun hvis Python allerede finnes):
> `python -m http.server` i mappa, og åpne `http://localhost:8000`. **Ikke installer noe.**

## Hva verktøyet gjør (per region: Vest og Midt)

- **Nøkkeltall:** faktisk snitt, prognosesnitt, endring, juni→juli (inneværende vs 2024), status.
- **Graf 1 – totalt fôr per uke:** faktiske uker heltrukket, prognoseuker stiplet.
- **Graf 2 – avvik per lokalitet:** Offensiv (rød) / Realistisk (grønn) / Defensiv (blå), sortert.
- **Graf 3 – juni→juli-økning:** 2024 vs prognose (+ historisk fôr/ib-snitt som referanse).
- **Tabell – regelbaserte justeringsforslag** med begrunnelse og 2024-sammenligning per lokalitet.
- **Seksjon – slaktelokaliteter** (fôr → 0) som påvirker utfôring.
- **Skriv ut / lagre som PDF** via nettleseren (egen knapp).

## Beregningslogikk (deterministisk)

- `faktisk_snitt = snitt(w23, w24)` – to siste faktiske uker
- `prognose_snitt = snitt(w25, w26)` – to **rene** prognoseuker (ikke w27, som er splittet)
- `endring_pct = (prognose_snitt − faktisk_snitt) / faktisk_snitt × 100`
- **Status:** Offensiv ≥ +8 %, Defensiv ≤ −8 %, ellers Realistisk
- Regiontotaler per **hele** uker (uke 27 = juni-del + juli-del slått sammen)
- juni→juli = `m06 Total → m07 Total`, sammenlignet mot 2024 per region og per lokalitet

### Innebygde forbehold (lærdom fra manuell analyse)
- **Usikkert grunnlag:** spriker w23 og w24 mye (én er en dipp), flagges raden og anbefalingen dempes.
- **Slaktetall finnes ikke i fôr-cuben.** Verktøyet utleder kun «fôr → 0 = slaktes ut».
  Du kan valgfritt lime inn slaktetall (antall fisk) i eget panel.
- **Ett år kan være avviksår** (2024 var svakt). Finnes `mars-apr` (fôr/ib), brukes flerårssnittet
  som bedre referanse, og verktøyet advarer mot å kutte blindt mot ett svakt år.

## Robust parsing av kjente kvirker

- Finner `Site name`-headerraden dynamisk (varierer mellom ark).
- Leser kolonnene **ut fra header-labelene** (`2026w23` …) – ingen hardkodede posisjoner.
- **Splittet uke 27:** samme ukelabel i to kolonner summeres til hel uke.
- **2024-ark** med andre ukenummer (w22..w31) og arknavn som `... (2)` håndteres.
- `Grand Total`-rad hoppes over. Tydelige feilmeldinger hvis ark/kolonner mangler.

## Valgfri AI-vurdering (AV som standard)

Et klart adskilt panel kan generere en tekstlig vurdering via et API-kall.
Krever internett + egen API-nøkkel (lagres kun lokalt i nettleseren).
**Kjernen virker fullstendig uten dette og uten internett.**

## Filer

| Fil | Rolle |
|-----|-------|
| `index.html` | Hele verktøyet (selvstendig: UI + logikk inline). Åpnes ved dobbeltklikk. |
| `vendor/xlsx.full.min.js` | SheetJS – lokal kopi (Excel-lesing) |
| `vendor/chart.umd.min.js` | Chart.js – lokal kopi (grafer) |
| `prognose_fôr.xlsx` | Eksempelfil til testing |
| `test.js` | Node-test (valgfri, kun for utvikling) som gjenbruker samme logikk fra `index.html` |

### Utvikler-test (valgfritt)
Logikken er enhetstestet uten nettleser. `test.js` henter CORE-blokken rett ut av
`index.html` (samme kilde som nettleseren bruker) og verifiserer mot ekte filer:

```
node test.js "prognose_fôr.xlsx"
```
