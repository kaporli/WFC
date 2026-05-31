from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_json(filename: str) -> list | dict:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Run the pipeline first: {path}")
    return json.loads(path.read_text())


# ── Warframes ─────────────────────────────────────────────────────────────────

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
    aura_slots: int
    abilities: list[AbilityRef]
    passive_description: str
    mastery_rank: int
    initial_energy: float
    exilus_polarity: str | None


def load_warframes() -> list[WarframeEntry]:
    return [
        WarframeEntry(
            unique_name=w["uniqueName"],
            name=w["name"],
            base_stats=BaseStats(**w["baseStats"]),
            polarities=w["polarities"],
            aura=w["aura"],
            aura_slots=w.get("auraSlots", 1),
            abilities=[
                AbilityRef(
                    name=a["name"], slot=a["slot"],
                    strength_scaling=a["strengthScaling"],
                    duration_scaling=a["durationScaling"],
                    range_scaling=a["rangeScaling"],
                    efficiency_scaling=a["efficiencyScaling"],
                )
                for a in w["abilities"]
            ],
            passive_description=w["passiveDescription"],
            mastery_rank=w["masteryRank"],
            initial_energy=w.get("initialEnergy", w["baseStats"]["energy"] / 4),
            exilus_polarity=w.get("exilusPolarity"),
        )
        for w in _load_json("warframes.json")
    ]


# ── Mods ──────────────────────────────────────────────────────────────────────

@dataclass
class ModEffect:
    stat: str
    stack_type: str
    level_values: list[float]
    target: str


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
    is_augment: bool
    compat_name: str | None
    set_multipliers: list[float]   # [bonus_at_2_pieces, bonus_at_3_pieces, ...]
    effects: list[ModEffect]
    raw_description: str


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
            is_augment=m.get("isAugment", False),
            compat_name=m.get("compatName"),
            set_multipliers=m.get("setMultipliers", []),
            effects=[
                ModEffect(
                    stat=e["stat"],
                    stack_type=e["stackType"],
                    level_values=e["levelValues"],
                    target=e.get("target", "self"),
                )
                for e in m["effects"]
            ],
            raw_description=m["rawDescription"],
        )
        for m in _load_json("mods.json")
    ]


# ── Arcanes ───────────────────────────────────────────────────────────────────

@dataclass
class ArcaneEffect:
    stat: str
    level_values: list[float]


@dataclass
class ArcaneEntry:
    unique_name: str
    name: str
    max_rank: int
    max_stacks: int
    trigger: str
    effects: list[ArcaneEffect]
    raw_description: str


def load_arcanes() -> list[ArcaneEntry]:
    return [
        ArcaneEntry(
            unique_name=a["uniqueName"],
            name=a["name"],
            max_rank=a["maxRank"],
            max_stacks=a["maxStacks"],
            trigger=a["trigger"],
            effects=[
                ArcaneEffect(stat=e["stat"], level_values=e["levelValues"])
                for e in a["effects"]
            ],
            raw_description=a["rawDescription"],
        )
        for a in _load_json("arcanes.json")
    ]


# ── Weapons ───────────────────────────────────────────────────────────────────

@dataclass
class WeaponStats:
    total_damage: float
    damage_types: dict[str, float]
    crit_chance: float
    crit_multiplier: float
    status_chance: float
    fire_rate: float
    magazine_size: int
    reload_time: float
    multishot: float
    range: float | None
    attack_speed: float | None
    combo_duration: float | None
    heavy_attack_damage: float | None


@dataclass
class WeaponEntry:
    unique_name: str
    name: str
    type: str
    slot: int
    base_stats: WeaponStats
    disposition: int
    mastery_rank: int


def load_weapons() -> list[WeaponEntry]:
    def parse_stats(s: dict) -> WeaponStats:
        return WeaponStats(
            total_damage=s["totalDamage"],
            damage_types=s["damageTypes"],
            crit_chance=s["critChance"],
            crit_multiplier=s["critMultiplier"],
            status_chance=s["statusChance"],
            fire_rate=s["fireRate"],
            magazine_size=s["magazineSize"],
            reload_time=s["reloadTime"],
            multishot=s["multishot"],
            range=s.get("range"),
            attack_speed=s.get("attackSpeed"),
            combo_duration=s.get("comboDuration"),
            heavy_attack_damage=s.get("heavyAttackDamage"),
        )
    return [
        WeaponEntry(
            unique_name=w["uniqueName"],
            name=w["name"],
            type=w["type"],
            slot=w.get("slot", 0),
            base_stats=parse_stats(w["baseStats"]),
            disposition=w["disposition"],
            mastery_rank=w["masteryRank"],
        )
        for w in _load_json("weapons.json")
    ]


# ── Arcane Helmets ────────────────────────────────────────────────────────────

@dataclass
class ArcaneHelmetEffect:
    stat: str
    value: float
    is_flat: bool


@dataclass
class ArcaneHelmetEntry:
    unique_name: str
    name: str
    warframe_name: str
    effects: list[ArcaneHelmetEffect]


def load_helmets() -> list[ArcaneHelmetEntry]:
    data = _load_json("helmets.json")
    if not isinstance(data, list):
        return []
    return [
        ArcaneHelmetEntry(
            unique_name=h["uniqueName"],
            name=h["name"],
            warframe_name=h["warframeName"],
            effects=[
                ArcaneHelmetEffect(stat=e["stat"], value=e["value"], is_flat=e["isFlat"])
                for e in h.get("effects", [])
            ],
        )
        for h in data
    ]


# ── Mod Sets ──────────────────────────────────────────────────────────────────

@dataclass
class SetBonusEffect:
    pieces: int
    stat: str       # 'mechanic' for display-only effects with no numeric stat
    value: float    # 0 for mechanic-only effects
    is_flat: bool
    raw_text: str   # original description text — always present for UI display


@dataclass
class SetBonusEntry:
    unique_name: str
    num_pieces_in_set: int
    bonus_by_piece_count: list[SetBonusEffect]


def load_mod_sets() -> list[SetBonusEntry]:
    return [
        SetBonusEntry(
            unique_name=s["uniqueName"],
            num_pieces_in_set=s["numPiecesInSet"],
            bonus_by_piece_count=[
                SetBonusEffect(
                    pieces=b["pieces"], stat=b["stat"],
                    value=b["value"], is_flat=b["isFlat"],
                    raw_text=b.get("rawText", ""),
                )
                for b in s["bonusByPieceCount"]
            ],
        )
        for s in _load_json("mod-sets.json")
    ]


# ── Ability Stats ─────────────────────────────────────────────────────────────

@dataclass
class AbilityStatBlock:
    label: str
    modifier: str
    base_value: float
    is_percent: bool


@dataclass
class AbilityStatsEntry:
    unique_name: str
    stats: list[AbilityStatBlock]


def load_ability_stats() -> list[AbilityStatsEntry]:
    return [
        AbilityStatsEntry(
            unique_name=e["uniqueName"],
            stats=[
                AbilityStatBlock(
                    label=b["label"], modifier=b["modifier"],
                    base_value=b["baseValue"], is_percent=b["isPercent"],
                )
                for b in e["stats"]
            ],
        )
        for e in _load_json("ability-stats.json")
    ]


# ── Abilities Data ────────────────────────────────────────────────────────────

@dataclass
class AbilitiesData:
    subsumable: list[str]
    augment_to_ability: dict[str, str]


def load_abilities_data() -> AbilitiesData:
    d = _load_json("abilities.json")
    return AbilitiesData(
        subsumable=d["subsumable"],
        augment_to_ability=d["augmentToAbility"],
    )


# ── Shard Bonuses ─────────────────────────────────────────────────────────────

@dataclass
class ShardBonus:
    stat: str
    value: float
    is_flat: bool
    conditional: bool


def load_shard_bonuses() -> dict[str, list[ShardBonus]]:
    raw = _load_json("shard-bonuses.json")
    result: dict[str, list[ShardBonus]] = {}
    if isinstance(raw, dict):
        for color, bonuses in raw.items():
            if isinstance(bonuses, list):
                result[color] = [
                    ShardBonus(
                        stat=b["stat"], value=b["value"],
                        is_flat=b["isFlat"], conditional=b["conditional"],
                    )
                    for b in bonuses
                ]
    return result
