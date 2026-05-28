from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

# Endo Base Cost per rarity — from wiki.warframe.com/w/Fusion
# Formula: endo_cost(from_rank, to_rank) = E_BC × (2^to_rank - 2^from_rank)
_ENDO_BASE_COST: dict[str, int] = {
    'Common': 10,
    'Uncommon': 20,
    'Peculiar': 20,
    'Rare': 30,
    'Amalgam': 30,
    'Galvanized': 30,
    'Legendary': 40,
    'AntiqueMods': 160,
}

def _load_credit_costs() -> dict[str, list[int]]:
    # Look for the file in the pipeline/src/data directory
    candidates = [
        Path(__file__).parent.parent.parent / "pipeline" / "src" / "data" / "upgrade-credits.json",
        Path(__file__).parent.parent.parent / "data" / "upgrade-credits.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text())
    return {}

_CREDIT_COSTS = _load_credit_costs()


@dataclass
class UpgradeCost:
    endo: int
    credits: int


def compute_upgrade_cost(
    rarity: str,
    max_rank: int,
    from_rank: int,
    to_rank: int,
) -> UpgradeCost:
    """
    Compute endo and credit cost to upgrade a mod from from_rank to to_rank.
    Endo formula: E_BC × (2^to_rank - 2^from_rank)
    Credits: per-rank lookup from pipeline/src/data/upgrade-credits.json
    """
    if from_rank >= to_rank:
        return UpgradeCost(endo=0, credits=0)

    e_bc = _ENDO_BASE_COST.get(rarity, _ENDO_BASE_COST['Common'])
    endo = e_bc * (2 ** to_rank - 2 ** from_rank)

    credit_table = _CREDIT_COSTS.get(rarity, _CREDIT_COSTS.get('Common', []))
    credits = sum(
        credit_table[r] if r < len(credit_table) else 0
        for r in range(from_rank, to_rank)
    )

    return UpgradeCost(endo=endo, credits=credits)
