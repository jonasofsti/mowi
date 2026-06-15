"""Excel-eksport i rutenett-formatet (rader = dato/dag, kolonner per båt).

I tillegg eksporteres et detaljark og en advarsels-/konfliktliste.
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from .config import AppConfig
from .engine import Conflict
from .models import TripSchedule

DAGER = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]


def grid_dataframe(schedules: list[TripSchedule], config: AppConfig) -> pd.DataFrame:
    """Rutenett: én rad per dato, én kolonne per båt. Celle = stoppene på turen."""
    boats = [b.name for b in config.boats if b.active]
    dates = sorted({s.trip.process_date for s in schedules})
    rows = []
    for d in dates:
        row = {"Dato": d.isoformat(), "Dag": DAGER[d.weekday()]}
        for boat in boats:
            cell_parts = []
            for s in schedules:
                if s.boat == boat and s.trip.process_date == d:
                    for st in s.stops:
                        cell_parts.append(
                            f"{st.site_name} | merd-sum {st.count} stk / {st.biomass_t:.1f} t | "
                            f"last {st.load_start:%d.%m %H:%M}–{st.load_finish:%H:%M}"
                            + (" ⚠ avstand mangler" if st.leg_missing else "")
                        )
                    if s.warnings:
                        cell_parts.append("Merknad: " + "; ".join(s.warnings))
            row[boat] = "\n".join(cell_parts)
        rows.append(row)
    return pd.DataFrame(rows, columns=["Dato", "Dag"] + boats)


def detail_dataframe(schedules: list[TripSchedule]) -> pd.DataFrame:
    rows = []
    for s in schedules:
        for i, st in enumerate(s.stops):
            rows.append({
                "Båt": s.boat,
                "Slaktedato": s.trip.process_date.isoformat(),
                "Stopp #": i + 1,
                "Lokalitet": st.site_name,
                "Antall": st.count,
                "Tonn": round(st.biomass_t, 1),
                "Ankomst lok.": st.arrival.strftime("%d.%m %H:%M"),
                "Last start": st.load_start.strftime("%d.%m %H:%M"),
                "Last ferdig": st.load_finish.strftime("%d.%m %H:%M"),
                "Avgang": st.departure.strftime("%d.%m %H:%M"),
                "Seiling t→neste": round(st.sailing_to_next_h, 2),
                "Holdetid (t)": round(st.holding_h, 1),
                "Avstand mangler": "JA" if st.leg_missing else "",
            })
        rows.append({
            "Båt": s.boat,
            "Slaktedato": s.trip.process_date.isoformat(),
            "Stopp #": "→ levering",
            "Lokalitet": "Jøsnøya",
            "Ankomst lok.": s.delivery.strftime("%d.%m %H:%M"),
            "Last start": "",
            "Last ferdig": "",
            "Avgang": (s.station_departure_clean.strftime("%d.%m %H:%M")
                       + " (ren båt ut)"),
            "Holdetid (t)": round(s.max_holding_h, 1),
        })
    return pd.DataFrame(rows)


def conflicts_dataframe(conflicts: list[Conflict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Alvor": c.severity, "Type": c.kind, "Båt": c.boat,
        "Slaktedato": c.process_date, "Melding": c.message,
    } for c in conflicts]) if conflicts else pd.DataFrame(
        columns=["Alvor", "Type", "Båt", "Slaktedato", "Melding"])


def export_excel(schedules: list[TripSchedule], conflicts: list[Conflict],
                 config: AppConfig) -> bytes:
    """Returnerer Excel-fila som bytes (kan lastes ned / skrives til disk)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        grid_dataframe(schedules, config).to_excel(xw, sheet_name="Kjøreplan", index=False)
        detail_dataframe(schedules).to_excel(xw, sheet_name="Detaljer", index=False)
        conflicts_dataframe(conflicts).to_excel(xw, sheet_name="Konflikter", index=False)
    return buf.getvalue()
