"""Bygg båtturer fra ordrer + tildelinger.

En tildeling per ordre: {boat, trip_seq, stop_seq}. Ordrer med samme
(boat, process_date, trip_seq) blir én tur; ordrer med samme lokalitet i samme
tur slås sammen til ett stopp (kun mer lastetid, ingen ekstra seiling).
stop_seq bestemmer rekkefølgen på stoppene (rekkefølgen endres ikke stille).
"""
from __future__ import annotations

from collections import defaultdict

from .models import SlaughterOrder, Trip, Stop


def default_assignments(orders: list[SlaughterOrder]) -> dict[str, dict]:
    """Startforslag: godta Boat fra slakteplanen; én tur per (båt, hentedato).

    Stopprekkefølge følger hentedato/ordre slik den kommer (kan overstyres).
    """
    assigns: dict[str, dict] = {}
    # grupper for å gi stabile trip_seq per (boat, process_date)
    trip_index: dict[tuple, int] = {}
    for o in orders:
        boat = o.proposed_boat or ""
        assigns[o.id] = {"boat": boat, "trip_seq": 0, "stop_seq": 0}
    return assigns


def auto_assign(orders: list[SlaughterOrder], config) -> tuple[dict[str, dict], list[SlaughterOrder]]:
    """Auto-forslag: pakk ordrer i båter per slaktedato (greedy).

    Store båter fylles først; én tur per båt per dag; én lokalitet per tur (slik
    trengs ingen seilingsledd). Returnerer (tildelinger, ufordelte ordrer).
    Forslaget er ment å overstyres fritt.
    """
    assigns: dict[str, dict] = {o.id: {"boat": "", "trip_seq": 0, "stop_seq": 0} for o in orders}
    unassigned: list[SlaughterOrder] = []

    by_date: dict = defaultdict(list)
    for o in orders:
        by_date[o.process_date].append(o)

    for pdate in sorted(by_date, key=lambda d: (d is None, d)):
        day_orders = sorted(by_date[pdate], key=lambda o: o.biomass_t, reverse=True)
        boats = sorted([b for b in config.boats if b.active],
                       key=lambda b: (b.capacity_tonnes, b.capacity_count), reverse=True)
        # arbeidskopi: én "tur" per båt denne dagen
        state = [{"name": b.name, "capT": b.capacity_tonnes, "capC": b.capacity_count,
                  "site": None, "usedT": 0.0, "usedC": 0} for b in boats]

        def norm(s):
            return (s or "").strip().lower()

        for o in day_orders:
            target = None
            prop = (o.proposed_boat or "").strip()
            if prop:
                pb = next((s for s in state if s["name"].lower() == prop.lower()), None)
                if pb and (pb["site"] is None or norm(pb["site"]) == norm(o.site_key)) \
                        and pb["usedT"] + o.biomass_t <= pb["capT"] + 1e-9 \
                        and pb["usedC"] + o.count <= pb["capC"]:
                    target = pb
            if target is None:
                target = next((s for s in state if s["site"] is not None
                               and norm(s["site"]) == norm(o.site_key)
                               and s["usedT"] + o.biomass_t <= s["capT"] + 1e-9
                               and s["usedC"] + o.count <= s["capC"]), None)
            if target is None:
                target = next((s for s in state if s["site"] is None
                               and o.biomass_t <= s["capT"] + 1e-9
                               and o.count <= s["capC"]), None)
            if target is not None:
                if target["site"] is None:
                    target["site"] = o.site_key
                target["usedT"] += o.biomass_t
                target["usedC"] += o.count
                assigns[o.id] = {"boat": target["name"], "trip_seq": 0, "stop_seq": 0}
            else:
                unassigned.append(o)

    return assigns, unassigned


def build_trips(orders: list[SlaughterOrder], assignments: dict[str, dict]) -> list[Trip]:
    by_order = {o.id: o for o in orders}

    # grupper ordrer per (boat, process_date, trip_seq)
    groups: dict[tuple, list[SlaughterOrder]] = defaultdict(list)
    for oid, a in assignments.items():
        o = by_order.get(oid)
        if o is None:
            continue
        boat = (a.get("boat") or "").strip()
        if not boat:
            continue  # ikke tildelt – hopp over (vises som "ufordelt" i UI)
        key = (boat, o.process_date, a.get("trip_seq", 0))
        groups[key].append(o)

    trips: list[Trip] = []
    for (boat, pdate, tseq), group in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2])):
        # stopprekkefølge fra stop_seq, deretter site
        stops_by_site: dict[str, Stop] = {}
        site_order: dict[str, int] = {}
        for o in group:
            sa = assignments[o.id]
            sk = o.site_key
            if sk not in stops_by_site:
                stops_by_site[sk] = Stop(site_key=sk, site_name=o.site_name)
                site_order[sk] = sa.get("stop_seq", 0)
            st = stops_by_site[sk]
            st.order_ids.append(o.id)
            st.count += o.count
            st.biomass_t += o.biomass_t
            # behold laveste stop_seq for lokaliteten
            site_order[sk] = min(site_order[sk], sa.get("stop_seq", 0))

        ordered_stops = [stops_by_site[sk] for sk in
                         sorted(stops_by_site, key=lambda k: (site_order[k], k))]
        trips.append(Trip(boat=boat, process_date=pdate, stops=ordered_stops, trip_id=tseq))
    return trips
