from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from warframe_engine.loader import (
    load_warframes, load_mods, load_arcanes, load_weapons,
    load_helmets, load_mod_sets, load_ability_stats, load_abilities_data, load_shard_bonuses,
    WarframeEntry, ModEntry, ArcaneEntry, WeaponEntry,
    ArcaneHelmetEntry, SetBonusEntry, AbilityStatsEntry, AbilitiesData, ShardBonus,
)
from warframe_engine.build import Build, EquippedMod


@dataclass
class StatSheet:
    ability_strength: float
    ability_duration: float
    ability_range: float
    ability_efficiency: float   # hard cap 1.75

    health: float
    shield: float
    armor: float
    energy: float
    sprint: float

    armor_dr: float   # armor / (armor + 300)
    ehp: float        # health / (1 - armor_dr) + shield

    can_shieldgate: bool
    gate_full_s: float    # 1.3
    gate_short_s: float   # 0.13


class DataCache:
    def __init__(self) -> None:
        warframes = load_warframes()
        mods = load_mods()
        arcanes = load_arcanes()
        weapons = load_weapons()
        helmets = load_helmets()
        mod_sets = load_mod_sets()
        ability_stats_list = load_ability_stats()
        abilities_data = load_abilities_data()
        shard_bonuses = load_shard_bonuses()

        self.warframe_by_name: dict[str, WarframeEntry] = {w.name: w for w in warframes}
        self.mod_by_unique_name: dict[str, ModEntry] = {m.unique_name: m for m in mods}
        self.arcane_by_unique_name: dict[str, ArcaneEntry] = {a.unique_name: a for a in arcanes}
        self.weapon_by_unique_name: dict[str, WeaponEntry] = {w.unique_name: w for w in weapons}
        self.helmet_by_unique_name: dict[str, ArcaneHelmetEntry] = {h.unique_name: h for h in helmets}
        self.arcane_helmet_unique_names: set[str] = {h.unique_name for h in helmets}
        self.mod_set_by_unique_name: dict[str, SetBonusEntry] = {s.unique_name: s for s in mod_sets}
        self.ability_stats_by_unique_name: dict[str, AbilityStatsEntry] = {
            e.unique_name: e for e in ability_stats_list
        }
        self.abilities_data: AbilitiesData = abilities_data
        self.shard_bonuses: dict[str, list[ShardBonus]] = shard_bonuses

        # Convenience refs for tests
        self.mods = mods
        self.arcanes = arcanes
        self.helmets = helmets


def compute_warframe_stats(
    build: Build,
    cache: DataCache,
    cross_equip_additive: dict[str, float] | None = None,
) -> StatSheet:
    warframe = cache.warframe_by_name[build.warframe_name]
    additive: dict[str, float] = defaultdict(float)
    flat: dict[str, float] = defaultdict(float)

    # ── Mods (regular + exilus + all auras) ───────────────────────────────────
    all_mods: list[EquippedMod | None] = [*build.mods, build.exilus, *build.auras]

    # Count set pieces per mod_set so we can apply per-mod set multipliers (e.g. Umbra)
    set_piece_counts: dict[str, int] = defaultdict(int)
    for em in filter(None, all_mods):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if mod and mod.mod_set:
            set_piece_counts[mod.mod_set] += 1

    for em in filter(None, all_mods):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if not mod:
            continue

        # Per-mod set multiplier: index 0 = bonus at 2 pieces, 1 = bonus at 3 pieces, etc.
        # Only applies to mods that carry their own modSetValues (e.g. Umbra mods)
        set_mult = 1.0
        if mod.set_multipliers and mod.mod_set:
            pieces = set_piece_counts.get(mod.mod_set, 0)
            tier_idx = pieces - 2  # 0 for 2 pieces, 1 for 3 pieces, ...
            if 0 <= tier_idx < len(mod.set_multipliers):
                set_mult = 1.0 + mod.set_multipliers[tier_idx]

        for eff in mod.effects:
            # Only apply effects targeting warframe or self (weapon effects handled by weapon_calculator)
            if eff.target not in ('self', 'warframe'):
                continue
            if em.rank < len(eff.level_values):
                additive[eff.stat] += eff.level_values[em.rank] * set_mult

    # ── Arcanes ────────────────────────────────────────────────────────────────
    for ea in build.arcanes:
        arcane = cache.arcane_by_unique_name.get(ea.unique_name)
        if not arcane:
            continue
        for eff in arcane.effects:
            if ea.rank < len(eff.level_values):
                additive[eff.stat] += eff.level_values[ea.rank]

    # ── Arcane helmet ──────────────────────────────────────────────────────────
    if build.helmet and build.helmet in cache.arcane_helmet_unique_names:
        helmet = cache.helmet_by_unique_name.get(build.helmet)
        if helmet:
            for eff in helmet.effects:
                if eff.is_flat:
                    flat[eff.stat] += eff.value
                else:
                    additive[eff.stat] += eff.value

    # ── Archon shards ──────────────────────────────────────────────────────────
    for shard in build.shards:
        color_bonuses = cache.shard_bonuses.get(shard.color, [])
        for bonus in color_bonuses:
            if bonus.stat != shard.stat or bonus.conditional:
                continue
            value = bonus.value * (1.5 if shard.tauforged else 1.0)
            if bonus.is_flat:
                flat[bonus.stat] += value
            else:
                additive[bonus.stat] += value

    # ── Cross-equipment contributions (from weapon mods) ──────────────────────
    if cross_equip_additive:
        for stat, val in cross_equip_additive.items():
            additive[stat] += val

    # ── Final stats ───────────────────────────────────────────────────────────
    b = warframe.base_stats
    health = (b.health + flat['health']) * (1 + additive['health'])
    shield = (b.shield + flat['shield']) * (1 + additive['shield'])
    armor  = (b.armor  + flat['armor'])  * (1 + additive['armor'])
    energy = (b.energy + flat['energy']) * (1 + additive['energy'])
    sprint = b.sprint * (1 + additive['sprint'])

    ability_strength   = 1.0 + additive['abilityStrength']
    ability_duration   = 1.0 + additive['abilityDuration']
    ability_range      = 1.0 + additive['abilityRange']
    ability_efficiency = min(1.75, 1.0 + additive['abilityEfficiency'])

    armor_dr = armor / (armor + 300) if armor > 0 else 0.0
    ehp = (health / (1 - armor_dr)) + shield if armor_dr < 1 else float('inf')

    return StatSheet(
        ability_strength=ability_strength,
        ability_duration=ability_duration,
        ability_range=ability_range,
        ability_efficiency=ability_efficiency,
        health=health,
        shield=shield,
        armor=armor,
        energy=energy,
        sprint=sprint,
        armor_dr=armor_dr,
        ehp=ehp,
        can_shieldgate=shield > 0,
        gate_full_s=1.3,
        gate_short_s=0.13,
    )
