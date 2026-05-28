from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from warframe_engine.loadout import Loadout
from warframe_engine.loadout_calculator import LoadoutStats
from warframe_engine.calculator import DataCache
from warframe_engine.build import EquippedMod


@dataclass
class MechanicCheck:
    id: str
    name: str
    category: str   # 'armor_strip' | 'shieldgate' | 'ability_threshold'
    value: float
    threshold: float
    passes: bool
    details: dict = field(default_factory=dict)


def _get_augur_pct(loadout: Loadout, cache: DataCache) -> float:
    """Return total Augur set energy→shield % from piece count across entire loadout."""
    piece_counts: dict[str, int] = defaultdict(int)

    def count(mods: list[EquippedMod], exilus: EquippedMod | None = None, riven: EquippedMod | None = None) -> None:
        for em in filter(None, [*mods, exilus, riven]):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if mod and mod.mod_set:
                piece_counts[mod.mod_set] += 1

    wf = loadout.warframe
    count(wf.mods, wf.exilus)
    for aura in wf.auras:
        mod = cache.mod_by_unique_name.get(aura.unique_name)
        if mod and mod.mod_set:
            piece_counts[mod.mod_set] += 1

    for slot_attr in ('primary', 'secondary', 'melee', 'archgun', 'companion_weapon'):
        slot = getattr(loadout, slot_attr, None)
        if slot:
            count(slot.mods, slot.exilus, slot.riven)

    for set_uid, pieces in piece_counts.items():
        if 'Augur' not in set_uid:
            continue
        set_entry = cache.mod_set_by_unique_name.get(set_uid)
        if not set_entry:
            continue
        for bonus in set_entry.bonus_by_piece_count:
            if bonus.pieces == pieces and bonus.stat == 'energyToShieldOnCast':
                return bonus.value
    return 0.0


def _get_brief_respite_pct(loadout: Loadout, cache: DataCache) -> float:
    """Return Brief Respite energy→shield % if equipped as aura or mod."""
    wf = loadout.warframe
    all_mods = [*wf.mods, wf.exilus, *wf.auras]
    for em in filter(None, all_mods):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if mod and 'Brief Respite' in mod.name and mod.effects:
            eff = mod.effects[0]
            rank = min(em.rank, len(eff.level_values) - 1)
            return eff.level_values[rank]
    return 0.0


def _shieldgate_checks(
    loadout: Loadout,
    stats: LoadoutStats,
    cache: DataCache,
) -> list[MechanicCheck]:
    augur_pct = _get_augur_pct(loadout, cache)
    respite_pct = _get_brief_respite_pct(loadout, cache)
    total_pct = augur_pct + respite_pct

    if total_pct <= 0:
        return []

    checks: list[MechanicCheck] = []
    efficiency = stats.warframe.ability_efficiency
    current_shield = stats.warframe.shield

    warframe = cache.warframe_by_name.get(loadout.warframe.warframe_name)
    if not warframe:
        return []

    for ability in warframe.abilities:
        # Find the ability stats entry by matching the ability name into the uniqueName path
        ability_stats = None
        normalized_name = ability.name.replace(' ', '').lower()
        for key, entry in cache.ability_stats_by_unique_name.items():
            if normalized_name in key.lower():
                ability_stats = entry
                break

        if not ability_stats:
            continue

        energy_block = next(
            (b for b in ability_stats.stats if b.modifier == 'AVATAR_ABILITY_EFFICIENCY'),
            None,
        )
        if not energy_block:
            continue

        base_cost = energy_block.base_value
        actual_cost = base_cost * (2 - efficiency)
        shields_restored = actual_cost * total_pct

        check_id = f"shieldgate_{ability.name.lower().replace(' ', '_')}"
        checks.append(MechanicCheck(
            id=check_id,
            name=f"Shieldgate via {ability.name}",
            category='shieldgate',
            value=round(shields_restored, 2),
            threshold=current_shield,
            passes=shields_restored >= current_shield,
            details={
                'ability_name': ability.name,
                'base_energy_cost': base_cost,
                'actual_energy_cost': round(actual_cost, 2),
                'shields_restored': round(shields_restored, 2),
                'conversion_pct': total_pct,
                'current_shield': current_shield,
            },
        ))

    return checks


def _armor_strip_checks(
    loadout: Loadout,
    stats: LoadoutStats,
    cache: DataCache,
) -> list[MechanicCheck]:
    checks: list[MechanicCheck] = []
    warframe = cache.warframe_by_name.get(loadout.warframe.warframe_name)
    if not warframe:
        return []

    ability_strength = stats.warframe.ability_strength

    for ability in warframe.abilities:
        # Match ability stats entry by normalized name in uniqueName path
        ability_stats = None
        normalized_name = ability.name.replace(' ', '').lower()
        for key, entry in cache.ability_stats_by_unique_name.items():
            if normalized_name in key.lower():
                ability_stats = entry
                break

        if not ability_stats:
            continue

        armor_block = next(
            (b for b in ability_stats.stats
             if 'armor' in b.label.lower() and 'reduction' in b.label.lower()),
            None,
        )
        if not armor_block:
            continue

        base_strip = armor_block.base_value
        final_strip = base_strip * ability_strength
        required_strength = (1.0 / base_strip) if base_strip > 0 else float('inf')

        check_id = f"armor_strip_{ability.name.lower().replace(' ', '_')}"
        checks.append(MechanicCheck(
            id=check_id,
            name=f"{ability.name} Full Armor Strip",
            category='armor_strip',
            value=round(final_strip, 4),
            threshold=1.0,
            passes=final_strip >= 1.0,
            details={
                'ability_name': ability.name,
                'base_armor_reduction': base_strip,
                'current_strength': ability_strength,
                'required_strength': round(required_strength, 2),
            },
        ))

    return checks


def run_checks(
    loadout: Loadout,
    stats: LoadoutStats,
    cache: DataCache,
) -> list[MechanicCheck]:
    checks: list[MechanicCheck] = []
    checks.extend(_shieldgate_checks(loadout, stats, cache))
    checks.extend(_armor_strip_checks(loadout, stats, cache))
    return checks
