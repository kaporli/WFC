"""
notables.py — surface all notable passive effects from an equipped loadout,
attributed to their source mod/set/weapon.

Notables are anything the UI should communicate to the player:
  - cross_equip_stat  : a mod on one slot changes a stat in a different slot
  - passive           : a descriptive mechanic from a mod (no numeric stat)
  - set_passive       : a mechanic-only set bonus (stat='mechanic')
  - set_stat          : a numeric set bonus that affects a slot
  - signature_weapon  : a weapon+warframe synergy bonus (e.g. Epitaph + Sevagoth)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.build import EquippedMod
from warframe_engine.calculator import DataCache


_SLOT_LABELS: dict[str, str] = {
    'warframe_mod': 'Warframe',
    'primary': 'Primary',
    'secondary': 'Secondary',
    'melee': 'Melee',
    'archgun': 'Archgun',
    'companion': 'Companion',
    'warframe_aura': 'Aura',
    'warframe_exilus': 'Exilus',
    'set': 'Set Bonus',
}


@dataclass
class Notable:
    source: str             # mod / set name
    source_slot: str        # where it's equipped: 'warframe_mod', 'melee', 'primary', etc.
    kind: str               # 'cross_equip_stat' | 'passive' | 'set_passive' | 'set_stat'
    stat: str | None        # normalised stat name (None for passive/set_passive)
    target: str | None      # slot the effect applies to (None for passives)
    value: float | None     # numeric value (None for passives)
    description: str        # always-present human-readable text


def _describe_stat(stat: str, value: float, target: str) -> str:
    pct = f"{value:+.0%}" if abs(value) < 10 else f"{value:+.0f}"
    target_label = _SLOT_LABELS.get(target, target.capitalize())
    return f"{pct} {stat} (affects {target_label})"


def _iter_slot_mods(slot: WeaponSlot | None) -> list[EquippedMod]:
    if slot is None:
        return []
    return [*slot.mods, slot.exilus, slot.riven]  # type: ignore[list-item]


def get_notables(loadout: Loadout, cache: DataCache) -> list[Notable]:
    notables: list[Notable] = []
    wf = loadout.warframe

    # ── Warframe mods ──────────────────────────────────────────────────────────
    wf_mods = [*wf.mods, wf.exilus, *wf.auras]
    for em in filter(None, wf_mods):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if not mod:
            continue
        rank = min(em.rank, mod.max_rank)
        slot_label = 'warframe_aura' if em in wf.auras else (
            'warframe_exilus' if em == wf.exilus else 'warframe_mod'
        )

        # Cross-equip stat effects (target != 'self' and target != 'warframe')
        for eff in mod.effects:
            if eff.target in ('self', 'warframe'):
                continue
            if rank < len(eff.level_values):
                val = eff.level_values[rank]
                if val == 0:
                    continue
                notables.append(Notable(
                    source=mod.name,
                    source_slot=slot_label,
                    kind='cross_equip_stat',
                    stat=eff.stat,
                    target=eff.target,
                    value=val,
                    description=_describe_stat(eff.stat, val, eff.target),
                ))

        # Passives (descriptive text from levelStats)
        for passive in mod.passives:
            notables.append(Notable(
                source=mod.name,
                source_slot=slot_label,
                kind='passive',
                stat=None,
                target=None,
                value=None,
                description=passive,
            ))

    # ── Weapon slots ───────────────────────────────────────────────────────────
    weapon_slots: list[tuple[str, WeaponSlot | None]] = [
        ('primary', loadout.primary),
        ('secondary', loadout.secondary),
        ('melee', loadout.melee),
        ('archgun', loadout.archgun if loadout.archgun_gravimag else None),
        ('companion', loadout.companion_weapon),
    ]

    for slot_name, slot in weapon_slots:
        if slot is None:
            continue
        for em in filter(None, _iter_slot_mods(slot)):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if not mod:
                continue
            rank = min(em.rank, mod.max_rank)

            # Cross-equip stat effects from weapon mods
            for eff in mod.effects:
                if eff.target == 'self':
                    continue
                if rank < len(eff.level_values):
                    val = eff.level_values[rank]
                    if val == 0:
                        continue
                    notables.append(Notable(
                        source=mod.name,
                        source_slot=slot_name,
                        kind='cross_equip_stat',
                        stat=eff.stat,
                        target=eff.target,
                        value=val,
                        description=_describe_stat(eff.stat, val, eff.target),
                    ))

            # Passives from weapon mods
            for passive in mod.passives:
                notables.append(Notable(
                    source=mod.name,
                    source_slot=slot_name,
                    kind='passive',
                    stat=None,
                    target=None,
                    value=None,
                    description=passive,
                ))

    # ── Set bonuses ────────────────────────────────────────────────────────────
    # Count set pieces across entire loadout
    from collections import defaultdict
    piece_counts: dict[str, int] = defaultdict(int)
    all_equipped: list[EquippedMod] = [
        *filter(None, wf_mods),
    ]
    for _, slot in weapon_slots:
        if slot:
            all_equipped.extend(filter(None, _iter_slot_mods(slot)))

    for em in all_equipped:
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if mod and mod.mod_set:
            piece_counts[mod.mod_set] += 1

    # Map set uniqueNames back to the mod that "owns" the set for display
    set_source_names: dict[str, str] = {}
    for em in all_equipped:
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if mod and mod.mod_set and mod.mod_set not in set_source_names:
            # Use the mod set uniqueName's last path component, cleaned up
            set_source_names[mod.mod_set] = mod.mod_set.split('/')[-1].replace('SetMod', ' Set')

    for set_uid, pieces in piece_counts.items():
        entry = cache.mod_set_by_unique_name.get(set_uid)
        if not entry:
            continue
        set_name = set_source_names.get(set_uid, set_uid.split('/')[-1])
        bonus = next((b for b in entry.bonus_by_piece_count if b.pieces == pieces), None)
        if not bonus:
            continue

        if bonus.stat == 'mechanic' or bonus.value == 0:
            notables.append(Notable(
                source=f"{set_name} ({pieces}/{entry.num_pieces_in_set})",
                source_slot='set',
                kind='set_passive',
                stat=None,
                target=None,
                value=None,
                description=bonus.raw_text,
            ))
        else:
            notables.append(Notable(
                source=f"{set_name} ({pieces}/{entry.num_pieces_in_set})",
                source_slot='set',
                kind='set_stat',
                stat=bonus.stat,
                target='warframe',
                value=bonus.value,
                description=bonus.raw_text,
            ))

    # ── Signature weapon interactions ──────────────────────────────────────────
    wf_name_lower = wf.warframe_name.lower()

    for slot_name, slot in weapon_slots:
        if slot is None:
            continue
        weapon = cache.weapon_by_unique_name.get(slot.weapon_unique_name)
        if not weapon:
            continue
        weapon_name_lower = weapon.name.lower()
        bonus = cache.signature_weapon_bonuses.get((wf_name_lower, weapon_name_lower))
        if bonus:
            notables.append(Notable(
                source=weapon.name,
                source_slot=slot_name,
                kind='signature_weapon',
                stat=None,
                target=None,
                value=None,
                description=bonus,
            ))

    return notables
