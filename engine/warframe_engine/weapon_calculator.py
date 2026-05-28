from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from warframe_engine.loadout import WeaponSlot
from warframe_engine.calculator import DataCache


@dataclass
class WeaponStatSheet:
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


def compute_weapon_stats(
    slot: WeaponSlot,
    cache: DataCache,
) -> tuple[WeaponStatSheet, dict[str, dict[str, float]]]:
    """
    Returns (WeaponStatSheet, cross_equip).
    cross_equip is keyed by target slot ('warframe', 'secondary', etc.)
    and maps stat -> additive bonus value.
    """
    weapon = cache.weapon_by_unique_name.get(slot.weapon_unique_name)
    if weapon is None:
        raise ValueError(f"Unknown weapon: {slot.weapon_unique_name}")

    additive: dict[str, float] = defaultdict(float)
    flat_combo: float = 0.0
    cross_equip: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    all_mods = [*slot.mods, slot.exilus, slot.riven]
    for em in filter(None, all_mods):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if not mod:
            continue
        for eff in mod.effects:
            if em.rank >= len(eff.level_values):
                continue
            val = eff.level_values[em.rank]
            if eff.target == 'self':
                if eff.stat == 'comboDuration':
                    flat_combo += val
                else:
                    additive[eff.stat] += val
            else:
                cross_equip[eff.target][eff.stat] += val

    b = weapon.base_stats

    # Scale damage types proportionally
    scaled_types: dict[str, float] = {}
    if b.damage_types:
        dmg_mult = 1 + additive['damage']
        scaled_types = {k: v * dmg_mult for k, v in b.damage_types.items()}
    total = b.total_damage * (1 + additive['damage'])

    sheet = WeaponStatSheet(
        total_damage=total,
        damage_types=scaled_types,
        crit_chance=b.crit_chance + additive['critChance'],
        crit_multiplier=b.crit_multiplier * (1 + additive['critMult']),
        status_chance=b.status_chance + additive['statusChance'],
        fire_rate=b.fire_rate * (1 + additive['fireRate']),
        magazine_size=round(b.magazine_size * (1 + additive['magazineSize'])),
        reload_time=b.reload_time * max(0.01, 1 - additive['reloadSpeed']),
        multishot=b.multishot * (1 + additive['multishot']),
        range=b.range,
        attack_speed=(
            (b.attack_speed or 1.0) * (1 + additive['attackSpeed'])
            if b.attack_speed else None
        ),
        combo_duration=(
            (b.combo_duration or 0) + flat_combo if b.combo_duration else None
        ),
        heavy_attack_damage=b.heavy_attack_damage,
    )

    return sheet, dict(cross_equip)
