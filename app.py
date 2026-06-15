"""Streamlit-app: Kjøreplan for bløggebåter (Mowi, Jøsnøya).

Kjør lokalt:  streamlit run app.py
Alt lagres lokalt i kjoreplan.db (SQLite). Ingen skytjenester.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from kjoreplan import db, importers, planner
from kjoreplan.config import AppConfig
from kjoreplan.engine import (
    DistanceBook, compute_trip, apply_unloading_queue, check_conflicts,
    feasibility_pickup,
)
from kjoreplan.models import Distance, InterSiteLeg

st.set_page_config(page_title="Kjøreplan bløggebåter – Jøsnøya", layout="wide")


# ---------------------------------------------------------------- state / db
@st.cache_resource
def get_con():
    return db.connect()


con = get_con()

if "config" not in st.session_state:
    st.session_state.config = db.load_config(con)
if "orders" not in st.session_state:
    st.session_state.orders = []
if "assignments" not in st.session_state:
    st.session_state.assignments = {}

cfg: AppConfig = st.session_state.config

st.title("🐟 Kjøreplan for bløggebåter – Jøsnøya")
st.caption("Lokalt beslutningsstøtteverktøy. Standarder merket «må verifiseres» er antakelser – bekreft tallene.")

tabs = st.tabs(["1) Import", "2) Konfig", "3) Tildeling", "4) Kjøreplan & konflikter", "5) Eksport"])


# ============================================================ 1) IMPORT
with tabs[0]:
    st.header("Import")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Slakteplan (.xlsx)")
        f = st.file_uploader("Slakteplan", type=["xlsx", "xls"], key="up_plan")
        if f is not None and st.button("Les inn slakteplan"):
            orders, w = importers.read_slaughter_plan(f)
            st.session_state.orders = orders
            st.session_state.assignments = planner.default_assignments(orders)
            # ta vare på lagrede manuelle tildelinger der de finnes
            saved = db.load_assignments(con)
            for oid, a in saved.items():
                if oid in st.session_state.assignments:
                    st.session_state.assignments[oid] = a
            st.success(f"Leste {len(orders)} ordrer.")
            for msg in w:
                st.warning(msg)
        if st.session_state.orders:
            st.info(f"{len(st.session_state.orders)} ordrer i minnet.")

    with c2:
        st.subheader("Avstander lokalitet → slakteri (.xlsx)")
        fd = st.file_uploader("Avstander", type=["xlsx", "xls"], key="up_dist")
        if fd is not None and st.button("Les inn avstander"):
            dists, w = importers.read_distances(fd)
            db.save_distances(con, dists)
            st.success(f"Lagret {len(dists)} avstander.")
            for msg in w:
                st.warning(msg)

        st.subheader("Seilingsledd mellom lokaliteter (valgfritt)")
        fl = st.file_uploader("Fra | Til | N.M.", type=["xlsx", "xls"], key="up_legs")
        if fl is not None and st.button("Les inn seilingsledd"):
            legs, w = importers.read_inter_site_legs(fl)
            db.save_legs(con, legs)
            st.success(f"Lagret {len(legs)} ledd.")
            for msg in w:
                st.warning(msg)

    st.divider()
    st.subheader("Lagrede avstander og ledd")
    dists = db.load_distances(con)
    legs = db.load_legs(con)
    cc1, cc2 = st.columns(2)
    with cc1:
        st.write("**Avstander (lokalitet → slakteri)**")
        if dists:
            st.dataframe(pd.DataFrame([{"Lokalitet": d.site_key, "Slakteri": d.station,
                                        "N.M.": d.nm, "Seilingstid (t)": d.sailing_time_h}
                                       for d in dists]), use_container_width=True)
        else:
            st.caption("Ingen avstander lagret ennå.")
    with cc2:
        st.write("**Seilingsledd (manuell innlegging)**")
        if legs:
            st.dataframe(pd.DataFrame([{"Fra": l.from_key, "Til": l.to_key, "N.M.": l.nm}
                                       for l in legs]), use_container_width=True)
        with st.form("add_leg"):
            lf = st.text_input("Fra (lokalitet/kode)")
            lt = st.text_input("Til (lokalitet/kode)")
            lnm = st.number_input("N.M.", min_value=0.0, value=0.0, step=1.0)
            if st.form_submit_button("Legg til/oppdater ledd") and lf and lt:
                db.upsert_leg(con, lf.strip(), lt.strip(), float(lnm))
                st.success(f"Lagret ledd {lf} ↔ {lt} = {lnm} N.M.")
                st.rerun()


# ============================================================ 2) KONFIG
with tabs[1]:
    st.header("Konfigurasjon")
    st.caption("Alle verdier kan endres. Verdier under er standarder – «må verifiseres».")

    st.subheader("Flåte")
    boat_df = pd.DataFrame([{
        "Båt": b.name, "Type": b.type, "Kap. antall": b.capacity_count,
        "Maks tonn": b.capacity_tonnes, "Lasterate (stk/t)": b.load_rate,
        "Marsjfart (kn)": b.speed_knots, "Innleid": b.hired, "Aktiv": b.active,
    } for b in cfg.boats])
    edited = st.data_editor(boat_df, num_rows="dynamic", use_container_width=True, key="boat_ed")

    st.subheader("Slakteri & plan")
    c1, c2, c3 = st.columns(3)
    with c1:
        station_name = st.text_input("Slakteri", cfg.station.name)
        arrival = st.text_input("Ankomst (HH:MM)", cfg.station.arrival.strftime("%H:%M"))
        pack_rate = st.number_input("Pakkerate (stk/t)", value=float(cfg.station.pack_rate), step=500.0)
    with c2:
        wash = st.number_input("Vask (timer)", value=float(cfg.station.wash_hours), step=0.5)
        single = st.checkbox("Kun én båt losser om gangen", value=cfg.station.single_unload)
        use_common = st.checkbox("Bruk felles planleggingsfart", value=cfg.plan.use_common_speed)
    with c3:
        plan_speed = st.number_input("Plan-fart (knop)", value=float(cfg.plan.plan_speed_knots), step=0.5)
        buffer_h = st.number_input("Buffer (t) – trekk lasting tidligere", value=float(cfg.plan.buffer_hours), step=0.5)
        max_hold = st.number_input("Maks holdetid (t) – 0 = ingen grense",
                                   value=float(cfg.plan.max_holding_hours or 0.0), step=1.0)
        queue_tol = st.number_input("Kø-toleranse (t) før varsel", value=float(cfg.plan.queue_tolerance_hours), step=0.5)

    if st.button("Lagre konfigurasjon"):
        from kjoreplan.config import BoatConfig, StationConfig, PlanConfig
        from datetime import time as _time
        boats = []
        for _, r in edited.iterrows():
            if not str(r["Båt"]).strip():
                continue
            boats.append(BoatConfig(
                name=str(r["Båt"]), type=str(r["Type"]),
                capacity_count=int(r["Kap. antall"]), capacity_tonnes=float(r["Maks tonn"]),
                load_rate=float(r["Lasterate (stk/t)"]), speed_knots=float(r["Marsjfart (kn)"]),
                hired=bool(r["Innleid"]), active=bool(r["Aktiv"]),
            ))
        hh, mm = arrival.split(":")
        cfg.boats = boats
        cfg.station = StationConfig(name=station_name, arrival=_time(int(hh), int(mm)),
                                    pack_rate=pack_rate, single_unload=single, wash_hours=wash)
        cfg.plan = PlanConfig(use_common_speed=use_common, plan_speed_knots=plan_speed,
                              buffer_hours=buffer_h,
                              max_holding_hours=(max_hold if max_hold > 0 else None),
                              queue_tolerance_hours=queue_tol,
                              slaughter_reference=cfg.plan.slaughter_reference)
        st.session_state.config = cfg
        db.save_config(con, cfg)
        st.success("Konfigurasjon lagret.")


# ============================================================ 3) TILDELING
with tabs[2]:
    st.header("Tildeling av båter")
    if not st.session_state.orders:
        st.info("Importer en slakteplan først (fane 1).")
    else:
        st.caption("Forslaget fra slakteplanens «Boat» er forhåndsfylt. Overstyr fritt. "
                   "trip_seq grupperer turer; stop_seq bestemmer rekkefølgen på stoppene.")
        if st.button("🚀 Lag forslag automatisk (auto-tildeling)"):
            assigns, unassigned = planner.auto_assign(st.session_state.orders, cfg)
            st.session_state.assignments = assigns
            db.save_assignments(con, assigns)
            if unassigned:
                st.warning(f"{len(unassigned)} ordre fikk ikke plass (kapasitet) – fordel manuelt "
                           f"eller legg til en innleid båt i Konfig.")
            st.success("Auto-forslag laget. Overstyr ved behov under.")
            st.rerun()
        rows = []
        for o in st.session_state.orders:
            a = st.session_state.assignments.get(o.id, {})
            rows.append({
                "order_id": o.id,
                "Slaktedato": o.process_date.isoformat() if o.process_date else "",
                "Hentedato": o.pickup_date.isoformat() if o.pickup_date else "",
                "Lokalitet": o.site_name, "Merd": o.unit,
                "Antall": o.count, "Tonn": round(o.biomass_t, 1),
                "Båt": a.get("boat", "") or (o.proposed_boat or ""),
                "trip_seq": a.get("trip_seq", 0), "stop_seq": a.get("stop_seq", 0),
            })
        df = pd.DataFrame(rows)
        boat_names = [b.name for b in cfg.boats]
        edited = st.data_editor(
            df, use_container_width=True, key="assign_ed",
            column_config={
                "Båt": st.column_config.SelectboxColumn(options=[""] + boat_names),
                "order_id": st.column_config.TextColumn(disabled=True),
            },
            disabled=["Slaktedato", "Hentedato", "Lokalitet", "Merd", "Antall", "Tonn"],
        )
        if st.button("Lagre tildeling"):
            for _, r in edited.iterrows():
                st.session_state.assignments[r["order_id"]] = {
                    "boat": str(r["Båt"]).strip(),
                    "trip_seq": int(r["trip_seq"]), "stop_seq": int(r["stop_seq"]),
                }
            db.save_assignments(con, st.session_state.assignments)
            st.success("Tildeling lagret.")


# ============================================================ 4) KJØREPLAN
def compute_all():
    dists = db.load_distances(con)
    legs = db.load_legs(con)
    book = DistanceBook(dists, legs, station=cfg.station.name)
    trips = planner.build_trips(st.session_state.orders, st.session_state.assignments)
    scheds = [compute_trip(t, cfg, book) for t in trips]
    apply_unloading_queue(scheds, cfg)
    conflicts = check_conflicts(scheds, cfg)
    # hentedato-gjennomførbarhet
    pickup_by_site = {}
    for o in st.session_state.orders:
        if o.pickup_date:
            cur = pickup_by_site.get(o.site_key)
            pdt = datetime.combine(o.pickup_date, datetime.min.time())
            if cur is None or pdt < cur:
                pickup_by_site[o.site_key] = pdt
    for s in scheds:
        conflicts.extend(feasibility_pickup(s, pickup_by_site))
    return scheds, conflicts


with tabs[3]:
    st.header("Kjøreplan & konflikter")
    if not st.session_state.orders:
        st.info("Importer en slakteplan først (fane 1).")
    else:
        scheds, conflicts = compute_all()
        from kjoreplan.export import grid_dataframe, detail_dataframe
        st.subheader("Rutenett (rader = dato, kolonner = båt)")
        st.dataframe(grid_dataframe(scheds, cfg), use_container_width=True)

        st.subheader("Tidslinje / Gantt per båt")
        gantt_rows = []
        for s in scheds:
            for st_ in s.stops:
                gantt_rows.append({"Båt": s.boat, "Aktivitet": f"Last {st_.site_name}",
                                   "Start": st_.load_start, "Slutt": st_.load_finish})
            gantt_rows.append({"Båt": s.boat, "Aktivitet": "Ved slakteri (loss+vask)",
                               "Start": s.unload_start or s.delivery,
                               "Slutt": s.wash_end or s.delivery})
        if gantt_rows:
            gdf = pd.DataFrame(gantt_rows)
            try:
                import altair as alt
                chart = alt.Chart(gdf).mark_bar().encode(
                    x="Start:T", x2="Slutt:T", y="Båt:N",
                    color="Aktivitet:N",
                    tooltip=["Båt", "Aktivitet", "Start", "Slutt"],
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
            except Exception:
                st.dataframe(gdf, use_container_width=True)

        st.subheader("Detaljert tidsplan")
        st.dataframe(detail_dataframe(scheds), use_container_width=True)

        st.subheader("Advarsler / konflikter")
        if conflicts:
            errs = [c for c in conflicts if c.severity == "feil"]
            warns = [c for c in conflicts if c.severity != "feil"]
            if errs:
                st.error(f"{len(errs)} feil")
            if warns:
                st.warning(f"{len(warns)} advarsler")
            st.dataframe(pd.DataFrame([{
                "Alvor": c.severity, "Type": c.kind, "Båt": c.boat,
                "Dato": c.process_date, "Melding": c.message} for c in conflicts]),
                use_container_width=True)
        else:
            st.success("Ingen konflikter funnet.")


# ============================================================ 5) EKSPORT
with tabs[4]:
    st.header("Eksport til Excel")
    if not st.session_state.orders:
        st.info("Importer en slakteplan først (fane 1).")
    else:
        scheds, conflicts = compute_all()
        from kjoreplan.export import export_excel
        data = export_excel(scheds, conflicts, cfg)
        st.download_button("⬇️ Last ned kjøreplan (.xlsx)", data=data,
                           file_name="kjoreplan.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("Arkene: Kjøreplan (rutenett), Detaljer (per stopp), Konflikter.")
