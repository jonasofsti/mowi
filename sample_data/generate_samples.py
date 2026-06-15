"""Genererer SYNTETISKE eksempelfiler for å teste/demonstrere verktøyet.

VIKTIG: Tallene her er oppdiktede demo-verdier (lokaliteter, avstander, antall),
IKKE reelle driftsdata. De finnes kun for å vise formatet og kjøre verktøyet.
Scenarioet bygger på det reelle eksempelet i kravspec: 16.06 laster Tautiki
først Mannbruholmen, deretter Grøttingsøya, og leverer Jøsnøya 06:15 dagen etter.

Kjør:  python sample_data/generate_samples.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent


def slaughter_plan() -> pd.DataFrame:
    rows = [
        # Id, Process, Boat, Euth., Pickup time, Site, Unit, Count, Avg. weight, Biomass, Packing station
        ["1001", date(2026, 6, 17), "Tautiki", "ja", date(2026, 6, 16),
         "Mannbruholmen (MBH)", "0007", 30000, 4500, 135.0, "Jøsnøya"],
        ["1002", date(2026, 6, 17), "Tautiki", "ja", date(2026, 6, 16),
         "Grøttingsøya (BDB)", "0009", 30000, 4200, 126.0, "Jøsnøya"],
        ["1003", date(2026, 6, 17), "Tauroa", "ja", date(2026, 6, 16),
         "Grøttingsøya (BDB)", "0011", 40000, 4200, 168.0, "Jøsnøya"],
        ["1004", date(2026, 6, 18), "Taupo", "nei", date(2026, 6, 17),
         "Storvika (STV)", "0003", 35000, 3800, 133.0, "Jøsnøya"],
        ["1005", date(2026, 6, 18), "Taupiri", "nei", date(2026, 6, 16),
         "Langholmen (LGH)", "0001", 38000, 3900, 148.2, "Jøsnøya"],
    ]
    cols = ["Id", "Process", "Boat", "Euth.", "Pickup time", "Site", "Unit",
            "Count", "Avg. weight", "Biomass", "Packing station"]
    return pd.DataFrame(rows, columns=cols)


def distances() -> pd.DataFrame:
    # Lokalitet (kode) | N.M. | Seilingstid (demo-tall)
    rows = [
        ["Mannbruholmen (MBH)", 42.0, None],
        ["Grøttingsøya (BDB)", 21.0, None],
        ["Storvika (STV)", 63.0, None],
        ["Langholmen (LGH)", 336.0, None],  # svært langt unna (~32 t @ 10.5 kn)
    ]
    return pd.DataFrame(rows, columns=["Lokalitet", "N.M.", "Seilingstid"])


def legs() -> pd.DataFrame:
    # Seilingsledd mellom lokaliteter (mangler i grunndata – demo)
    rows = [["Mannbruholmen (MBH)", "Grøttingsøya (BDB)", 10.5]]
    return pd.DataFrame(rows, columns=["Fra", "Til", "N.M."])


def main():
    slaughter_plan().to_excel(OUT / "slakteplan_demo.xlsx", index=False)
    distances().to_excel(OUT / "avstander_demo.xlsx", index=False)
    legs().to_excel(OUT / "seilingsledd_demo.xlsx", index=False)
    print("Skrev demo-filer til", OUT)


if __name__ == "__main__":
    main()
