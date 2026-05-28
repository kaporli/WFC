from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"


@dataclass
class BaseStats:
    health: float
    shield: float
    armor: float
    energy: float
    sprint: float


@dataclass
class AbilityRef:
    name: str
    slot: int
    strength_scaling: bool
    duration_scaling: bool
    range_scaling: bool
    efficiency_scaling: bool


@dataclass
class WarframeEntry:
    unique_name: str
    name: str
    base_stats: BaseStats
    polarities: list[str]
    aura: str | None
    abilities: list[AbilityRef]
    passive_description: str
    mastery_rank: int


@dataclass
class ModEffect:
    stat: str
    stack_type: str
    value_per_rank: float


@dataclass
class ModEntry:
    unique_name: str
    name: str
    polarity: str
    rarity: str
    max_rank: int
    type: str
    mod_set: str | None
    tradable: bool
    effects: list[ModEffect]
    raw_description: str


@dataclass
class ArcaneEffect:
    stat: str
    value: float
    at_max_rank: bool


@dataclass
class ArcaneEntry:
    unique_name: str
    name: str
    max_rank: int
    max_stacks: int
    trigger: str
    effects: list[ArcaneEffect]
    raw_description: str


def _load_json(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}. Run the pipeline first.")
    return json.loads(path.read_text())


def load_warframes() -> list[WarframeEntry]:
    return [
        WarframeEntry(
            unique_name=w["uniqueName"],
            name=w["name"],
            base_stats=BaseStats(**w["baseStats"]),
            polarities=w["polarities"],
            aura=w["aura"],
            abilities=[
                AbilityRef(
                    name=a["name"],
                    slot=a["slot"],
                    strength_scaling=a["strengthScaling"],
                    duration_scaling=a["durationScaling"],
                    range_scaling=a["rangeScaling"],
                    efficiency_scaling=a["efficiencyScaling"],
                )
                for a in w["abilities"]
            ],
            passive_description=w["passiveDescription"],
            mastery_rank=w["masteryRank"],
        )
        for w in _load_json("warframes.json")
    ]


def load_mods() -> list[ModEntry]:
    return [
        ModEntry(
            unique_name=m["uniqueName"],
            name=m["name"],
            polarity=m["polarity"],
            rarity=m["rarity"],
            max_rank=m["maxRank"],
            type=m["type"],
            mod_set=m["modSet"],
            tradable=m["tradable"],
            effects=[ModEffect(
                stat=e["stat"],
                stack_type=e["stackType"],
                value_per_rank=e["valuePerRank"],
            ) for e in m["effects"]],
            raw_description=m["rawDescription"],
        )
        for m in _load_json("mods.json")
    ]


def load_arcanes() -> list[ArcaneEntry]:
    return [
        ArcaneEntry(
            unique_name=a["uniqueName"],
            name=a["name"],
            max_rank=a["maxRank"],
            max_stacks=a["maxStacks"],
            trigger=a["trigger"],
            effects=[ArcaneEffect(
                stat=e["stat"],
                value=e["value"],
                at_max_rank=e["atMaxRank"],
            ) for e in a["effects"]],
            raw_description=a["rawDescription"],
        )
        for a in _load_json("arcanes.json")
    ]
