"""Robust import fra Excel: slakteplan, avstander og seilingsledd.

Importen tåler rotete kolonnenavn og varierende rekkefølge ved å normalisere
overskrifter og matche mot kjente aliaser.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

import pandas as pd

from .models import SlaughterOrder, Distance, InterSiteLeg


# ---- kolonne-aliaser for slakteplanen (engelske overskrifter slik de kommer) ----
SLAUGHTER_ALIASES: dict[str, list[str]] = {
    "id": ["id", "slakteordre", "order id", "ordre"],
    "process": ["process", "process date", "slaktedato", "slakt"],
    "boat": ["boat", "båt", "baat"],
    "euth": ["euth.", "euth", "bløgget", "blogget", "avlivet"],
    "pickup": ["pickup time", "pickup", "hentedato", "hentetid", "pick up time"],
    "site": ["site", "lokalitet", "location"],
    "unit": ["unit", "merd", "enhet"],
    "count": ["count", "antall", "antall fisk", "fish count"],
    "avg_weight": ["avg. weight", "avg weight", "snittvekt", "average weight", "avg.weight"],
    "biomass": ["biomass", "biomasse"],
    "station": ["packing station", "slakteri", "packing", "station"],
}


def _norm_header(h) -> str:
    return re.sub(r"\s+", " ", str(h).strip().lower())


def _build_colmap(columns, aliases: dict[str, list[str]]) -> dict[str, str]:
    """Map logisk felt -> faktisk kolonnenavn i arket."""
    norm = {_norm_header(c): c for c in columns}
    out: dict[str, str] = {}
    for field, alts in aliases.items():
        for a in alts:
            if a in norm:
                out[field] = norm[a]
                break
        else:
            # delvis match (f.eks. "avg. weight (g)")
            for nkey, orig in norm.items():
                if any(nkey.startswith(a) or a in nkey for a in alts):
                    out[field] = orig
                    break
    return out


_CODE_RE = re.compile(r"\(([^)]+)\)\s*$")


def split_site(raw) -> tuple[str, Optional[str]]:
    """'Grøttingsøya (BDB)' -> ('Grøttingsøya (BDB)', 'BDB')."""
    s = str(raw).strip()
    m = _CODE_RE.search(s)
    code = m.group(1).strip() if m else None
    return s, code


def _to_date(v) -> Optional[date]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    ts = pd.to_datetime(v, dayfirst=True, errors="coerce")
    return None if pd.isna(ts) else ts.date()


def _to_float(v, default=0.0) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return default


def _to_int(v, default=0) -> int:
    return int(round(_to_float(v, default)))


def read_slaughter_plan(path_or_buf, sheet_name=0) -> tuple[list[SlaughterOrder], list[str]]:
    """Les slakteplan fra Excel. Returnerer (ordrer, advarsler)."""
    warnings: list[str] = []
    df = pd.read_excel(path_or_buf, sheet_name=sheet_name)
    df = df.dropna(how="all")
    colmap = _build_colmap(df.columns, SLAUGHTER_ALIASES)

    required = ["id", "process", "site", "count"]
    missing = [r for r in required if r not in colmap]
    if missing:
        warnings.append(f"Mangler nødvendige kolonner: {', '.join(missing)}.")

    orders: list[SlaughterOrder] = []
    for idx, row in df.iterrows():
        def get(field):
            col = colmap.get(field)
            return row[col] if col is not None else None

        site_raw = get("site")
        if site_raw is None or (isinstance(site_raw, float) and pd.isna(site_raw)):
            continue
        site_name, site_code = split_site(site_raw)
        count = _to_int(get("count"))
        avg_w = _to_float(get("avg_weight"))
        biomass = _to_float(get("biomass"))
        # Avled biomasse hvis den mangler men vi har antall + snittvekt (gram -> tonn).
        if biomass <= 0 and count > 0 and avg_w > 0:
            biomass = count * avg_w / 1_000_000.0

        oid = get("id")
        oid = str(oid).strip() if oid is not None and not (isinstance(oid, float) and pd.isna(oid)) else f"rad{idx}"

        orders.append(SlaughterOrder(
            id=oid,
            process_date=_to_date(get("process")),
            proposed_boat=(str(get("boat")).strip() if get("boat") is not None
                           and not (isinstance(get("boat"), float) and pd.isna(get("boat"))) else None),
            euth=(str(get("euth")).strip() if get("euth") is not None else None),
            pickup_date=_to_date(get("pickup")),
            site_name=site_name, site_code=site_code,
            unit=(str(get("unit")).strip() if get("unit") is not None else ""),
            count=count, avg_weight_g=avg_w, biomass_t=biomass,
            packing_station=(str(get("station")).strip() if get("station") is not None else "Jøsnøya"),
        ))

    if not orders:
        warnings.append("Fant ingen gyldige rader i slakteplanen.")
    return orders, warnings


# ---- avstander ----
DIST_ALIASES = {
    "site": ["lokalitet", "site", "location"],
    "nm": ["n.m.", "nm", "nautiske mil", "nautical miles", "distance"],
    "time": ["seilingstid", "sailing time", "tid"],
}


def _read_distances_value_layout(df, norm, site_col, station_default) -> list[Distance]:
    """Parse layout med «Slakteri | N.M. | … | Seilingstid»-blokker per rad.

    Slakteriet ligger i en verdikolonne (Herøy/Ulvan/Jøsnøya). Vi parer hver
    Slakteri-kolonne med tilhørende N.M.- og Seilingstid-kolonne (samme suffiks),
    og lager én Distance per (lokalitet, slakteri).
    """
    # finn suffikser ('', '.1', '.2', ...) for Slakteri-kolonnene
    out: list[Distance] = []
    suffixes = []
    for c in norm:
        if c == "slakteri":
            suffixes.append("")
        elif c.startswith("slakteri."):
            suffixes.append(c[len("slakteri"):])  # '.1', '.2'
    pairs = []
    for suf in suffixes:
        scol = norm.get("slakteri" + suf)
        ncol = norm.get("n.m." + suf) or norm.get("nm" + suf)
        tcol = norm.get("seilingstid" + suf)
        if scol and ncol:
            pairs.append((scol, ncol, tcol))
    for _, row in df.iterrows():
        raw_site = row[site_col]
        if raw_site is None or (isinstance(raw_site, float) and pd.isna(raw_site)):
            continue
        site_name, code = split_site(raw_site)
        key = (code or site_name).strip()
        for scol, ncol, tcol in pairs:
            station = row[scol]
            if station is None or (isinstance(station, float) and pd.isna(station)):
                continue
            nm = _to_float(row[ncol], default=-1)
            if nm < 0:
                continue
            t = _to_float(row[tcol], default=0) if tcol else 0
            out.append(Distance(site_key=key, station=str(station).strip(), nm=nm,
                                sailing_time_h=(t if t and t > 0 else None)))
    return out


def read_distances(path_or_buf, sheet_name=0, station_default="Jøsnøya") -> tuple[list[Distance], list[str]]:
    """Les avstander. Støtter både smalt ark (Lokalitet|N.M.|Seilingstid) og
    bredt ark med kolonner per slakteri (Herøy/Ulvan/Jøsnøya)."""
    warnings: list[str] = []
    df = pd.read_excel(path_or_buf, sheet_name=sheet_name)
    df = df.dropna(how="all")
    norm = {_norm_header(c): c for c in df.columns}

    site_col = None
    for a in DIST_ALIASES["site"]:
        if a in norm:
            site_col = norm[a]
            break
    if site_col is None:
        warnings.append("Fant ikke lokalitet-kolonne i avstandsarket.")
        return [], warnings

    # Layout der slakteriet står i VERDI-kolonner (gjentatte «Slakteri | N.M. |
    # ... | Seilingstid»-blokker per slakteri), ikke som kolonneoverskrift.
    if any(c == "slakteri" or c.startswith("slakteri.") for c in norm):
        return _read_distances_value_layout(df, norm, site_col, station_default), warnings

    # Finn slakteri-kolonner (bredt format): kolonner som matcher kjente slakterier.
    station_cols = {c: orig for c, orig in norm.items()
                    if c in ("jøsnøya", "josnoya", "jösnöya", "ulvan", "herøy", "heroy")}

    out: list[Distance] = []
    if station_cols:
        for _, row in df.iterrows():
            site_name, code = split_site(row[site_col])
            key = (code or site_name).strip()
            for ncol, orig in station_cols.items():
                nm = _to_float(row[orig], default=-1)
                if nm >= 0:
                    out.append(Distance(site_key=key, station=orig, nm=nm))
    else:
        nm_col = next((norm[a] for a in DIST_ALIASES["nm"] if a in norm), None)
        time_col = next((norm[a] for a in DIST_ALIASES["time"] if a in norm), None)
        if nm_col is None and time_col is None:
            warnings.append("Fant verken N.M.- eller seilingstid-kolonne.")
            return out, warnings
        for _, row in df.iterrows():
            site_name, code = split_site(row[site_col])
            key = (code or site_name).strip()
            nm = _to_float(row[nm_col]) if nm_col else 0.0
            t = _to_float(row[time_col]) if time_col else None
            out.append(Distance(site_key=key, station=station_default, nm=nm,
                                sailing_time_h=(t if t and t > 0 else None)))
    if not out:
        warnings.append("Fant ingen avstandsrader.")
    return out, warnings


# ---- seilingsledd mellom lokaliteter ----
LEG_ALIASES = {
    "from": ["fra", "from", "fra lokalitet", "from site"],
    "to": ["til", "to", "til lokalitet", "to site"],
    "nm": ["n.m.", "nm", "nautiske mil", "distance"],
}


def read_inter_site_legs(path_or_buf, sheet_name=0) -> tuple[list[InterSiteLeg], list[str]]:
    """Les fra/til-tabell med seilingsledd mellom lokaliteter."""
    warnings: list[str] = []
    df = pd.read_excel(path_or_buf, sheet_name=sheet_name)
    df = df.dropna(how="all")
    norm = {_norm_header(c): c for c in df.columns}
    fcol = next((norm[a] for a in LEG_ALIASES["from"] if a in norm), None)
    tcol = next((norm[a] for a in LEG_ALIASES["to"] if a in norm), None)
    ncol = next((norm[a] for a in LEG_ALIASES["nm"] if a in norm), None)
    if not (fcol and tcol and ncol):
        warnings.append("Seilingsledd-ark må ha kolonnene Fra | Til | N.M.")
        return [], warnings
    out: list[InterSiteLeg] = []
    for _, row in df.iterrows():
        _, fcode = split_site(row[fcol])
        _, tcode = split_site(row[tcol])
        fk = (fcode or str(row[fcol])).strip()
        tk = (tcode or str(row[tcol])).strip()
        nm = _to_float(row[ncol], default=-1)
        if nm >= 0 and fk and tk:
            out.append(InterSiteLeg(from_key=fk, to_key=tk, nm=nm))
    return out, warnings
