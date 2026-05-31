from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.loadout_calculator import LoadoutStats
from warframe_engine.calculator import DataCache
from warframe_engine.build import EquippedMod
from warframe_engine.loader import SetBonusEntry


@dataclass
class MechanicCheck:
    id: str
    name: str
    category: str   # 'armor_strip' | 'shieldgate' | 'set_bonus'
    value: float
    threshold: float
    passes: bool
    details: dict = field(default_factory=dict)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _count_all_set_pieces(loadout: Loadout, cache: DataCache) -> dict[str, int]:
    """Count equipped pieces per mod-set uniqueName across the full loadout."""
    counts: dict[str, int] = defaultdict(int)

    def _tally(mods: list[EquippedMod], exilus: EquippedMod | None = None, riven: EquippedMod | None = None) -> None:
        for em in filter(None, [*mods, exilus, riven]):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if mod and mod.mod_set:
                counts[mod.mod_set] += 1

    wf = loadout.warframe
    _tally(wf.mods, wf.exilus)
    for aura in wf.auras:
        mod = cache.mod_by_unique_name.get(aura.unique_name)
        if mod and mod.mod_set:
            counts[mod.mod_set] += 1

    for slot_attr in ('primary', 'secondary', 'melee', 'archgun', 'companion_weapon'):
        slot: WeaponSlot | None = getattr(loadout, slot_attr, None)
        if slot:
            _tally(slot.mods, slot.exilus, slot.riven)

    return dict(counts)


def _get_set_bonus(
    piece_counts: dict[str, int],
    cache: DataCache,
    uid_fragment: str,
    stat_name: str,
) -> tuple[int, float]:
    """Return (pieces_equipped, bonus_value) for a named set. (0, 0.0) if not equipped."""
    for set_uid, pieces in piece_counts.items():
        if uid_fragment.lower() not in set_uid.lower():
            continue
        entry = cache.mod_set_by_unique_name.get(set_uid)
        if not entry:
            continue
        bonus = next(
            (b for b in entry.bonus_by_piece_count if b.pieces == pieces and b.stat == stat_name),
            None,
        )
        if bonus:
            return pieces, bonus.value
    return 0, 0.0


def _get_brief_respite_pct(loadout: Loadout, cache: DataCache) -> float:
    """Return Brief Respite energy→shield % if equipped."""
    wf = loadout.warframe
    for em in filter(None, [*wf.mods, wf.exilus, *wf.auras]):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if mod and 'Brief Respite' in mod.name and mod.effects:
            eff = mod.effects[0]
            rank = min(em.rank, len(eff.level_values) - 1)
            return eff.level_values[rank]
    return 0.0


# ── Shieldgate ─────────────────────────────────────────────────────────────────

def _shieldgate_checks(
    loadout: Loadout,
    stats: LoadoutStats,
    cache: DataCache,
    piece_counts: dict[str, int],
) -> list[MechanicCheck]:
    _, augur_pct = _get_set_bonus(piece_counts, cache, 'Augur', 'energyToShieldOnCast')
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
        normalized_name = ability.name.replace(' ', '').lower()
        ability_stats = next(
            (e for k, e in cache.ability_stats_by_unique_name.items() if normalized_name in k.lower()),
            None,
        )
        if not ability_stats:
            continue
        energy_block = next(
            (b for b in ability_stats.stats if b.modifier == 'AVATAR_ABILITY_EFFICIENCY'), None
        )
        if not energy_block:
            continue

        base_cost = energy_block.base_value
        actual_cost = base_cost * (2 - efficiency)
        shields_restored = actual_cost * total_pct

        checks.append(MechanicCheck(
            id=f"shieldgate_{ability.name.lower().replace(' ', '_')}",
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
                'conversion_pct': round(total_pct, 4),
                'augur_pct': round(augur_pct, 4),
                'brief_respite_pct': round(respite_pct, 4),
                'current_shield': current_shield,
            },
        ))
    return checks


# ── Armor strip ────────────────────────────────────────────────────────────────

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
        normalized_name = ability.name.replace(' ', '').lower()
        ability_stats = next(
            (e for k, e in cache.ability_stats_by_unique_name.items() if normalized_name in k.lower()),
            None,
        )
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

        checks.append(MechanicCheck(
            id=f"armor_strip_{ability.name.lower().replace(' ', '_')}",
            name=f"{ability.name} Full Armor Strip",
            category='armor_strip',
            value=round(final_strip, 4),
            threshold=1.0,
            passes=final_strip >= 1.0,
            details={
                'ability_name': ability.name,
                'base_armor_reduction': base_strip,
                'current_strength': round(ability_strength, 4),
                'required_strength': round(required_strength, 2),
            },
        ))
    return checks


# ── Gladiator ─────────────────────────────────────────────────────────────────

def _gladiator_checks(
    stats: LoadoutStats,
    cache: DataCache,
    piece_counts: dict[str, int],
) -> list[MechanicCheck]:
    pieces, bonus_per_mult = _get_set_bonus(piece_counts, cache, 'Gladiator', 'meleeCritPerComboMult')
    if pieces == 0:
        return []

    base_crit = stats.melee.crit_chance if stats.melee else 0.0
    COMBO_LEVELS = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0]

    return [MechanicCheck(
        id='gladiator_melee_crit',
        name='Gladiator Set — Melee Critical Chance',
        category='set_bonus',
        value=bonus_per_mult,
        threshold=0.0,
        passes=True,
        details={
            'pieces': pieces,
            'bonus_per_combo_mult': round(bonus_per_mult, 4),
            'base_melee_crit': round(base_crit, 4),
            'effective_crit_by_combo': {
                f'x{c}': round(base_crit + bonus_per_mult * c, 4)
                for c in COMBO_LEVELS
            },
        },
    )]


# ── Vigilante ─────────────────────────────────────────────────────────────────

def _vigilante_checks(
    stats: LoadoutStats,
    cache: DataCache,
    piece_counts: dict[str, int],
) -> list[MechanicCheck]:
    pieces, enhance_chance = _get_set_bonus(piece_counts, cache, 'Vigilante', 'primaryCritEnhanceChance')
    if pieces == 0:
        return []

    base_crit = stats.primary.crit_chance if stats.primary else 0.0
    base_mult = stats.primary.crit_multiplier if stats.primary else 1.0

    # Each critical hit has `enhance_chance` to jump up one tier (yellow→orange, orange→red)
    # Effective crit multiplier increase from enhancements (approximate):
    # orange crits deal 2× the yellow crit bonus; red crits deal 3×
    # At base crit_mult C, enhanced crits deal C + (C-1) extra (one more step)
    enhanced_portion = base_crit * enhance_chance  # portion of hits that get enhanced
    effective_avg_mult = base_mult + (base_mult - 1) * enhanced_portion

    return [MechanicCheck(
        id='vigilante_crit_enhancement',
        name='Vigilante Set — Primary Crit Enhancement',
        category='set_bonus',
        value=round(enhance_chance, 4),
        threshold=0.0,
        passes=True,
        details={
            'pieces': pieces,
            'enhancement_chance': round(enhance_chance, 4),
            'base_primary_crit': round(base_crit, 4),
            'base_primary_mult': round(base_mult, 4),
            'pct_of_hits_enhanced': round(base_crit * enhance_chance, 4),
            'effective_avg_crit_mult': round(effective_avg_mult, 4),
        },
    )]


# ── Hunter ────────────────────────────────────────────────────────────────────

def _hunter_checks(
    cache: DataCache,
    piece_counts: dict[str, int],
) -> list[MechanicCheck]:
    pieces, damage_bonus = _get_set_bonus(piece_counts, cache, 'Hunter', 'companionSlashDamage')
    if pieces == 0:
        return []

    return [MechanicCheck(
        id='hunter_companion_slash',
        name='Hunter Set — Companion Damage vs Slash-Affected Enemies',
        category='set_bonus',
        value=round(damage_bonus, 4),
        threshold=0.0,
        passes=True,
        details={
            'pieces': pieces,
            'companion_damage_bonus': round(damage_bonus, 4),
            'companion_damage_multiplier': round(1.0 + damage_bonus, 4),
            'note': 'Applies when enemy has active Slash status',
        },
    )]


# ── Synth ─────────────────────────────────────────────────────────────────────

def _synth_checks(
    cache: DataCache,
    piece_counts: dict[str, int],
) -> list[MechanicCheck]:
    pieces, reload_rate = _get_set_bonus(piece_counts, cache, 'Synth', 'holsterReloadRate')
    if pieces == 0:
        return []

    return [MechanicCheck(
        id='synth_holster_reload',
        name='Synth Set — Holster Reload Rate',
        category='set_bonus',
        value=round(reload_rate, 4),
        threshold=0.0,
        passes=True,
        details={
            'pieces': pieces,
            'reload_rate_per_second': round(reload_rate, 4),
            'note': 'Holstered Primary and Secondary weapons reload at this rate per second',
        },
    )]


# ── Boreal ────────────────────────────────────────────────────────────────────

def _boreal_checks(
    cache: DataCache,
    piece_counts: dict[str, int],
) -> list[MechanicCheck]:
    pieces, dr = _get_set_bonus(piece_counts, cache, 'Boreal', 'airborneReducedDamageTaken')
    if pieces == 0:
        return []

    return [MechanicCheck(
        id='boreal_airborne_dr',
        name='Boreal Set — Airborne Damage Reduction',
        category='set_bonus',
        value=round(dr, 4),
        threshold=0.0,
        passes=True,
        details={
            'pieces': pieces,
            'damage_reduction_airborne': round(dr, 4),
            'note': 'Damage reduction applies only while airborne',
        },
    )]


# ── Raptor ────────────────────────────────────────────────────────────────────

def _raptor_checks(
    cache: DataCache,
    piece_counts: dict[str, int],
) -> list[MechanicCheck]:
    pieces, immunity_chance = _get_set_bonus(piece_counts, cache, 'Raptor', 'airborneKnockdownImmunity')
    if pieces == 0:
        return []

    return [MechanicCheck(
        id='raptor_knockdown_immunity',
        name='Raptor Set — Airborne Knockdown Immunity',
        category='set_bonus',
        value=round(immunity_chance, 4),
        threshold=1.0,
        passes=immunity_chance >= 1.0,
        details={
            'pieces': pieces,
            'knockdown_immunity_chance': round(immunity_chance, 4),
            'note': 'Applies only while airborne',
        },
    )]


# ── Entry point ────────────────────────────────────────────────────────────────

def run_checks(
    loadout: Loadout,
    stats: LoadoutStats,
    cache: DataCache,
) -> list[MechanicCheck]:
    checks: list[MechanicCheck] = []

    # Count set pieces once; all check functions share the result
    piece_counts = _count_all_set_pieces(loadout, cache)

    checks.extend(_shieldgate_checks(loadout, stats, cache, piece_counts))
    checks.extend(_armor_strip_checks(loadout, stats, cache))
    checks.extend(_gladiator_checks(stats, cache, piece_counts))
    checks.extend(_vigilante_checks(stats, cache, piece_counts))
    checks.extend(_hunter_checks(cache, piece_counts))
    checks.extend(_synth_checks(cache, piece_counts))
    checks.extend(_boreal_checks(cache, piece_counts))
    checks.extend(_raptor_checks(cache, piece_counts))

    return checks
