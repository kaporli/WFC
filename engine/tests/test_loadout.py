from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.build import Build, EquippedMod


def test_loadout_round_trip():
    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        primary=WeaponSlot(
            weapon_unique_name='/Lotus/Weapons/Tenno/LongGuns/TnSniperRifle/TnSniperRifle',
            mods=[EquippedMod('/Lotus/Upgrades/Mods/Rifle/RifleDamageAmountMod', rank=10)],
        ),
        secondary=None,
        melee=None,
    )
    d = loadout.to_dict()
    restored = Loadout.from_dict(d)
    assert restored.warframe.warframe_name == 'Frost'
    assert restored.primary is not None
    assert len(restored.primary.mods) == 1
    assert restored.primary.mods[0].rank == 10


def test_loadout_defaults():
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    assert loadout.primary is None
    assert loadout.secondary is None
    assert loadout.melee is None
    assert loadout.archgun is None
    assert loadout.archgun_gravimag is False
    assert loadout.companion_mods == []
    assert loadout.companion_weapon is None


def test_weapon_slot_defaults():
    slot = WeaponSlot(weapon_unique_name='/some/weapon')
    assert slot.mods == []
    assert slot.exilus is None
    assert slot.riven is None


def test_loadout_to_dict_and_back():
    loadout = Loadout(
        warframe=Build(warframe_name='Rhino'),
        melee=WeaponSlot(
            weapon_unique_name='/Lotus/Weapons/Tenno/Melee/TnSword/TnSword',
            mods=[],
        ),
        archgun_gravimag=True,
    )
    d = loadout.to_dict()
    assert d['archgun_gravimag'] is True
    assert d['melee'] is not None
    assert d['primary'] is None
    restored = Loadout.from_dict(d)
    assert restored.archgun_gravimag is True
    assert restored.melee is not None
    assert restored.primary is None
