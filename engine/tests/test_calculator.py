import pytest
from warframe_engine.calculator import DataCache, compute_warframe_stats
from warframe_engine.build import Build, EquippedMod, ArchonShard


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> str:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"Mod '{name}' not found in data"
    return m.unique_name


def test_frost_base_stats(cache):
    build = Build(warframe_name='Frost')
    stats = compute_warframe_stats(build, cache)
    assert stats.health == pytest.approx(270, rel=0.05)
    assert stats.shield == pytest.approx(455, rel=0.05)
    assert stats.armor == pytest.approx(315, rel=0.05)
    assert stats.ability_strength == pytest.approx(1.0, rel=0.01)
    assert stats.can_shieldgate is True
    assert stats.gate_full_s == pytest.approx(1.3)


def test_vitality_max_rank(cache):
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(find_mod(cache, 'Vitality'), rank=10)],
    )
    stats = compute_warframe_stats(build, cache)
    # Vitality R10 = +100% → 270 * 2.0 = 540
    assert stats.health == pytest.approx(540, rel=0.02)


def test_vitality_mid_rank(cache):
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(find_mod(cache, 'Vitality'), rank=3)],
    )
    stats = compute_warframe_stats(build, cache)
    # R3 = +36% → 270 * 1.36 = 367.2
    assert stats.health == pytest.approx(270 * 1.36, rel=0.02)


def test_steel_fiber_max_rank(cache):
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(find_mod(cache, 'Steel Fiber'), rank=10)],
    )
    stats = compute_warframe_stats(build, cache)
    # Steel Fiber R10 = +100% armor → 315 * 2.0 = 630
    assert stats.armor == pytest.approx(630, rel=0.02)


def test_ehp_formula(cache):
    build = Build(
        warframe_name='Frost',
        mods=[
            EquippedMod(find_mod(cache, 'Vitality'), rank=10),
            EquippedMod(find_mod(cache, 'Steel Fiber'), rank=10),
        ],
    )
    stats = compute_warframe_stats(build, cache)
    # armor=630, armor_dr=630/930≈0.677, ehp=540/(1-0.677)+455
    expected_ehp = (540 / (1 - 630 / (630 + 300))) + 455
    assert stats.ehp == pytest.approx(expected_ehp, rel=0.02)


def test_ability_strength(cache):
    intensify_uid = find_mod(cache, 'Intensify')
    transient_uid = find_mod(cache, 'Transient Fortitude')
    build = Build(
        warframe_name='Rhino',
        mods=[
            EquippedMod(intensify_uid, rank=5),
            EquippedMod(transient_uid, rank=10),
        ],
    )
    stats = compute_warframe_stats(build, cache)
    # Intensify R5=+30%, Transient Fortitude R10=+55% → 1.85
    assert stats.ability_strength == pytest.approx(1.85, rel=0.02)


def test_efficiency_cap(cache):
    build = Build(
        warframe_name='Frost',
        mods=[
            EquippedMod(find_mod(cache, 'Streamline'), rank=5),
            EquippedMod(find_mod(cache, 'Fleeting Expertise'), rank=5),
        ],
    )
    stats = compute_warframe_stats(build, cache)
    # 30% + 60% = 90% → 1.90, capped at 1.75
    assert stats.ability_efficiency == pytest.approx(1.75, rel=0.01)


def test_crimson_shard_strength(cache):
    build = Build(
        warframe_name='Frost',
        shards=[ArchonShard(color='crimson', stat='abilityStrength', tauforged=False)],
    )
    stats = compute_warframe_stats(build, cache)
    assert stats.ability_strength == pytest.approx(1.10, rel=0.01)


def test_crimson_shard_strength_tauforged(cache):
    build = Build(
        warframe_name='Frost',
        shards=[ArchonShard(color='crimson', stat='abilityStrength', tauforged=True)],
    )
    stats = compute_warframe_stats(build, cache)
    assert stats.ability_strength == pytest.approx(1.15, rel=0.01)


def test_azure_flat_health_shard(cache):
    build = Build(
        warframe_name='Frost',
        shards=[ArchonShard(color='azure', stat='health', tauforged=False)],
    )
    stats = compute_warframe_stats(build, cache)
    # Azure flat +150 BEFORE mod scaling → (270+150)*1.0 = 420
    assert stats.health == pytest.approx(420, rel=0.02)
