"""Datamodell for kjøreplan-verktøyet.

Sentrale begreper:
- SlaughterOrder : én rad i slakteplanen (en merd/enhet som skal slaktes).
- Site           : en oppdrettslokalitet (med kode og avstand til slakteriet).
- Distance       : lokalitet -> slakteri, i nautiske mil.
- InterSiteLeg   : seilingsledd MELLOM to lokaliteter (mangler i grunndata; legges inn manuelt/importeres).
- Stop           : ett stopp på en båttur = én lokalitet + de ordrene som lastes der.
- Trip           : en ordnet sekvens av stopp for én båt med levering på Process-dato.
- StopSchedule / TripSchedule : utregnet tidslinje (fylles av engine).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class SlaughterOrder:
    id: str
    process_date: date            # slaktedato (dagen fisken pakkes)
    proposed_boat: Optional[str]  # forslag fra slakteplanen (kan være tom)
    euth: Optional[str]           # bløgget/avlivet – kun gjennomgangsfelt
    pickup_date: Optional[date]   # foreslått hentedato
    site_name: str                # rå lokalitetstekst, f.eks. "Grøttingsøya (BDB)"
    site_code: Optional[str]      # kode i parentes, f.eks. "BDB"
    unit: str                     # merd/enhet
    count: int                    # antall fisk
    avg_weight_g: float           # snittvekt i gram
    biomass_t: float              # biomasse i tonn
    packing_station: str          # slakteri (Jøsnøya)

    @property
    def site_key(self) -> str:
        """Nøkkel for å matche mot avstandstabellen (kode hvis finnes, ellers navn)."""
        return (self.site_code or self.site_name or "").strip()


@dataclass
class Site:
    name: str
    code: Optional[str] = None

    @property
    def key(self) -> str:
        return (self.code or self.name or "").strip()


@dataclass
class Distance:
    """Lokalitet -> slakteri."""
    site_key: str
    station: str
    nm: float                     # nautiske mil
    sailing_time_h: Optional[float] = None  # valgfri direkte oppgitt seilingstid


@dataclass
class InterSiteLeg:
    """Seilingsledd mellom to lokaliteter (begge retninger antas like)."""
    from_key: str
    to_key: str
    nm: float


@dataclass
class Stop:
    """Ett stopp på en tur: en lokalitet + ordrene som lastes der."""
    site_key: str
    site_name: str
    order_ids: list[str] = field(default_factory=list)
    # aggregert mengde (fylles fra ordrene)
    count: int = 0
    biomass_t: float = 0.0


@dataclass
class Trip:
    """En båttur: ordnet sekvens av stopp, levering 06:15 på process_date."""
    boat: str
    process_date: date            # slakte-/leveringsdato
    stops: list[Stop] = field(default_factory=list)
    note: str = ""
    trip_id: Optional[int] = None

    @property
    def total_count(self) -> int:
        return sum(s.count for s in self.stops)

    @property
    def total_biomass_t(self) -> float:
        return sum(s.biomass_t for s in self.stops)


# ---- utregnet tidsplan (output fra engine) ----

@dataclass
class StopSchedule:
    site_key: str
    site_name: str
    arrival: datetime             # båt ankommer lokaliteten (= lasting start)
    load_start: datetime
    load_finish: datetime         # = avgang fra stoppet
    departure: datetime
    sailing_to_next_h: float      # seiling til neste stopp (eller til slakteriet)
    leg_missing: bool             # True hvis seilingsledd mangler (ble satt til 0 + advart)
    count: int
    biomass_t: float
    holding_h: float              # holdetid for fisken lastet på dette stoppet


@dataclass
class TripSchedule:
    trip: Trip
    boat: str
    delivery: datetime            # ankomst slakteri (06:15)
    station_departure_clean: datetime  # når ren båt forlater slakteriet for første stopp
    stops: list[StopSchedule] = field(default_factory=list)
    # losse-/vaskevindu (fylles av kø-beregning på slakteriet)
    unload_start: Optional[datetime] = None
    unload_end: Optional[datetime] = None
    wash_end: Optional[datetime] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def earliest_load_start(self) -> Optional[datetime]:
        return min((s.load_start for s in self.stops), default=None)

    @property
    def max_holding_h(self) -> float:
        return max((s.holding_h for s in self.stops), default=0.0)
