"""Beregningsmotor: baklengs tidsberegning, kø på losseplassen og konfliktsjekk.

Kjernen regner BAKLENGS fra ankomst 06:15 på Process-dato gjennom stoppene i
omvendt rekkefølge (se Prompt_kjoreplan_blobgebater.md, "Tidsberegning").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .config import AppConfig
from .models import (
    Trip, TripSchedule, StopSchedule, Distance, InterSiteLeg,
)


# ----------------------------------------------------------------------------
# Hjelpere: avstander og fart
# ----------------------------------------------------------------------------

class DistanceBook:
    """Slår opp avstander lokalitet->slakteri og ledd mellom lokaliteter."""

    def __init__(self, distances: list[Distance], legs: list[InterSiteLeg]):
        self._to_station: dict[str, Distance] = {}
        for d in distances:
            self._to_station[_norm(d.site_key)] = d
        self._legs: dict[tuple[str, str], float] = {}
        for lg in legs:
            self._legs[(_norm(lg.from_key), _norm(lg.to_key))] = lg.nm
            self._legs[(_norm(lg.to_key), _norm(lg.from_key))] = lg.nm  # symmetrisk

    def nm_to_station(self, site_key: str) -> Optional[float]:
        d = self._to_station.get(_norm(site_key))
        return d.nm if d else None

    def direct_time_to_station(self, site_key: str) -> Optional[float]:
        d = self._to_station.get(_norm(site_key))
        return d.sailing_time_h if d and d.sailing_time_h is not None else None

    def nm_between(self, from_key: str, to_key: str) -> Optional[float]:
        if _norm(from_key) == _norm(to_key):
            return 0.0  # samme lokalitet (ulike merder) – ingen seiling
        return self._legs.get((_norm(from_key), _norm(to_key)))


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def sailing_hours(nm: float, boat_name: str, config: AppConfig) -> float:
    """Seilingstid (timer) = N.M. / fart (knop)."""
    if config.plan.use_common_speed:
        speed = config.plan.plan_speed_knots
    else:
        b = config.boat(boat_name)
        speed = b.speed_knots if b else config.plan.plan_speed_knots
    if speed <= 0:
        return 0.0
    return nm / speed


def load_hours(count: int, boat_name: str, config: AppConfig) -> float:
    """Lastetid = antall fisk / lasterate (per båt)."""
    b = config.boat(boat_name)
    rate = b.load_rate if b else 0.0
    if rate <= 0:
        return 0.0
    return count / rate


def unload_hours(count: int, config: AppConfig) -> float:
    """Lossetid = antall fisk / pakkerate."""
    rate = config.station.pack_rate
    if rate <= 0:
        return 0.0
    return count / rate


# ----------------------------------------------------------------------------
# Baklengs tidsberegning for én tur
# ----------------------------------------------------------------------------

def compute_trip(trip: Trip, config: AppConfig, book: DistanceBook) -> TripSchedule:
    """Regn baklengs fra ankomst 06:15 på Process-dato gjennom alle stopp.

    Buffer trekker lastingen `buffer_hours` tidligere (slingringsmonn).
    """
    warnings: list[str] = []
    arr = config.station.arrival
    delivery = datetime.combine(trip.process_date, arr)

    sched = TripSchedule(
        trip=trip, boat=trip.boat, delivery=delivery,
        station_departure_clean=delivery,  # oppdateres til slutt
        warnings=warnings,
    )
    if not trip.stops:
        warnings.append("Turen har ingen stopp.")
        return sched

    buffer = timedelta(hours=max(0.0, config.plan.buffer_hours))

    # Vi bygger baklengs: start med ankomst-tidspunktet ved slakteriet og jobb
    # oss gjennom stoppene fra SISTE til FØRSTE.
    stop_scheds: list[StopSchedule] = []
    next_arrival = delivery  # "ankomst neste stopp" for det første baklengs-leddet er levering
    n = len(trip.stops)

    for i in range(n - 1, -1, -1):
        stop = trip.stops[i]
        if i == n - 1:
            # siste stopp -> seiler direkte til slakteriet
            nm = book.nm_to_station(stop.site_key)
            direct = book.direct_time_to_station(stop.site_key)
            if direct is not None:
                sail_h = direct
                leg_missing = False
            elif nm is not None:
                sail_h = sailing_hours(nm, trip.boat, config)
                leg_missing = False
            else:
                sail_h = 0.0
                leg_missing = True
                warnings.append(
                    f"Mangler avstand for lokalitet '{stop.site_name}' -> {config.station.name}. "
                    f"Seilingsledd satt til 0 t (ikke gjettet)."
                )
        else:
            # tidligere stopp -> seiler til neste stopp (annen lokalitet)
            next_stop = trip.stops[i + 1]
            nm = book.nm_between(stop.site_key, next_stop.site_key)
            if nm is None:
                sail_h = 0.0
                leg_missing = True
                warnings.append(
                    f"Mangler seilingsledd '{stop.site_name}' -> '{next_stop.site_name}'. "
                    f"Satt til 0 t (ikke gjettet) – legg inn avstanden manuelt."
                )
            else:
                sail_h = sailing_hours(nm, trip.boat, config)
                leg_missing = False

        departure = next_arrival - timedelta(hours=sail_h)
        load_finish = departure - buffer
        lt = load_hours(stop.count, trip.boat, config)
        load_start = load_finish - timedelta(hours=lt)
        arrival_stop = load_start

        stop_scheds.append(StopSchedule(
            site_key=stop.site_key, site_name=stop.site_name,
            arrival=arrival_stop, load_start=load_start, load_finish=load_finish,
            departure=departure, sailing_to_next_h=sail_h, leg_missing=leg_missing,
            count=stop.count, biomass_t=stop.biomass_t, holding_h=0.0,
        ))
        next_arrival = arrival_stop

    stop_scheds.reverse()  # tilbake til kronologisk rekkefølge (første -> siste)
    sched.stops = stop_scheds

    # Ren båt forlater slakteriet for å nå første stopp.
    first = stop_scheds[0]
    nm0 = book.nm_to_station(first.site_key)
    direct0 = book.direct_time_to_station(first.site_key)
    if direct0 is not None:
        back_h = direct0
    elif nm0 is not None:
        back_h = sailing_hours(nm0, trip.boat, config)
    else:
        back_h = 0.0
    sched.station_departure_clean = first.arrival - timedelta(hours=back_h)

    # Holdetid per stopp = fra ferdig lastet til slaktetidspunkt.
    slaughter_ref = delivery  # "arrival": slaktes ved ankomst 06:15 (oppdateres ev. etter kø)
    for s in stop_scheds:
        s.holding_h = (slaughter_ref - s.load_finish).total_seconds() / 3600.0

    return sched


# ----------------------------------------------------------------------------
# Kø på losseplassen (FIFO etter ankomst) – kun én båt om gangen
# ----------------------------------------------------------------------------

def apply_unloading_queue(schedules: list[TripSchedule], config: AppConfig) -> None:
    """Beregn losse-/vaskevindu med FIFO-kø. Muterer schedules in-place.

    Alle båter sikter mot ankomst 06:15. Kun én kan losse om gangen, så de
    danner kø. Lossing starter tidligst 06:15 og når forrige båt er ferdig.
    """
    if not config.station.single_unload:
        # parallell lossing – hver båt losser fra egen ankomst
        for s in schedules:
            _set_unload(s, s.delivery, config)
        return

    # Sorter FIFO etter ankomst (tie-break: båtnavn for determinisme).
    ordered = sorted(schedules, key=lambda s: (s.delivery, s.boat))
    # Kø per dag (man losser ikke på tvers av døgn i samme sekvens-buffer,
    # men vi lar køen flyte – forrige båt kan dytte neste utover).
    prev_end: dict[str, datetime] = {}  # nøkkel: dato (for å nullstille per dag)
    busy_until: Optional[datetime] = None
    last_day = None
    for s in ordered:
        day = s.delivery.date()
        if day != last_day:
            busy_until = None
            last_day = day
        start = s.delivery
        if busy_until is not None and busy_until > start:
            start = busy_until
        _set_unload(s, start, config)
        busy_until = s.unload_end

        wait_h = (start - s.delivery).total_seconds() / 3600.0
        if wait_h > config.plan.queue_tolerance_hours:
            s.warnings.append(
                f"Kø på losseplassen: lossing starter {start:%H:%M} "
                f"({wait_h:.1f} t etter 06:15-vinduet)."
            )

    # Oppdater holdetid hvis brukeren vil regne mot faktisk lossetidspunkt.
    if config.plan.slaughter_reference == "unload_end":
        for s in schedules:
            if s.unload_end is None:
                continue
            for st in s.stops:
                st.holding_h = (s.unload_end - st.load_finish).total_seconds() / 3600.0


def _set_unload(s: TripSchedule, start: datetime, config: AppConfig) -> None:
    uh = unload_hours(s.trip.total_count, config)
    s.unload_start = start
    s.unload_end = start + timedelta(hours=uh)
    s.wash_end = s.unload_end + timedelta(hours=config.station.wash_hours)


# ----------------------------------------------------------------------------
# Konfliktsjekk
# ----------------------------------------------------------------------------

@dataclass
class Conflict:
    kind: str          # maskinlesbar type
    severity: str      # "feil" | "advarsel"
    boat: Optional[str]
    process_date: Optional[str]
    message: str


def check_conflicts(schedules: list[TripSchedule], config: AppConfig) -> list[Conflict]:
    conflicts: list[Conflict] = []

    for s in schedules:
        boat = s.boat
        pd = s.trip.process_date.isoformat()
        b = config.boat(boat)

        # 1) Kapasitet (tonn ELLER antall)
        if b is not None:
            if s.trip.total_biomass_t > b.capacity_tonnes + 1e-9:
                conflicts.append(Conflict(
                    "kapasitet_tonn", "feil", boat, pd,
                    f"Last {s.trip.total_biomass_t:.1f} t over kapasitet "
                    f"({b.capacity_tonnes:.0f} t) for {boat}."))
            if s.trip.total_count > b.capacity_count:
                conflicts.append(Conflict(
                    "kapasitet_antall", "feil", boat, pd,
                    f"Last {s.trip.total_count} stk over kapasitet "
                    f"({b.capacity_count} stk) for {boat}."))
        else:
            conflicts.append(Conflict(
                "ukjent_baat", "advarsel", boat, pd,
                f"Båt '{boat}' finnes ikke i flåtekonfigurasjonen."))

        # 2) Ankomst i helg
        if s.delivery.weekday() >= 5:  # 5=lør, 6=søn
            conflicts.append(Conflict(
                "helg_levering", "feil", boat, pd,
                f"Levering {s.delivery:%a %d.%m} er i helg – ingen ankomst lør/søn."))

        # 3) Manglende avstand/ledd
        for st in s.stops:
            if st.leg_missing:
                conflicts.append(Conflict(
                    "mangler_avstand", "advarsel", boat, pd,
                    f"Stopp '{st.site_name}' mangler registrert seilingsavstand."))

        # 4) Maks holdetid (kun hvis bruker har satt grense)
        mh = config.plan.max_holding_hours
        if mh is not None:
            worst = max(s.stops, key=lambda x: x.holding_h, default=None)
            if worst is not None and worst.holding_h > mh + 1e-9:
                conflicts.append(Conflict(
                    "holdetid", "advarsel", boat, pd,
                    f"Holdetid {worst.holding_h:.1f} t (stopp '{worst.site_name}') "
                    f"over maks {mh:.1f} t."))

        # 5) Kø forbi 06:15-vindu (warnings fra kø-beregningen)
        for w in s.warnings:
            if w.startswith("Kø på losseplassen"):
                conflicts.append(Conflict("ko_losseplass", "advarsel", boat, pd, w))

    # 6) Båt to steder samtidig / ikke ferdig vasket før neste tur
    by_boat: dict[str, list[TripSchedule]] = {}
    for s in schedules:
        by_boat.setdefault(s.boat, []).append(s)
    for boat, lst in by_boat.items():
        lst = sorted(lst, key=lambda s: s.station_departure_clean)
        for a, b2 in zip(lst, lst[1:]):
            a_end = a.wash_end or a.unload_end or a.delivery
            if a_end > b2.station_departure_clean + timedelta(seconds=1):
                conflicts.append(Conflict(
                    "overlapp", "feil", boat, b2.trip.process_date.isoformat(),
                    f"{boat}: forrige tur ikke ferdig (klar/vasket {a_end:%d.%m %H:%M}) "
                    f"før neste tur starter ({b2.station_departure_clean:%d.%m %H:%M})."))

    return conflicts


def feasibility_pickup(s: TripSchedule, order_pickup_dates: dict[str, "datetime"]) -> list[Conflict]:
    """Sjekk at oppgitt hentedato er gjennomførbar (lasting rekker 06:15).

    order_pickup_dates: site_key -> tidligste foreslåtte hentedato (date som datetime).
    Flagger hvis faktisk nødvendig lasting-start er FØR foreslått hentedato.
    """
    out: list[Conflict] = []
    for st in s.stops:
        pickup = order_pickup_dates.get(st.site_key)
        if pickup is None:
            continue
        if st.load_start.date() < pickup.date():
            out.append(Conflict(
                "hentedato", "advarsel", s.boat, s.trip.process_date.isoformat(),
                f"Stopp '{st.site_name}': lasting må starte {st.load_start:%d.%m %H:%M}, "
                f"FØR foreslått hentedato {pickup:%d.%m}. Hentingen må starte tidligere."))
    return out
