"""Konfigurerbare standarder.

ALLE tall her er standarder som KAN endres i appen. Verdier merket
"MÅ VERIFISERES" er fornuftige antakelser, ikke fasit – bekreft før reell bruk.
Ingen tall er funnet på som "sannhet": de stammer fra kravspec eller er satt til
nøytrale verdier (f.eks. None) der bruker selv må oppgi tallet.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import time
from typing import Optional
import json


@dataclass
class BoatConfig:
    name: str
    type: str                     # "stor" | "liten"
    capacity_count: int           # maks antall fisk
    capacity_tonnes: float        # MÅ VERIFISERES: maks biomasse per last
    load_rate: float              # stk/t på lokaliteten (lasterate)
    speed_knots: float            # marsjfart (brukes kun hvis vi ikke bruker felles plan-fart)
    hired: bool = False           # innleid (f.eks. en 5. båt)
    active: bool = True


def default_boats() -> list[BoatConfig]:
    """Flåten fra kravspec. Kapasitet i tonn er MÅ VERIFISERES."""
    return [
        BoatConfig("Tauroa", "stor", 110_000, 600.0, 30_000, 13.0),
        BoatConfig("Tautiki", "stor", 110_000, 600.0, 30_000, 13.0),
        BoatConfig("Taupo", "liten", 40_000, 220.0, 8_000, 10.0),
        BoatConfig("Taupiri", "liten", 40_000, 220.0, 8_000, 10.0),
    ]


@dataclass
class StationConfig:
    name: str = "Jøsnøya"
    arrival: time = time(6, 15)   # båtene må være framme kl 06:15 (man–fre)
    pack_rate: float = 7000.0     # MÅ VERIFISERES: stk/t på pakkeriet (bestemmer lossetid)
    single_unload: bool = True    # kun én båt kan losse om gangen (FIFO)
    wash_hours: float = 4.0       # vask etter tømming


@dataclass
class PlanConfig:
    """Globale planleggingsparametre."""
    use_common_speed: bool = True            # felles plan-fart vs båtens marsjfart
    plan_speed_knots: float = 10.5           # MÅ VERIFISERES: felles planleggingsfart (~10–11 kn)
    buffer_hours: float = 0.0                # trekk lasting tidligere (bruker valgte: 0 = ingen)
    max_holding_hours: Optional[float] = None  # IKKE GJETTET – bruker må sette grensen selv
    # Toleranse før kø på losseplassen flagges som "forbi 06:15-vinduet" (timer).
    queue_tolerance_hours: float = 2.0       # MÅ VERIFISERES

    # Slaktetidspunkt brukt i holdetid-beregning: "arrival" = ankomst 06:15,
    # "unload_end" = når båten er ferdig losset (mer presist, men avhenger av kø).
    slaughter_reference: str = "arrival"


@dataclass
class AppConfig:
    boats: list[BoatConfig] = field(default_factory=default_boats)
    station: StationConfig = field(default_factory=StationConfig)
    plan: PlanConfig = field(default_factory=PlanConfig)

    # ---- serialisering (for lagring i SQLite/fil) ----
    def to_dict(self) -> dict:
        d = asdict(self)
        d["station"]["arrival"] = self.station.arrival.strftime("%H:%M")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        boats = [BoatConfig(**b) for b in d.get("boats", [])] or default_boats()
        st = dict(d.get("station", {}))
        if "arrival" in st and isinstance(st["arrival"], str):
            hh, mm = st["arrival"].split(":")
            st["arrival"] = time(int(hh), int(mm))
        station = StationConfig(**st) if st else StationConfig()
        plan = PlanConfig(**d.get("plan", {})) if d.get("plan") else PlanConfig()
        return cls(boats=boats, station=station, plan=plan)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "AppConfig":
        return cls.from_dict(json.loads(s))

    def boat(self, name: str) -> Optional[BoatConfig]:
        for b in self.boats:
            if b.name.lower() == (name or "").lower():
                return b
        return None
