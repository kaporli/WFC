import pytest
from warframe_engine.calculator import DataCache
from warframe_engine.build import Build, EquippedMod
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.loadout_calculator import compute_loadout, LoadoutStats


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> str:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"'{name}' not found"
    return m.unique_name


def test_warframe_only_loadout(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    assert isinstance(stats, LoadoutStats)
    assert stats.warframe.health == pytest.approx(270, rel=0.05)
    assert stats.primary is None
    assert stats.secondary is None
    assert stats.melee is None


def test_loadout_returns_weapon_stats(cache):
    primary_uid = next(
        w.unique_name for w in cache.weapon_by_unique_name.values() if w.slot == 0
    )
    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        primary=WeaponSlot(weapon_unique_name=primary_uid),
    )
    stats = compute_loadout(loadout, cache)
    assert stats.primary is not None
    assert stats.primary.total_damage > 0


def test_cross_equip_sprint_from_amalgam_serration(cache):
    """Amalgam Serration on primary gives +25% sprint speed to warframe."""
    amalgam_serration = next(
        (m for m in cache.mods if m.name == 'Amalgam Serration'), None
    )
    if amalgam_serration is None:
        pytest.skip('Amalgam Serration not in data')

    primary_uid = next(
        w.unique_name for w in cache.weapon_by_unique_name.values() if w.slot == 0
    )
    base_loadout = Loadout(warframe=Build(warframe_name='Frost'))
    base_stats = compute_loadout(base_loadout, cache)

    modded_loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        primary=WeaponSlot(
            weapon_unique_name=primary_uid,
            mods=[EquippedMod(amalgam_serration.unique_name, rank=amalgam_serration.max_rank)],
        ),
    )
    modded_stats = compute_loadout(modded_loadout, cache)
    assert modded_stats.warframe.sprint > base_stats.warframe.sprint


def test_augur_set_2_pieces(cache):
    """2 Augur pieces across warframe + secondary = 80% set bonus counted."""
    augur_accord = find_mod(cache, 'Augur Accord')
    augur_pact = find_mod(cache, 'Augur Pact')
    secondary_uid = next(
        w.unique_name for w in cache.weapon_by_unique_name.values() if w.slot == 1
    )
    loadout = Loadout(
        warframe=Build(
            warframe_name='Frost',
            mods=[EquippedMod(augur_accord, rank=5)],
        ),
        secondary=WeaponSlot(
            weapon_unique_name=secondary_uid,
            mods=[EquippedMod(augur_pact, rank=5)],
        ),
    )
    stats = compute_loadout(loadout, cache)
    # Just verify it runs without error; set bonus effect (energy->shield)
    # is checked in the mechanic checks layer
    assert stats.warframe.health > 0
    assert stats.secondary is not None
