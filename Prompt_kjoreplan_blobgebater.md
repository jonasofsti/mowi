# Prompt: Verktøy for kjøreplaner for bløggebåter (Mowi, Jøsnøya)

## Kontekst og mål
Jeg er planleggingskoordinator hos Mowi. Bygg et **lokalt** verktøy (kjører på min
egen maskin, ingen sky) som lager **utkast til kjøreplaner** for bløggebåter som
frakter fisk fra oppdrettslokaliteter til **Jøsnøya slakteri**.

**Input** er en **slakteplan** (gitt av meg, eksportert fra et internt
simuleringssystem). Verktøyets jobb er **kun logistikken rundt båtene**: tildele
båter til slakteordrer, regne ut nøyaktige lastetidspunkter, sjekke at det henger
sammen, og flagge konflikter. Det er et **beslutningsstøtteverktøy** — jeg skal
kunne overstyre alt manuelt og få ny validering. Det er **ikke** et fullautomatisk
optimeringssystem i v1.

## Arbeidsmåte (viktig)
- Bygg **trinnvis**: datamodell → import → beregningsmotor → visning →
  konfliktsjekk, FØR du vurderer auto-optimering.
- **Still meg oppklarende spørsmål** før du antar noe uklart.
- List opp alle antakelser du gjør, og gjør dem til **konfigurerbare felt** med
  fornuftige standarder markert "må verifiseres". **Ikke finn på tall.**

## Slakteplan – inndataformat (dette er det viktigste arket)
Importer fra Excel. Kolonnene er (engelske overskrifter slik de kommer):

| Kolonne          | Betydning                                              |
|------------------|--------------------------------------------------------|
| Id               | Slakteordre-ID                                          |
| Process          | **Slaktedato** (dagen fisken pakkes på slakteriet)      |
| Boat             | Foreslått båt (kan være tom – se under)                 |
| Euth.            | Bløgget/avlivet (ja/nei) – kun gjennomgangsfelt, ingen logikk |
| Pickup time      | **Hentedato** (når båten laster på lokaliteten)         |
| Site             | Lokalitet, ofte med kode i parentes, f.eks. "Grøttingsøya (BDB)" |
| Unit             | Merd/enhet, f.eks. 0009                                  |
| Count            | Antall fisk                                             |
| Avg. weight      | Snittvekt i **gram**                                    |
| Biomass          | Biomasse i **tonn**                                     |
| Packing station  | Slakteri (Jøsnøya)                                       |

- `Boat`-kolonnen er et **forslag**: godta den hvis den finnes, men la meg
  overstyre. Verktøyet regner uansett ut nøyaktig lastetidspunkt og validerer.
- Flere rader kan dele samme lokalitet (ulike merder) eller samme båt+hentedato.
  Verktøyet skal kunne **slå sammen flere ordrer til én båttur** når kapasitet,
  tidsvindu og rute tillater det.
- Gjør importen robust mot rotete kolonner og varierende rekkefølge.

## Båter (4 stk – gjør flåten redigerbar, det finnes av og til en innleid 5. båt)
| Båt     | Type  | Kap. antall | Marsjfart | Lasterate (stk/t) |
|---------|-------|-------------|-----------|-------------------|
| Tauroa  | stor  | 110 000     | 13 knop   | ~30 000           |
| Tautiki | stor  | 110 000     | 13 knop   | ~30 000           |
| Taupo   | liten | 40 000      | 10 knop   | 8 000             |
| Taupiri | liten | 40 000      | 10 knop   | 8 000             |

- Kapasitet skal modelleres i **både tonn (biomasse) og antall fisk**. Reell grense
  er ofte biomasse. Gjør **maks tonn per båt** konfigurerbart (de store tar minst
  ~600 t i én last – sett en fornuftig standard og be meg bekrefte). Antall fisk =
  biomasse / snittvekt; bruk grensen som slår inn først.
- La meg velge om seilingstid regnes med båtens marsjfart (13/10) eller en felles
  **planleggingsfart** (default ~10–11 knop, slik historiske planer faktisk bruker).
- Lasterate er per båt (store har flere stunnere). Konfigurerbar.

## Slakteri: Jøsnøya (gjør slakteri redigerbart for framtiden – Ulvan/Herøy finnes)
- Båtene må være **framme kl. 06:15** alle hverdager (man–fre). Ingen ankomst i helg.
- **Kun én båt kan losse om gangen** → båter står i kø (FIFO etter ankomst).
- Lossetid per båt = antall fisk / **pakkerate (~7000 stk/t, konfigurerbar)**. For de
  store båtene er pakkeriets volum ofte den bindende begrensningen.
- I v1: **stol på slakteplanens dagsvolum**, ikke håndhev et eget kapasitetstak på
  anlegget. (Bekreft med meg.)
- **Vask: 4 timer** etter at båten er tømt; kan kjøres når som helst. **Ignorer
  mannskapsskift og hviledager** – det styres av andre.

## Avstander / seiling
- Avstand er i **nautiske mil (N.M.)**. Seilingstid (timer) = N.M. / fart (knop).
- Importer avstandene fra Excel. Reneste kilde er et ark med kolonnene
  **Lokalitet | N.M. | Seilingstid** (lokalitet → Jøsnøya). Støtt også det bredere
  formatet med kolonner per slakteri (Herøy/Ulvan/Jøsnøya).
- Distansene er **kun lokalitet → slakteri**. Konsekvenser:
  - Flere **merder på samme lokalitet**: ingen ekstra seiling, bare mer lastetid.
  - En tur innom **flere lokaliteter** (forekommer i praksis): da trengs
    seilingsledd **mellom** lokaliteter, som mangler i dataene. La meg legge inn
    slike ekstra ledd manuelt, og **advar tydelig** når en fler-lokalitetstur
    bruker et ledd uten registrert avstand (ikke gjett avstanden stille).
- Enkelte lokaliteter er svært langt unna (opptil ~32 t seiling én vei), så lasting
  kan måtte starte **to døgn** før slakting. Tidsmotoren må håndtere flere døgn
  bakover og døgnskifter korrekt.

## Tidsberegning (kjernelogikk – baklengs fra ankomst 06:15 på slaktedato)
En **båttur** er en **ordnet sekvens av stopp** (én eller flere lokaliteter), med
lasting på hvert stopp og seiling mellom dem. Reelt eksempel: 16.06 laster Tautiki
**først Mannbruholmen, deretter Grøttingsøya**, og leverer Jøsnøya 06:15 dagen etter.

Regn baklengs fra ankomst 06:15 på Process-dato, gjennom stoppene i omvendt rekkefølge:
```
SISTE stopp (det som ligger nærmest levering i ruten):
  avgang siste stopp = 06:15 − seilingstid(siste stopp → Jøsnøya)
  lasting ferdig     = avgang
  lasting start      = lasting ferdig − lastetid(stopp)
  ankomst stopp      = lasting start
For hvert TIDLIGERE stopp (jobb bakover gjennom ruten):
  avgang dette stopp = ankomst neste stopp − seilingstid(dette stopp → neste stopp)
  lasting ferdig     = avgang
  lasting start      = lasting ferdig − lastetid(stopp)
  ankomst stopp      = lasting start
Til slutt:
  avgang Jøsnøya (ren båt) = ankomst første stopp − seilingstid(Jøsnøya → første stopp)

  lastetid(stopp) = antall fisk på stoppet / lasterate (per båt)
Etter levering: lossing (antall / pakkerate, kun én båt om gangen) → vask (4 t) → ledig
```
- **Rekkefølgen på stoppene bestemmer jeg** (eller jeg godtar rekkefølgen fra
  slakteplanen). Ikke endre rekkefølgen stille i v1 – men du kan gjerne *foreslå* en
  bedre rekkefølge som et forslag jeg kan godta.
- Hvert ledd mellom to **ulike** lokaliteter trenger egen seilingsavstand (mangler i
  grunndataene – la meg legge den inn, og **advar** hvis leddet mangler; ikke gjett).
  Flere **merder på samme lokalitet** legger bare til lastetid, ikke seiling.
- Valider at slakteplanens oppgitte **Pickup time (hentedato)** er gjennomførbar.
  Hvis turen ikke rekker 06:15 med lasting på hentedagen, **flagg at hentingen må
  starte tidligere** (evt. dagen før).

## Mål og betingelser
- **Minimer holdetid** (tid fra ferdig lastet til slakting) – fisken blir dødsstiv
  hvis det går for lenge. Last derfor **så sent som mulig** på hentedagen. På turer
  med flere stopp har **fisken fra det første stoppet lengst holdetid** (den ligger i
  båten mens du seiler til og laster de neste stoppene). Regn ut holdetid **per
  stopp/ordre**, og sjekk maks-holdetid mot det dårligste (først lastede) stoppet.
- **MEN** trekk lastingen en **konfigurerbar buffer** (default lav, f.eks. 2–3 t)
  tidligere enn seneste gjennomførbare tidspunkt, som slingringsmonn mot uforutsette
  hendelser. Støtt i tillegg en valgfri **maks holdetid** som gir varsel ved
  overskridelse (be meg sette grensen – ikke gjett et medisinsk tall).
- Flagg disse konfliktene:
  - Båt to steder samtidig (overlapp i tidslinjen, inkl. vask).
  - Last over kapasitet (tonn **eller** antall).
  - Ankomst i helg.
  - Brudd på maks holdetid.
  - Båt ikke ferdig vasket før neste tur.
  - Kø på losseplassen som dytter en båt forbi sitt 06:15-vindu.
  - Lokalitet/ledd uten registrert avstand.
- Helg: ingen levering lør/søn, men lasting kan skje i helg for mandagslevering.

## Utdata
- Kjøreplan i **samme rutenett-format jeg er vant til**: rader = dato/dag, kolonner
  per båt, der hver celle viser lokalitet, merd, lastetidspunkt, lastemengde
  (antall + tonn) og merknad. I tillegg en **tidslinje/Gantt** per båt.
- Liste over **advarsler/konflikter** med forklaring.
- **Eksport til Excel** i et format jeg kan dele og redigere.

## Teknologi
- Lokalt og enkelt å kjøre/vedlikeholde for en ikke-utvikler, med god Excel-støtte.
  Foreslå f.eks. Python + Streamlit + pandas/openpyxl, eller en enkelt-fil lokal
  nettside. **Begrunn valget kort før du starter.**
- Lokal lagring (SQLite eller fil). Ingen skytjenester.

## Leveranse nå
1. Still meg de viktigste gjenstående oppklaringsspørsmålene (bl.a. maks tonn per
   båt, maks holdetid + buffer, og hvordan jeg helst vil oppgi seilingsledd mellom
   lokaliteter).
2. Foreslå datamodell, importformat og stack.
3. Bygg en kjørbar v1: import av slakteplan + avstander, tildeling av båter
   (godta forslag fra slakteplanen + manuell overstyring), full baklengs
   tidsberegning med kø på losseplassen, konfliktsjekk, og Excel inn/ut i
   rutenett-formatet. Auto-forslag til tildeling kan komme som steg 2.
