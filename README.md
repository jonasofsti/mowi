# Kjøreplan for bløggebåter (Mowi, Jøsnøya)

Lokalt beslutningsstøtteverktøy som lager **utkast til kjøreplaner** for
bløggebåter ut fra en **slakteplan**. Verktøyet tildeler båter, regner ut
nøyaktige lastetidspunkter **baklengs** fra ankomst 06:15 på slaktedato,
modellerer kø på losseplassen, og flagger konflikter. Du kan overstyre alt
manuelt og få ny validering.

Kravspesifikasjonen ligger i [`Prompt_kjoreplan_blobgebater.md`](Prompt_kjoreplan_blobgebater.md).

> **Ikke et auto-optimeringssystem i v1.** Det godtar forslaget fra slakteplanen
> og lar deg overstyre. Auto-forslag til tildeling er planlagt som neste steg.

## Stack og hvorfor

| Valg | Begrunnelse |
|------|-------------|
| **Python + Streamlit** | Kjører 100 % lokalt med én kommando, ingen sky. Lett å vedlikeholde for en ikke-utvikler. Redigerbare tabeller og Gantt uten å skrive kode. |
| **pandas + openpyxl** | Robust Excel inn/ut – kjernen i arbeidsflyten din. |
| **SQLite** | Lokal lagring av konfig, avstander, ledd og tildelinger. Ingen skytjenester. |

## To måter å kjøre på

### A) Uten installasjon / uten admin (anbefalt på låst PC) — `kjoreplan.html`

Dobbeltklikk **`kjoreplan.html`** så åpnes hele verktøyet i nettleseren du
allerede har. Ingen Python, ingen installasjon, ingen admin-tilgang. Excel inn/ut
går via SheetJS (lastes fra nett ved åpning – krever internett), og all logikk +
lagring skjer lokalt i nettleseren (localStorage). Beregningsmotoren er en port av
Python-versjonen og gir **identiske** tall (verifisert).

**Én handling → ferdig forslag:** Last opp slakteplanen, så lager programmet
**automatisk** et forslag til kjøreplan (velger båter, slår sammen ordrer til
turer, regner tider). Du kan overstyre alt i fane 3.

- **Excel-fil** (eksakt) eller **bilde/skjermbilde** (OCR via Tesseract.js – leses
  av automatisk, men **må kontrolleres** før bruk).
- **Avstander** legges inn én gang og huskes; uten dem lages forslaget likevel,
  men lastetidspunktene er foreløpige (seiling = 0) til avstandene er på plass.

**Auto-tildeling (forslag):** greedy per slaktedato – store båter fylles først,
én tur per båt per dag, og én lokalitet per tur (slik trengs ingen seilingsledd).
Samme lokalitet samme dag slås sammen; dager over kapasitet splittes på flere
båter; ordrer uten plass markeres som ufordelt.

> Trenger du en helt offline-versjon (uten internett), kan Excel-biblioteket
> bygges inn i fila – si fra.

### B) Python + Streamlit (for IT-styrt oppsett)

```bash
pip install -r requirements.txt
python sample_data/generate_samples.py     # (valgfritt) lag demo-filer
streamlit run app.py
```

Appen åpnes i nettleseren. Alt lagres lokalt i `kjoreplan.db`.

Begge variantene har samme fem faner og samme beregningsmotor.

## Arbeidsflyt i appen (fanene)

1. **Import** – last opp slakteplan (.xlsx), avstander (lokalitet → slakteri),
   og evt. seilingsledd mellom lokaliteter. Manglende ledd kan også legges inn
   manuelt her (lagres for gjenbruk).
2. **Konfig** – rediger flåte, kapasiteter, fart, rater, vask, buffer og maks
   holdetid. Standardene er merket «må verifiseres».
3. **Tildeling** – `Boat` fra slakteplanen er forhåndsfylt; overstyr fritt.
   `trip_seq` grupperer turer, `stop_seq` bestemmer rekkefølgen på stoppene
   (rekkefølgen endres aldri stille).
4. **Kjøreplan & konflikter** – rutenett (rader = dato, kolonner = båt),
   Gantt per båt, detaljert tidsplan og konfliktliste.
5. **Eksport** – last ned Excel med arkene *Kjøreplan*, *Detaljer*, *Konflikter*.

## Antakelser (alle konfigurerbare – «må verifiseres»)

Bekreftet med planleggingskoordinator under oppstart:

- **Maks last:** store båter (Tauroa/Tautiki) **600 t**, små (Taupo/Taupiri) **220 t**.
  Antall (110 000 / 40 000) eller tonn – den grensen som slår inn først gjelder.
- **Holdetid:** **ingen buffer** (last så sent som mulig = ankomst 06:15). Maks
  holdetid er **ikke gjettet** – sett tallet selv i Konfig for å få varsel.
- **Seilingsledd mellom lokaliteter:** importeres fra fra/til-tabell hvis den
  finnes, ellers legges inn manuelt. **Advarer tydelig** ved manglende ledd og
  gjetter aldri avstanden (settes til 0 t + flagg).
- **Fart:** felles planleggingsfart **10,5 knop** (kan byttes til båtens marsjfart).

Øvrige standarder satt i `kjoreplan/config.py`: pakkerate 7000 stk/t, vask 4 t,
ankomst 06:15 man–fre, kun én båt losser om gangen (FIFO).

## Konfliktene som flagges

Kapasitet (tonn/antall), helgelevering, manglende avstand/ledd, brudd på maks
holdetid (hvis satt), kø på losseplassen forbi 06:15-vinduet, båt ikke ferdig
vasket før neste tur / to steder samtidig, og ugjennomførbar hentedato.

## Prosjektstruktur

```
kjoreplan.html              # selvstendig nettleser-app (null installasjon)
app.py                      # Streamlit-UI
kjoreplan/
  config.py                 # konfigurerbare standarder
  models.py                 # datamodell (ordre, stopp, tur, tidsplan ...)
  importers.py              # robust Excel-import (slakteplan/avstander/ledd)
  planner.py                # bygger turer fra ordrer + tildelinger
  engine.py                 # baklengs tidsberegning, kø, konfliktsjekk
  export.py                 # Excel-eksport i rutenett-format
  db.py                     # SQLite-lagring
tests/test_engine.py        # enhetstester for kjernelogikken
sample_data/                # generator for syntetiske demo-filer
```

## Tester

```bash
python tests/test_engine.py        # eller: python -m pytest tests/ -q
```

Testene verifiserer bl.a. at baklengs-beregningen treffer eksempelet i kravspec
(første stopp har lengst holdetid), at manglende ledd advares uten gjetting, og
at FIFO-køen på losseplassen er korrekt.

## Status / neste steg

- ✅ v1: import (Excel/bilde-OCR), **auto-forslag til tildeling**, manuell
  overstyring, full baklengs tidsberegning med kø, konfliktsjekk, Gantt og Excel
  inn/ut i rutenett-format.
- ⏭️ Videre: smartere optimering (fler-stopp-turer når avstander finnes, minimere
  antall turer/holdetid på tvers av dager), og forslag til bedre stopprekkefølge.
