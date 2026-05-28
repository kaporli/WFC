import pytest
from warframe_engine.build import Build, EquippedMod, EquippedArcane, ArchonShard


def test_build_round_trip():
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod('/Lotus/Upgrades/Mods/Warframe/AvatarHealthMaxMod', rank=10)],
        arcanes=[],
        shards=[ArchonShard(color='crimson', stat='abilityStrength', tauforged=False)],
        exilus=None,
        auras=[EquippedMod('/Lotus/Upgrades/Mods/Warframe/AssaultMod', rank=9)],
        helmet=None,
        helminth_ability=None,
    )
    d = build.to_dict()
    restored = Build.from_dict(d)
    assert restored.warframe_name == 'Frost'
    assert len(restored.mods) == 1
    assert restored.mods[0].rank == 10
    assert restored.shards[0].color == 'crimson'
    assert restored.shards[0].tauforged is False


def test_build_defaults():
    build = Build(warframe_name='Frost')
    assert build.mods == []
    assert build.arcanes == []
    assert build.shards == []
    assert build.exilus is None
    assert build.auras == []
    assert build.helmet is None
    assert build.helminth_ability is None


def test_validate_requires_datacache():
    """validate() must accept a DataCache-like object."""
    from warframe_engine.calculator import DataCache
    cache = DataCache()
    build = Build(warframe_name='Frost')
    errors = build.validate(cache)
    assert isinstance(errors, list)
    assert errors == []  # valid build


def test_validate_unknown_warframe():
    from warframe_engine.calculator import DataCache
    cache = DataCache()
    build = Build(warframe_name='NotAWarframe')
    errors = build.validate(cache)
    assert any('warframe' in e.lower() or 'unknown' in e.lower() for e in errors)


def test_validate_augment_wrong_warframe():
    from warframe_engine.calculator import DataCache
    cache = DataCache()
    # Abating Link is a Trinity augment — invalid on Frost without Helminth
    abating_link = next((m for m in cache.mods if m.name == 'Abating Link'), None)
    if abating_link is None:
        pytest.skip('Abating Link not in data')
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(abating_link.unique_name, rank=3)],
    )
    errors = build.validate(cache)
    assert any('augment' in e.lower() for e in errors), f'Expected augment error, got: {errors}'


def test_validate_augment_valid_with_helminth():
    from warframe_engine.calculator import DataCache
    cache = DataCache()
    piercing_roar = next((m for m in cache.mods if m.name == 'Piercing Roar'), None)
    if piercing_roar is None:
        pytest.skip('Piercing Roar not in data')
    roar_unique = cache.abilities_data.augment_to_ability.get('Piercing Roar')
    if not roar_unique:
        pytest.skip('Piercing Roar not in augment map')
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(piercing_roar.unique_name, rank=3)],
        helminth_ability=roar_unique,
    )
    errors = build.validate(cache)
    assert not any('augment' in e.lower() for e in errors), f'Unexpected augment error: {errors}'


def test_validate_too_many_auras():
    from warframe_engine.calculator import DataCache
    cache = DataCache()
    build = Build(
        warframe_name='Frost',
        auras=[
            EquippedMod('/Lotus/Upgrades/Mods/Warframe/AssaultMod', rank=9),
            EquippedMod('/Lotus/Upgrades/Mods/Warframe/AssaultMod', rank=9),
        ],
    )
    errors = build.validate(cache)
    assert any('aura' in e.lower() for e in errors), f'Expected aura error, got: {errors}'


def test_validate_rank_out_of_bounds():
    from warframe_engine.calculator import DataCache
    cache = DataCache()
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod('/Lotus/Upgrades/Mods/Warframe/AvatarHealthMaxMod', rank=99)],
    )
    errors = build.validate(cache)
    assert any('rank' in e.lower() for e in errors), f'Expected rank error, got: {errors}'
