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


def find_set_mods(cache, set_fragment: str, count: int) -> list[str]:
    """Return unique_names of `count` mods from the named set."""
    mods = [m for m in cache.mods if m.mod_set and set_fragment.lower() in m.mod_set.lower()]
    assert len(mods) >= count, f"Need {count} mods from {set_fragment}, found {len(mods)}"
    return [m.unique_name for m in mods[:count]]


def find_weapon(cache, slot: int) -> str:
    w = next((w for w in cache.weapon_by_unique_name.values() if w.slot == slot), None)
    assert w is not None
    return w.unique_name


# ── Existing checks ────────────────────────────────────────────────────────────

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
        assert c.category in ('armor_strip', 'shieldgate', 'set_bonus')
        assert isinstance(c.passes, bool)
        assert isinstance(c.details, dict)


def test_armor_strip_check_exists_for_frost(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    armor_checks = [c for c in checks if c.category == 'armor_strip']
    assert len(armor_checks) >= 1


def test_armor_strip_not_passing_at_base_strength(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    armor_checks = [c for c in checks if c.category == 'armor_strip']
    if not armor_checks:
        pytest.skip('No armor strip checks found')
    assert not any(c.passes for c in armor_checks) or stats.warframe.ability_strength >= 2.5


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
    augur_accord = find_mod(cache, 'Augur Accord')
    augur_pact = find_mod(cache, 'Augur Pact')
    loadout = Loadout(
        warframe=Build(warframe_name='Frost', mods=[EquippedMod(augur_accord, rank=5)]),
        secondary=WeaponSlot(weapon_unique_name=find_weapon(cache, 1),
                             mods=[EquippedMod(augur_pact, rank=5)]),
    )
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    sg_checks = [c for c in checks if c.category == 'shieldgate']
    assert len(sg_checks) >= 1
    for c in sg_checks:
        assert 'shields_restored' in c.details
        assert 'augur_pct' in c.details
        assert c.details['augur_pct'] == pytest.approx(0.80, rel=0.01)  # 2 pieces = 80%


def test_no_shieldgate_without_conversion(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    assert not any(c.category == 'shieldgate' for c in checks)


# ── Gladiator ─────────────────────────────────────────────────────────────────

def test_gladiator_check_with_set(cache):
    # Equip 6 Gladiator mods across melee + warframe
    gladiator_uids = find_set_mods(cache, 'Gladiator', 6)
    melee_uid = find_weapon(cache, 2)

    # Put mods on melee (max 8 slots)
    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        melee=WeaponSlot(
            weapon_unique_name=melee_uid,
            mods=[EquippedMod(uid, rank=0) for uid in gladiator_uids],
        ),
    )
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    gladiator_checks = [c for c in checks if c.id == 'gladiator_melee_crit']
    assert len(gladiator_checks) == 1
    c = gladiator_checks[0]
    assert c.category == 'set_bonus'
    assert c.details['pieces'] == 6
    # 6 pieces = 0.60 per combo mult
    assert c.details['bonus_per_combo_mult'] == pytest.approx(0.60, rel=0.01)
    # At combo ×3: base_crit + 0.60*3 = base_crit + 1.80
    assert 'effective_crit_by_combo' in c.details
    assert 'x3.0' in c.details['effective_crit_by_combo']


def test_gladiator_check_absent_without_set(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    assert not any(c.id == 'gladiator_melee_crit' for c in checks)


# ── Vigilante ─────────────────────────────────────────────────────────────────

def test_vigilante_check_with_set(cache):
    vigilante_uids = find_set_mods(cache, 'Vigilante', 6)
    primary_uid = find_weapon(cache, 0)

    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        primary=WeaponSlot(
            weapon_unique_name=primary_uid,
            mods=[EquippedMod(uid, rank=0) for uid in vigilante_uids],
        ),
    )
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    vig_checks = [c for c in checks if c.id == 'vigilante_crit_enhancement']
    assert len(vig_checks) == 1
    c = vig_checks[0]
    assert c.details['pieces'] == 6
    # 6 pieces = 30% enhancement chance
    assert c.details['enhancement_chance'] == pytest.approx(0.30, rel=0.01)
    assert 'effective_avg_crit_mult' in c.details


def test_vigilante_check_absent_without_set(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    assert not any(c.id == 'vigilante_crit_enhancement' for c in checks)


# ── Hunter ────────────────────────────────────────────────────────────────────

def test_hunter_check_with_set(cache):
    hunter_uids = find_set_mods(cache, 'Hunter', 6)
    melee_uid = find_weapon(cache, 2)

    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        melee=WeaponSlot(
            weapon_unique_name=melee_uid,
            mods=[EquippedMod(uid, rank=0) for uid in hunter_uids],
        ),
    )
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    hunter_checks = [c for c in checks if c.id == 'hunter_companion_slash']
    assert len(hunter_checks) == 1
    c = hunter_checks[0]
    assert c.details['pieces'] == 6
    # 6 pieces = +150% companion damage
    assert c.details['companion_damage_bonus'] == pytest.approx(1.50, rel=0.01)
    assert c.details['companion_damage_multiplier'] == pytest.approx(2.50, rel=0.01)


# ── Boreal ────────────────────────────────────────────────────────────────────

def test_boreal_check_with_set(cache):
    boreal_uids = find_set_mods(cache, 'Boreal', 3)
    primary_uid = find_weapon(cache, 0)

    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        primary=WeaponSlot(
            weapon_unique_name=primary_uid,
            mods=[EquippedMod(uid, rank=0) for uid in boreal_uids],
        ),
    )
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    boreal_checks = [c for c in checks if c.id == 'boreal_airborne_dr']
    assert len(boreal_checks) == 1
    c = boreal_checks[0]
    assert c.details['pieces'] == 3
    # 3 pieces = 60% airborne DR
    assert c.details['damage_reduction_airborne'] == pytest.approx(0.60, rel=0.01)


# ── Synth ─────────────────────────────────────────────────────────────────────

def test_synth_check_with_set(cache):
    synth_uids = find_set_mods(cache, 'Synth', 4)
    primary_uid = find_weapon(cache, 0)

    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        primary=WeaponSlot(
            weapon_unique_name=primary_uid,
            mods=[EquippedMod(uid, rank=0) for uid in synth_uids],
        ),
    )
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    synth_checks = [c for c in checks if c.id == 'synth_holster_reload']
    assert len(synth_checks) == 1
    c = synth_checks[0]
    assert c.details['pieces'] == 4
    # 4 pieces = 20%/s reload
    assert c.details['reload_rate_per_second'] == pytest.approx(0.20, rel=0.01)
