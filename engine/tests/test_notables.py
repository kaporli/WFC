import pytest
from warframe_engine.calculator import DataCache
from warframe_engine.build import Build, EquippedMod
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.notables import get_notables, Notable


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> tuple[str, int]:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"'{name}' not found"
    return m.unique_name, m.max_rank


def find_weapon(cache, slot: int) -> str:
    w = next((w for w in cache.weapon_by_unique_name.values() if w.slot == slot), None)
    assert w is not None
    return w.unique_name


def test_notables_returns_list(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    notables = get_notables(loadout, cache)
    assert isinstance(notables, list)
    for n in notables:
        assert isinstance(n, Notable)
        assert n.source
        assert n.description
        assert n.kind in ('cross_equip_stat', 'passive', 'set_passive', 'set_stat', 'signature_weapon')


def test_amalgam_furax_passive_surfaced(cache):
    """Amalgam Furax Body Count passive should appear when on melee slot."""
    uid, rank = find_mod(cache, 'Amalgam Furax Body Count')
    melee_uid = find_weapon(cache, 2)

    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        melee=WeaponSlot(weapon_unique_name=melee_uid,
                         mods=[EquippedMod(uid, rank=rank)]),
    )
    notables = get_notables(loadout, cache)
    passive = next(
        (n for n in notables
         if n.source == 'Amalgam Furax Body Count' and n.kind == 'passive'),
        None,
    )
    assert passive is not None, 'Expected Amalgam Furax passive in notables'
    assert 'kills' in passive.description.lower() or 'blast' in passive.description.lower()


def test_amalgam_furax_cross_equip_stat_surfaced(cache):
    """Amalgam Furax Body Count should also surface its +45% secondary fire rate."""
    uid, rank = find_mod(cache, 'Amalgam Furax Body Count')
    melee_uid = find_weapon(cache, 2)

    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        melee=WeaponSlot(weapon_unique_name=melee_uid,
                         mods=[EquippedMod(uid, rank=rank)]),
    )
    notables = get_notables(loadout, cache)
    cross = next(
        (n for n in notables
         if n.source == 'Amalgam Furax Body Count' and n.kind == 'cross_equip_stat'),
        None,
    )
    assert cross is not None, 'Expected cross-equip fire rate notable from Amalgam Furax'
    assert cross.stat in ('fireRate', 'secondary_fire_rate', 'comboDuration') or cross.target == 'secondary'


def test_augur_set_notable(cache):
    """2 Augur pieces should produce a set_stat notable."""
    accord_uid, accord_rank = find_mod(cache, 'Augur Accord')
    pact_uid, pact_rank = find_mod(cache, 'Augur Pact')
    secondary_uid = find_weapon(cache, 1)

    loadout = Loadout(
        warframe=Build(warframe_name='Frost',
                       mods=[EquippedMod(accord_uid, rank=accord_rank)]),
        secondary=WeaponSlot(weapon_unique_name=secondary_uid,
                             mods=[EquippedMod(pact_uid, rank=pact_rank)]),
    )
    notables = get_notables(loadout, cache)
    set_n = next(
        (n for n in notables if n.kind in ('set_stat', 'set_passive') and 'Augur' in n.source),
        None,
    )
    assert set_n is not None, 'Expected Augur set notable'
    assert set_n.description


def test_source_attribution(cache):
    """Every notable must carry the mod/set name it came from."""
    uid, rank = find_mod(cache, 'Amalgam Serration')
    primary_uid = find_weapon(cache, 0)

    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        primary=WeaponSlot(weapon_unique_name=primary_uid,
                           mods=[EquippedMod(uid, rank=rank)]),
    )
    notables = get_notables(loadout, cache)
    serration = [n for n in notables if 'Amalgam Serration' in n.source]
    assert len(serration) >= 1, 'Expected at least one notable from Amalgam Serration'
    # Should surface +25% sprint speed cross-equip to warframe
    sprint = next((n for n in serration if n.stat and 'sprint' in n.stat.lower()), None)
    assert sprint is not None, 'Expected sprint cross-equip from Amalgam Serration'
    assert sprint.target == 'warframe'
    assert sprint.source_slot == 'primary'


def test_empty_loadout_no_cross_equip(cache):
    """A plain warframe build with no Amalgam/set mods has no cross-equip notables."""
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    notables = get_notables(loadout, cache)
    cross = [n for n in notables if n.kind == 'cross_equip_stat']
    assert len(cross) == 0


def test_signature_weapon_notable(cache):
    """Sevagoth + Epitaph should produce a signature_weapon notable."""
    # Find Epitaph in weapon cache
    epitaph = next(
        (w for w in cache.weapon_by_unique_name.values() if w.name == 'Epitaph'),
        None,
    )
    if epitaph is None:
        pytest.skip('Epitaph not in weapons data')
    if not cache.signature_weapon_bonuses:
        pytest.skip('signature-weapons.json empty (run full pipeline first)')

    loadout = Loadout(
        warframe=Build(warframe_name='Sevagoth'),
        secondary=WeaponSlot(weapon_unique_name=epitaph.unique_name),
    )
    notables = get_notables(loadout, cache)
    sig = next((n for n in notables if n.kind == 'signature_weapon'), None)
    assert sig is not None, 'Expected signature_weapon notable for Sevagoth + Epitaph'
    assert sig.source == 'Epitaph'
    assert sig.source_slot == 'secondary'
    assert '20%' in sig.description or 'headshot' in sig.description.lower()


def test_no_signature_notable_wrong_warframe(cache):
    """Epitaph on a different warframe should not produce a signature notable."""
    epitaph = next(
        (w for w in cache.weapon_by_unique_name.values() if w.name == 'Epitaph'),
        None,
    )
    if epitaph is None:
        pytest.skip('Epitaph not in weapons data')

    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        secondary=WeaponSlot(weapon_unique_name=epitaph.unique_name),
    )
    notables = get_notables(loadout, cache)
    sig = [n for n in notables if n.kind == 'signature_weapon']
    assert len(sig) == 0, f'Expected no signature notable for Frost + Epitaph, got: {sig}'
