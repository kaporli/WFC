import pytest
from warframe_engine.calculator import DataCache
from warframe_engine.build import Build, EquippedMod
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.loadout_calculator import compute_loadout
from warframe_engine.checks import run_checks, MechanicCheck


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> str:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"'{name}' not found"
    return m.unique_name


def test_run_checks_returns_list(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    assert isinstance(checks, list)


def test_mechanic_check_structure(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    for c in checks:
        assert isinstance(c, MechanicCheck)
        assert c.id
        assert c.name
        assert c.category in ('armor_strip', 'shieldgate', 'ability_threshold')
        assert isinstance(c.passes, bool)
        assert isinstance(c.details, dict)


def test_armor_strip_check_exists_for_frost(cache):
    """Frost's Avalanche has armor reduction — should produce an armor strip check."""
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    armor_checks = [c for c in checks if c.category == 'armor_strip']
    assert len(armor_checks) >= 1, f"Expected armor strip check for Frost, got: {[c.name for c in checks]}"


def test_armor_strip_not_passing_at_base_strength(cache):
    """At 100% strength, 40% base armor reduction doesn't full strip."""
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    armor_checks = [c for c in checks if c.category == 'armor_strip']
    if not armor_checks:
        pytest.skip('No armor strip checks found')
    # At base strength, none should pass full strip (would need 250% strength)
    any_passing = any(c.passes for c in armor_checks)
    # With 100% strength, 40% base strip = 40% < 100% → should not pass
    # (unless the warframe has very high base strength somehow — unlikely)
    assert not any_passing or stats.warframe.ability_strength >= 2.5


def test_armor_strip_check_has_required_strength(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    armor_checks = [c for c in checks if c.category == 'armor_strip']
    if not armor_checks:
        pytest.skip('No armor strip checks found')
    for check in armor_checks:
        assert 'required_strength' in check.details
        assert check.details['required_strength'] > 0


def test_shieldgate_check_with_augur(cache):
    """2 Augur pieces → shieldgate checks present."""
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
    checks = run_checks(loadout, stats, cache)
    sg_checks = [c for c in checks if c.category == 'shieldgate']
    assert len(sg_checks) >= 1, 'Expected shieldgate checks with Augur set'
    for c in sg_checks:
        assert 'shields_restored' in c.details or 'energy_cost' in c.details


def test_no_shieldgate_without_conversion(cache):
    """Without Brief Respite or Augur, no shieldgate checks returned."""
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    sg_checks = [c for c in checks if c.category == 'shieldgate']
    assert len(sg_checks) == 0, f"Expected no shieldgate checks without conversion mods, got: {sg_checks}"
