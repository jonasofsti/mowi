"""Enhetstester for beregningsmotoren (baklengs tid, kø, konflikter).

Kjør:  python -m pytest tests/ -q   (eller: python tests/test_engine.py)
Avhenger kun av stdlib (ikke pandas), så den kan kjøres uten Excel-stack.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kjoreplan.config import AppConfig
from kjoreplan.models import Trip, Stop, Distance, InterSiteLeg
from kjoreplan.engine import (
    DistanceBook, compute_trip, apply_unloading_queue, check_conflicts,
)

TUE = date(2026, 6, 16)  # tirsdag


def base_config() -> AppConfig:
    cfg = AppConfig()
    cfg.plan.use_common_speed = True
    cfg.plan.plan_speed_knots = 10.5
    cfg.plan.buffer_hours = 0.0
    return cfg


def test_single_stop_backward():
    cfg = base_config()
    book = DistanceBook([Distance("A", "Jøsnøya", nm=21.0)], [])
    trip = Trip(boat="Tautiki", process_date=TUE,
                stops=[Stop("A", "Lok A", count=30_000, biomass_t=120.0)])
    s = compute_trip(trip, cfg, book)
    st = s.stops[0]
    assert s.delivery == datetime(2026, 6, 16, 6, 15)
    # 21 nm / 10.5 kn = 2.0 t seiling
    assert st.departure == datetime(2026, 6, 16, 4, 15)
    assert st.load_finish == datetime(2026, 6, 16, 4, 15)
    # 30000 / 30000 stk/t = 1.0 t lasting
    assert st.load_start == datetime(2026, 6, 16, 3, 15)
    assert s.station_departure_clean == datetime(2026, 6, 16, 1, 15)
    assert abs(st.holding_h - 2.0) < 1e-6


def test_two_stops_first_has_longest_holding():
    cfg = base_config()
    book = DistanceBook(
        distances=[Distance("M", "Jøsnøya", 42.0), Distance("G", "Jøsnøya", 21.0)],
        legs=[InterSiteLeg("M", "G", 10.5)],
    )
    trip = Trip(boat="Tautiki", process_date=TUE, stops=[
        Stop("M", "Mannbruholmen", count=30_000, biomass_t=120.0),
        Stop("G", "Grøttingsøya", count=30_000, biomass_t=120.0),
    ])
    s = compute_trip(trip, cfg, book)
    m, g = s.stops
    # G: 21/10.5 = 2.0 -> avgang 04:15, last 03:15-04:15
    assert g.load_finish == datetime(2026, 6, 16, 4, 15)
    # M->G: 10.5/10.5 = 1.0 -> avgang M 03:15-1=02:15, last 01:15-02:15
    assert m.load_finish == datetime(2026, 6, 16, 2, 15)
    # ren båt ut: 42/10.5 = 4.0 før ankomst M 01:15 -> 21:15 dagen før
    assert s.station_departure_clean == datetime(2026, 6, 15, 21, 15)
    # første stopp (M) har lengst holdetid
    assert m.holding_h > g.holding_h
    assert abs(m.holding_h - 4.0) < 1e-6
    assert abs(g.holding_h - 2.0) < 1e-6


def test_missing_leg_warns_and_no_guess():
    cfg = base_config()
    book = DistanceBook([Distance("G", "Jøsnøya", 21.0)], [])  # M->G mangler, M->station mangler
    trip = Trip(boat="Tautiki", process_date=TUE, stops=[
        Stop("M", "Mannbruholmen", count=30_000, biomass_t=120.0),
        Stop("G", "Grøttingsøya", count=30_000, biomass_t=120.0),
    ])
    s = compute_trip(trip, cfg, book)
    assert any("Mangler seilingsledd" in w for w in s.warnings)
    assert s.stops[0].leg_missing is True  # M->G mangler


def test_capacity_conflict():
    cfg = base_config()
    book = DistanceBook([Distance("A", "Jøsnøya", 21.0)], [])
    trip = Trip(boat="Taupo", process_date=TUE,  # liten: 40k / 220 t
                stops=[Stop("A", "Lok A", count=50_000, biomass_t=300.0)])
    s = compute_trip(trip, cfg, book)
    apply_unloading_queue([s], cfg)
    conflicts = check_conflicts([s], cfg)
    kinds = {c.kind for c in conflicts}
    assert "kapasitet_antall" in kinds
    assert "kapasitet_tonn" in kinds


def test_weekend_delivery_conflict():
    cfg = base_config()
    book = DistanceBook([Distance("A", "Jøsnøya", 21.0)], [])
    sat = date(2026, 6, 20)  # lørdag
    trip = Trip(boat="Tautiki", process_date=sat,
                stops=[Stop("A", "Lok A", count=30_000, biomass_t=120.0)])
    s = compute_trip(trip, cfg, book)
    apply_unloading_queue([s], cfg)
    conflicts = check_conflicts([s], cfg)
    assert any(c.kind == "helg_levering" for c in conflicts)


def test_unloading_queue_fifo():
    cfg = base_config()
    book = DistanceBook([Distance("A", "Jøsnøya", 21.0)], [])
    t1 = Trip(boat="Tauroa", process_date=TUE, stops=[Stop("A", "A", count=30_000, biomass_t=120.0)])
    t2 = Trip(boat="Tautiki", process_date=TUE, stops=[Stop("A", "A", count=30_000, biomass_t=120.0)])
    s1 = compute_trip(t1, cfg, book)
    s2 = compute_trip(t2, cfg, book)
    apply_unloading_queue([s1, s2], cfg)
    # begge ankommer 06:15; én losser av gangen -> andre starter når første er ferdig
    first, second = sorted([s1, s2], key=lambda s: s.unload_start)
    assert second.unload_start >= first.unload_end - timedelta(seconds=1)
    # 30000 / 7000 = ~4.2857 t lossing
    assert abs((first.unload_end - first.unload_start).total_seconds() / 3600 - 30000 / 7000) < 1e-6


def test_holding_breach_only_when_set():
    cfg = base_config()
    book = DistanceBook([Distance("A", "Jøsnøya", 21.0)], [])
    trip = Trip(boat="Tautiki", process_date=TUE,
                stops=[Stop("A", "Lok A", count=30_000, biomass_t=120.0)])
    s = compute_trip(trip, cfg, book)
    apply_unloading_queue([s], cfg)
    # ingen grense satt -> ingen holdetid-konflikt
    assert not any(c.kind == "holdetid" for c in check_conflicts([s], cfg))
    # sett en lav grense -> konflikt
    cfg.plan.max_holding_hours = 1.0
    assert any(c.kind == "holdetid" for c in check_conflicts([s], cfg))


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} tester bestått.")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
