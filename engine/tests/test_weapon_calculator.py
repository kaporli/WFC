import pytest
from warframe_engine.calculator import DataCache
from warframe_engine.loadout import WeaponSlot
from warframe_engine.build import EquippedMod
from warframe_engine.weapon_calculator import compute_weapon_stats, WeaponStatSheet


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> str:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"'{name}' not found"
    return m.unique_name


def find_weapon(cache, slot: int) -> str:
    w = next((w for w in cache.weapon_by_unique_name.values() if w.slot == slot), None)
    assert w is not None, f"No weapon with slot {slot}"
    return w.unique_name


def test_base_weapon_stats(cache):
    slot = WeaponSlot(weapon_unique_name=find_weapon(cache, 0))
    sheet, cross = compute_weapon_stats(slot, cache)
    assert sheet.total_damage > 0
    assert sheet.crit_chance >= 0
    assert cross == {} or isinstance(cross, dict)


def test_serration_increases_damage(cache):
    uid = find_weapon(cache, 0)
    base_slot = WeaponSlot(weapon_unique_name=uid)
    base_sheet, _ = compute_weapon_stats(base_slot, cache)

    # Use the full-rank Serration (max_rank=10) which gives +165% at rank 10
    serration = next(
        (m for m in cache.mods if m.name == 'Serration' and m.max_rank == 10),
        None,
    )
    assert serration is not None, "Serration (max_rank=10) not found in data"
    modded_slot = WeaponSlot(weapon_unique_name=uid,
                             mods=[EquippedMod(serration.unique_name, rank=10)])
    modded_sheet, _ = compute_weapon_stats(modded_slot, cache)
    # Serration R10 = +165% → total ≈ base × 2.65
    assert modded_sheet.total_damage == pytest.approx(
        base_sheet.total_damage * 2.65, rel=0.05
    )


def test_cross_equip_amalgam(cache):
    """A melee Amalgam mod with secondary fire rate routes to cross_equip['secondary']."""
    amalgam = next(
        (m for m in cache.mods if 'Amalgam' in m.name
         and any(e.target == 'secondary' for e in m.effects)),
        None,
    )
    if amalgam is None:
        pytest.skip('No Amalgam mod with secondary cross-equip in data')

    melee_uid = find_weapon(cache, 2)
    slot = WeaponSlot(weapon_unique_name=melee_uid,
                      mods=[EquippedMod(amalgam.unique_name, amalgam.max_rank)])
    _, cross = compute_weapon_stats(slot, cache)
    assert 'secondary' in cross, f"Expected secondary in cross_equip, got: {cross}"


def test_weapon_stat_sheet_fields(cache):
    slot = WeaponSlot(weapon_unique_name=find_weapon(cache, 1))
    sheet, _ = compute_weapon_stats(slot, cache)
    assert isinstance(sheet, WeaponStatSheet)
    assert hasattr(sheet, 'total_damage')
    assert hasattr(sheet, 'crit_chance')
    assert hasattr(sheet, 'status_chance')
    assert hasattr(sheet, 'fire_rate')
