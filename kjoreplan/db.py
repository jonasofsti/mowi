"""Lokal lagring i SQLite. Ingen skytjenester.

Lagrer konfigurasjon, importerte avstander/ledd og manuelle båttildelinger slik
at planen overlever omstart av appen.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from .config import AppConfig
from .models import Distance, InterSiteLeg

DEFAULT_DB = Path("kjoreplan.db")


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    _init(con)
    return con


def _init(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS distances (
            site_key TEXT, station TEXT, nm REAL, sailing_time_h REAL,
            PRIMARY KEY (site_key, station)
        );
        CREATE TABLE IF NOT EXISTS legs (
            from_key TEXT, to_key TEXT, nm REAL,
            PRIMARY KEY (from_key, to_key)
        );
        CREATE TABLE IF NOT EXISTS assignments (
            order_id TEXT PRIMARY KEY, boat TEXT, trip_seq INTEGER, stop_seq INTEGER
        );
        """
    )
    con.commit()


# ---- config ----
def save_config(con: sqlite3.Connection, cfg: AppConfig) -> None:
    con.execute("INSERT OR REPLACE INTO kv (key, value) VALUES ('config', ?)",
                (cfg.to_json(),))
    con.commit()


def load_config(con: sqlite3.Connection) -> AppConfig:
    row = con.execute("SELECT value FROM kv WHERE key='config'").fetchone()
    return AppConfig.from_json(row["value"]) if row else AppConfig()


# ---- avstander ----
def save_distances(con: sqlite3.Connection, distances: list[Distance]) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO distances (site_key, station, nm, sailing_time_h) VALUES (?,?,?,?)",
        [(d.site_key, d.station, d.nm, d.sailing_time_h) for d in distances],
    )
    con.commit()


def load_distances(con: sqlite3.Connection) -> list[Distance]:
    rows = con.execute("SELECT site_key, station, nm, sailing_time_h FROM distances").fetchall()
    return [Distance(r["site_key"], r["station"], r["nm"], r["sailing_time_h"]) for r in rows]


# ---- ledd ----
def save_legs(con: sqlite3.Connection, legs: list[InterSiteLeg]) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO legs (from_key, to_key, nm) VALUES (?,?,?)",
        [(lg.from_key, lg.to_key, lg.nm) for lg in legs],
    )
    con.commit()


def load_legs(con: sqlite3.Connection) -> list[InterSiteLeg]:
    rows = con.execute("SELECT from_key, to_key, nm FROM legs").fetchall()
    return [InterSiteLeg(r["from_key"], r["to_key"], r["nm"]) for r in rows]


def upsert_leg(con: sqlite3.Connection, from_key: str, to_key: str, nm: float) -> None:
    save_legs(con, [InterSiteLeg(from_key, to_key, nm)])


# ---- tildelinger ----
def save_assignments(con: sqlite3.Connection, assignments: dict[str, dict]) -> None:
    con.execute("DELETE FROM assignments")
    con.executemany(
        "INSERT INTO assignments (order_id, boat, trip_seq, stop_seq) VALUES (?,?,?,?)",
        [(oid, a.get("boat"), a.get("trip_seq", 0), a.get("stop_seq", 0))
         for oid, a in assignments.items()],
    )
    con.commit()


def load_assignments(con: sqlite3.Connection) -> dict[str, dict]:
    rows = con.execute("SELECT order_id, boat, trip_seq, stop_seq FROM assignments").fetchall()
    return {r["order_id"]: {"boat": r["boat"], "trip_seq": r["trip_seq"],
                            "stop_seq": r["stop_seq"]} for r in rows}
