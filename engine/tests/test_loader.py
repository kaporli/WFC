from warframe_engine.loader import (
    load_warframes, load_mods, load_arcanes, load_weapons,
    load_helmets, load_mod_sets, load_ability_stats, load_abilities_data,
    load_shard_bonuses,
    ArcaneHelmetEntry, SetBonusEntry, AbilityStatsEntry, AbilitiesData,
)


def test_warframe_has_aura_slots():
    frames = load_warframes()
    frost = next(f for f in frames if f.name == 'Frost')
    assert hasattr(frost, 'aura_slots')
    assert frost.aura_slots == 1


def test_warframe_has_initial_energy():
    frames = load_warframes()
    frost = next(f for f in frames if f.name == 'Frost')
    assert frost.initial_energy > 0


def test_mod_has_level_values():
    mods = load_mods()
    vit = next(m for m in mods if m.name == 'Vitality')
    assert len(vit.effects) > 0
    assert hasattr(vit.effects[0], 'level_values')
    assert len(vit.effects[0].level_values) == 11
    assert abs(vit.effects[0].level_values[10] - 1.0) < 0.01
    assert abs(vit.effects[0].level_values[3] - 0.36) < 0.02


def test_mod_has_augment_fields():
    mods = load_mods()
    augment = next(m for m in mods if m.is_augment)
    assert augment.compat_name is not None


def test_mod_effect_has_target():
    mods = load_mods()
    for mod in mods:
        for eff in mod.effects:
            assert eff.target in ('self', 'warframe', 'primary', 'secondary', 'melee', 'archgun', 'companion')


def test_arcane_has_level_values():
    arcanes = load_arcanes()
    energize = next((a for a in arcanes if 'Energize' in a.name), None)
    assert energize is not None
    assert len(energize.effects) > 0
    assert hasattr(energize.effects[0], 'level_values')


def test_weapons_have_slot():
    weapons = load_weapons()
    primaries = [w for w in weapons if w.slot == 0]
    secondaries = [w for w in weapons if w.slot == 1]
    melees = [w for w in weapons if w.slot == 2]
    assert len(primaries) > 0
    assert len(secondaries) > 0
    assert len(melees) > 0


def test_helmets_load():
    helmets = load_helmets()
    assert isinstance(helmets, list)
    # May be empty if ExportCustoms parsing hasn't matched yet, but must load without error
    print(f'helmets: {len(helmets)} entries')


def test_mod_sets_load():
    sets = load_mod_sets()
    assert len(sets) > 0
    augur = next((s for s in sets if 'Augur' in s.unique_name), None)
    assert augur is not None
    assert len(augur.bonus_by_piece_count) > 0
    assert augur.bonus_by_piece_count[0].pieces == 1
    assert abs(augur.bonus_by_piece_count[0].value - 0.40) < 0.01


def test_ability_stats_load():
    stats = load_ability_stats()
    assert len(stats) > 0
    armor_strip = next((a for a in stats if any(
        'armor' in b.label.lower() and 'reduction' in b.label.lower()
        for b in a.stats
    )), None)
    assert armor_strip is not None, 'Expected at least one armor-stripping ability'


def test_abilities_data_load():
    data = load_abilities_data()
    assert len(data.subsumable) >= 10
    assert len(data.augment_to_ability) >= 50
    assert 'Piercing Roar' in data.augment_to_ability


def test_shard_bonuses_load():
    shards = load_shard_bonuses()
    assert 'crimson' in shards
    assert 'azure' in shards
    crimson = shards['crimson']
    strength = next((s for s in crimson if s.stat == 'abilityStrength'), None)
    assert strength is not None
    assert abs(strength.value - 0.10) < 0.01  # +10% normal
    assert strength.conditional is False
