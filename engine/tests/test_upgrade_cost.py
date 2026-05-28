import pytest
from warframe_engine.upgrade_cost import compute_upgrade_cost, UpgradeCost


def test_common_rank_0_to_1():
    # Common E_BC = 10; endo = 10 × (2^1 - 2^0) = 10
    result = compute_upgrade_cost('Common', max_rank=5, from_rank=0, to_rank=1)
    assert isinstance(result, UpgradeCost)
    assert result.endo == 10


def test_common_rank_0_to_5():
    # Common E_BC = 10; endo = 10 × (2^5 - 2^0) = 10 × 31 = 310
    result = compute_upgrade_cost('Common', max_rank=5, from_rank=0, to_rank=5)
    assert result.endo == 310


def test_uncommon_rank_0_to_1():
    # Uncommon E_BC = 20; endo = 20 × 1 = 20
    result = compute_upgrade_cost('Uncommon', max_rank=5, from_rank=0, to_rank=1)
    assert result.endo == 20


def test_rare_rank_0_to_5():
    # Rare E_BC = 30; endo = 30 × 31 = 930
    result = compute_upgrade_cost('Rare', max_rank=5, from_rank=0, to_rank=5)
    assert result.endo == 930


def test_legendary_rank_5_to_10():
    # Legendary E_BC = 40; endo = 40 × (2^10 - 2^5) = 40 × 992 = 39680
    result = compute_upgrade_cost('Legendary', max_rank=10, from_rank=5, to_rank=10)
    assert result.endo == 39680


def test_same_rank_zero_cost():
    result = compute_upgrade_cost('Common', max_rank=5, from_rank=3, to_rank=3)
    assert result.endo == 0
    assert result.credits == 0


def test_credits_non_negative():
    for rarity in ('Common', 'Uncommon', 'Rare', 'Legendary'):
        result = compute_upgrade_cost(rarity, max_rank=5, from_rank=0, to_rank=5)
        assert result.credits >= 0


def test_endo_increases_with_rank():
    r1 = compute_upgrade_cost('Common', max_rank=10, from_rank=0, to_rank=1)
    r5 = compute_upgrade_cost('Common', max_rank=10, from_rank=0, to_rank=5)
    assert r5.endo > r1.endo


def test_upgrade_cost_fields():
    result = compute_upgrade_cost('Common', max_rank=5, from_rank=0, to_rank=1)
    assert hasattr(result, 'endo')
    assert hasattr(result, 'credits')
