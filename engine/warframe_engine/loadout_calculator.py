from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.calculator import DataCache, StatSheet, compute_warframe_stats
from warframe_engine.weapon_calculator import WeaponStatSheet, compute_weapon_stats
from warframe_engine.build import EquippedMod


@dataclass
class LoadoutStats:
    warframe: StatSheet
    primary: WeaponStatSheet | None
    secondary: WeaponStatSheet | None
    melee: WeaponStatSheet | None
    archgun: WeaponStatSheet | None
    companion_weapon: WeaponStatSheet | None


def _compute_slot(
    slot: WeaponSlot | None,
    cache: DataCache,
) -> tuple[WeaponStatSheet | None, dict[str, dict[str, float]]]:
    if slot is None:
        return None, {}
    sheet, cross_equip = compute_weapon_stats(slot, cache)
    return sheet, cross_equip


def _count_set_pieces(loadout: Loadout, cache: DataCache) -> dict[str, int]:
    """Count equipped pieces per mod-set uniqueName across entire loadout."""
    counts: dict[str, int] = defaultdict(int)

    def count_mods(mods: list[EquippedMod], exilus: EquippedMod | None = None, riven: EquippedMod | None = None) -> None:
        for em in filter(None, [*mods, exilus, riven]):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if mod and mod.mod_set:
                counts[mod.mod_set] += 1

    wf = loadout.warframe
    count_mods(wf.mods, wf.exilus)
    for aura in wf.auras:
        mod = cache.mod_by_unique_name.get(aura.unique_name)
        if mod and mod.mod_set:
            counts[mod.mod_set] += 1

    for slot_attr in ('primary', 'secondary', 'melee', 'archgun', 'companion_weapon'):
        slot: WeaponSlot | None = getattr(loadout, slot_attr, None)
        if slot:
            count_mods(slot.mods, slot.exilus, slot.riven)

    return dict(counts)


def _resolve_set_bonuses(loadout: Loadout, cache: DataCache) -> dict[str, float]:
    """Return additive bonuses for warframe from mod set bonuses."""
    piece_counts = _count_set_pieces(loadout, cache)
    warframe_bonus: dict[str, float] = defaultdict(float)

    for set_uid, pieces in piece_counts.items():
        set_entry = cache.mod_set_by_unique_name.get(set_uid)
        if not set_entry:
            continue
        for bonus in set_entry.bonus_by_piece_count:
            if bonus.pieces == pieces and not bonus.is_flat and bonus.stat != 'mechanic':
                warframe_bonus[bonus.stat] += bonus.value

    return dict(warframe_bonus)


def compute_loadout(loadout: Loadout, cache: DataCache) -> LoadoutStats:
    """
    Compute stat sheets for all slots.
    Cross-equipment mod effects route to appropriate slots.
    Set bonuses counted across all slots, applied to warframe.
    """
    # 1. Compute weapon slots, collect cross-equip contributions
    primary, ce_primary     = _compute_slot(loadout.primary, cache)
    secondary, ce_secondary = _compute_slot(loadout.secondary, cache)
    melee, ce_melee         = _compute_slot(loadout.melee, cache)

    # Archgun only contributes if Gravimag is installed
    archgun_slot = loadout.archgun if loadout.archgun_gravimag else None
    archgun, ce_archgun     = _compute_slot(archgun_slot, cache)
    companion_weapon, _     = _compute_slot(loadout.companion_weapon, cache)

    # 2. Merge all cross-equip -> warframe contributions
    warframe_cross: dict[str, float] = defaultdict(float)
    for ce in (ce_primary, ce_secondary, ce_melee, ce_archgun):
        for stat, val in ce.get('warframe', {}).items():
            warframe_cross[stat] += val

    # 3. Resolve set bonuses (additive to warframe pool)
    set_bonuses = _resolve_set_bonuses(loadout, cache)
    for stat, val in set_bonuses.items():
        warframe_cross[stat] += val

    # 4. Compute warframe stats with all contributions applied
    warframe_stats = compute_warframe_stats(
        loadout.warframe,
        cache,
        cross_equip_additive=dict(warframe_cross) if warframe_cross else None,
    )

    return LoadoutStats(
        warframe=warframe_stats,
        primary=primary,
        secondary=secondary,
        melee=melee,
        archgun=archgun,
        companion_weapon=companion_weapon,
    )
