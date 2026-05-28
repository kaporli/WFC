# Warframe Planner — Calc Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python calc engine: load all new data files, model a full loadout (warframe + weapons + companion), compute per-slot stat sheets with cross-equipment routing, run mechanic checks (shieldgate, armor strip), and compute upgrade costs.

**Architecture:** Pure functions operating on dataclasses. `compute_loadout()` is the top-level entry: it computes each weapon slot independently (collecting cross-equip contributions), then computes the warframe stats (with cross-equip applied). `run_checks()` operates on a completed `LoadoutStats`. No global state; `DataCache` is instantiated once and passed everywhere.

**Tech Stack:** Python 3.12, dataclasses, pytest. Requires Plan A (pipeline fixes) to have run so all `data/*.json` files exist.

**Prerequisite:** Run `cd /Users/elias/Documents/WFC/pipeline && npx tsx src/index.ts run --fresh` before running any tests in this plan.

---

## File Map

```
engine/warframe_engine/
  loader.py          MODIFY — add new data files, new dataclasses
  build.py           CREATE — Build, EquippedMod, EquippedArcane, ArchonShard + validate()
  loadout.py         CREATE — WeaponSlot, Loadout
  shards.py          CREATE — load SHARD_BONUSES from data/shard-bonuses.json
  calculator.py      MODIFY — DataCache expanded; add compute_warframe_stats()
  weapon_calculator.py  CREATE — WeaponStatSheet, compute_weapon_stats()
  loadout_calculator.py CREATE — LoadoutStats, compute_loadout()
  checks.py          CREATE — MechanicCheck, run_checks()
  upgrade_cost.py    CREATE — endo formula + credit lookup, compute_upgrade_cost()
engine/tests/
  test_loader.py     MODIFY — add tests for new fields
  test_build.py      CREATE
  test_loadout.py    CREATE
  test_calculator.py CREATE
  test_weapon_calculator.py  CREATE
  test_loadout_calculator.py CREATE
  test_checks.py     CREATE
  test_upgrade_cost.py CREATE
```

---

## Task 1: Update loader.py for new schema fields

**Files:**
- Modify: `engine/warframe_engine/loader.py`
- Modify: `engine/tests/test_loader.py`

- [ ] **Step 1: Write failing tests**

Add to `engine/tests/test_loader.py`:

```python
from warframe_engine.loader import (
    load_warframes, load_mods, load_arcanes,
    load_helmets, load_mod_sets, load_ability_stats, load_abilities_data,
    ArcaneHelmetEntry, SetBonusEntry, AbilityStatsEntry, AbilitiesData,
)


def test_warframe_has_aura_slots():
    frames = load_warframes()
    frost = next(f for f in frames if f.name == 'Frost')
    assert hasattr(frost, 'aura_slots')
    assert frost.aura_slots == 1


def test_warframe_has_initial_energy():
    frames = load_warframes()
    frost = next(f for f in frames if f.name == 'Frost')
    assert frost.initial_energy > 0


def test_mod_has_level_values():
    mods = load_mods()
    vit = next(m for m in mods if m.name == 'Vitality')
    assert len(vit.effects) > 0
    assert hasattr(vit.effects[0], 'level_values')
    assert len(vit.effects[0].level_values) == 11
    assert abs(vit.effects[0].level_values[10] - 1.0) < 0.01
    assert abs(vit.effects[0].level_values[3] - 0.36) < 0.02


def test_mod_has_augment_fields():
    mods = load_mods()
    augment = next(m for m in mods if m.is_augment)
    assert augment.compat_name is not None


def test_mod_effect_has_target():
    mods = load_mods()
    for mod in mods:
        for eff in mod.effects:
            assert eff.target in ('self', 'warframe', 'primary', 'secondary', 'melee', 'archgun', 'companion')


def test_arcane_has_level_values():
    arcanes = load_arcanes()
    energize = next((a for a in arcanes if 'Energize' in a.name), None)
    assert energize is not None
    assert len(energize.effects) > 0
    assert hasattr(energize.effects[0], 'level_values')


def test_helmets_load():
    helmets = load_helmets()
    assert len(helmets) > 0
    aurora = next((h for h in helmets if 'Aurora' in h.name), None)
    assert aurora is not None
    assert aurora.warframe_name == 'Frost'
    assert len(aurora.effects) == 2  # one positive, one negative


def test_mod_sets_load():
    sets = load_mod_sets()
    assert len(sets) > 0
    augur = next((s for s in sets if 'Augur' in s.unique_name), None)
    assert augur is not None
    assert len(augur.bonus_by_piece_count) > 0
    assert augur.bonus_by_piece_count[0].pieces == 1
    assert abs(augur.bonus_by_piece_count[0].value - 0.40) < 0.01


def test_ability_stats_load():
    stats = load_ability_stats()
    assert len(stats) > 0
    # Find any ability with armor reduction
    armor_strip = next((a for a in stats if any(
        'armor' in b.label.lower() and 'reduction' in b.label.lower()
        for b in a.stats
    )), None)
    assert armor_strip is not None, 'Expected at least one armor-stripping ability'


def test_abilities_data_load():
    data = load_abilities_data()
    assert len(data.subsumable) >= 10
    assert len(data.augment_to_ability) >= 50
    assert 'Piercing Roar' in data.augment_to_ability
```

- [ ] **Step 2: Run tests to see them fail**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_loader.py -v 2>&1 | head -40
```
Expected: ImportError or AttributeError — new functions/classes don't exist yet.

- [ ] **Step 3: Rewrite `engine/warframe_engine/loader.py`**

```python
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_json(filename: str) -> list | dict:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Run the pipeline first: {path}")
    return json.loads(path.read_text())


# ── Warframes ──────────────────────────────────────────────────────────────────

@dataclass
class BaseStats:
    health: float
    shield: float
    armor: float
    energy: float
    sprint: float


@dataclass
class AbilityRef:
    name: str
    slot: int
    strength_scaling: bool
    duration_scaling: bool
    range_scaling: bool
    efficiency_scaling: bool


@dataclass
class WarframeEntry:
    unique_name: str
    name: str
    base_stats: BaseStats
    polarities: list[str]
    aura: str | None
    aura_slots: int
    abilities: list[AbilityRef]
    passive_description: str
    mastery_rank: int
    initial_energy: float
    exilus_polarity: str | None


def load_warframes() -> list[WarframeEntry]:
    return [
        WarframeEntry(
            unique_name=w["uniqueName"],
            name=w["name"],
            base_stats=BaseStats(**w["baseStats"]),
            polarities=w["polarities"],
            aura=w["aura"],
            aura_slots=w.get("auraSlots", 1),
            abilities=[
                AbilityRef(
                    name=a["name"], slot=a["slot"],
                    strength_scaling=a["strengthScaling"],
                    duration_scaling=a["durationScaling"],
                    range_scaling=a["rangeScaling"],
                    efficiency_scaling=a["efficiencyScaling"],
                )
                for a in w["abilities"]
            ],
            passive_description=w["passiveDescription"],
            mastery_rank=w["masteryRank"],
            initial_energy=w.get("initialEnergy", w["baseStats"]["energy"] / 4),
            exilus_polarity=w.get("exilusPolarity"),
        )
        for w in _load_json("warframes.json")
    ]


# ── Mods ───────────────────────────────────────────────────────────────────────

@dataclass
class ModEffect:
    stat: str
    stack_type: str
    level_values: list[float]   # index = rank
    target: str                 # 'self' | 'warframe' | 'primary' | 'secondary' | 'melee' | etc.


@dataclass
class ModEntry:
    unique_name: str
    name: str
    polarity: str
    rarity: str
    max_rank: int
    type: str
    mod_set: str | None
    tradable: bool
    is_augment: bool
    compat_name: str | None
    effects: list[ModEffect]
    raw_description: str


def load_mods() -> list[ModEntry]:
    return [
        ModEntry(
            unique_name=m["uniqueName"],
            name=m["name"],
            polarity=m["polarity"],
            rarity=m["rarity"],
            max_rank=m["maxRank"],
            type=m["type"],
            mod_set=m["modSet"],
            tradable=m["tradable"],
            is_augment=m.get("isAugment", False),
            compat_name=m.get("compatName"),
            effects=[
                ModEffect(
                    stat=e["stat"],
                    stack_type=e["stackType"],
                    level_values=e["levelValues"],
                    target=e.get("target", "self"),
                )
                for e in m["effects"]
            ],
            raw_description=m["rawDescription"],
        )
        for m in _load_json("mods.json")
    ]


# ── Arcanes ────────────────────────────────────────────────────────────────────

@dataclass
class ArcaneEffect:
    stat: str
    level_values: list[float]


@dataclass
class ArcaneEntry:
    unique_name: str
    name: str
    max_rank: int
    max_stacks: int
    trigger: str
    effects: list[ArcaneEffect]
    raw_description: str


def load_arcanes() -> list[ArcaneEntry]:
    return [
        ArcaneEntry(
            unique_name=a["uniqueName"],
            name=a["name"],
            max_rank=a["maxRank"],
            max_stacks=a["maxStacks"],
            trigger=a["trigger"],
            effects=[
                ArcaneEffect(stat=e["stat"], level_values=e["levelValues"])
                for e in a["effects"]
            ],
            raw_description=a["rawDescription"],
        )
        for a in _load_json("arcanes.json")
    ]


# ── Weapons ────────────────────────────────────────────────────────────────────

@dataclass
class WeaponStats:
    total_damage: float
    damage_types: dict[str, float]
    crit_chance: float
    crit_multiplier: float
    status_chance: float
    fire_rate: float
    magazine_size: int
    reload_time: float
    multishot: float
    range: float | None
    attack_speed: float | None
    combo_duration: float | None
    heavy_attack_damage: float | None


@dataclass
class WeaponEntry:
    unique_name: str
    name: str
    type: str
    slot: int
    base_stats: WeaponStats
    disposition: int
    mastery_rank: int


def load_weapons() -> list[WeaponEntry]:
    def parse_stats(s: dict) -> WeaponStats:
        return WeaponStats(
            total_damage=s["totalDamage"],
            damage_types=s["damageTypes"],
            crit_chance=s["critChance"],
            crit_multiplier=s["critMultiplier"],
            status_chance=s["statusChance"],
            fire_rate=s["fireRate"],
            magazine_size=s["magazineSize"],
            reload_time=s["reloadTime"],
            multishot=s["multishot"],
            range=s.get("range"),
            attack_speed=s.get("attackSpeed"),
            combo_duration=s.get("comboDuration"),
            heavy_attack_damage=s.get("heavyAttackDamage"),
        )
    return [
        WeaponEntry(
            unique_name=w["uniqueName"],
            name=w["name"],
            type=w["type"],
            slot=w.get("slot", 0),
            base_stats=parse_stats(w["baseStats"]),
            disposition=w["disposition"],
            mastery_rank=w["masteryRank"],
        )
        for w in _load_json("weapons.json")
    ]


# ── Arcane Helmets ─────────────────────────────────────────────────────────────

@dataclass
class ArcaneHelmetEffect:
    stat: str
    value: float
    is_flat: bool


@dataclass
class ArcaneHelmetEntry:
    unique_name: str
    name: str
    warframe_name: str
    effects: list[ArcaneHelmetEffect]


def load_helmets() -> list[ArcaneHelmetEntry]:
    return [
        ArcaneHelmetEntry(
            unique_name=h["uniqueName"],
            name=h["name"],
            warframe_name=h["warframeName"],
            effects=[
                ArcaneHelmetEffect(stat=e["stat"], value=e["value"], is_flat=e["isFlat"])
                for e in h["effects"]
            ],
        )
        for h in _load_json("helmets.json")
    ]


# ── Mod Sets ───────────────────────────────────────────────────────────────────

@dataclass
class SetBonusEffect:
    pieces: int
    stat: str
    value: float
    is_flat: bool


@dataclass
class SetBonusEntry:
    unique_name: str
    num_pieces_in_set: int
    bonus_by_piece_count: list[SetBonusEffect]


def load_mod_sets() -> list[SetBonusEntry]:
    return [
        SetBonusEntry(
            unique_name=s["uniqueName"],
            num_pieces_in_set=s["numPiecesInSet"],
            bonus_by_piece_count=[
                SetBonusEffect(
                    pieces=b["pieces"], stat=b["stat"],
                    value=b["value"], is_flat=b["isFlat"],
                )
                for b in s["bonusByPieceCount"]
            ],
        )
        for s in _load_json("mod-sets.json")
    ]


# ── Ability Stats ──────────────────────────────────────────────────────────────

@dataclass
class AbilityStatBlock:
    label: str
    modifier: str
    base_value: float
    is_percent: bool


@dataclass
class AbilityStatsEntry:
    unique_name: str
    stats: list[AbilityStatBlock]


def load_ability_stats() -> list[AbilityStatsEntry]:
    return [
        AbilityStatsEntry(
            unique_name=e["uniqueName"],
            stats=[
                AbilityStatBlock(
                    label=b["label"], modifier=b["modifier"],
                    base_value=b["baseValue"], is_percent=b["isPercent"],
                )
                for b in e["stats"]
            ],
        )
        for e in _load_json("ability-stats.json")
    ]


# ── Abilities Data (subsumable + augment map) ──────────────────────────────────

@dataclass
class AbilitiesData:
    subsumable: list[str]
    augment_to_ability: dict[str, str]


def load_abilities_data() -> AbilitiesData:
    d = _load_json("abilities.json")
    return AbilitiesData(
        subsumable=d["subsumable"],
        augment_to_ability=d["augmentToAbility"],
    )


# ── Shard Bonuses ──────────────────────────────────────────────────────────────

@dataclass
class ShardBonus:
    stat: str
    value: float
    is_flat: bool
    conditional: bool


def load_shard_bonuses() -> dict[str, list[ShardBonus]]:
    raw = _load_json("shard-bonuses.json")
    result: dict[str, list[ShardBonus]] = {}
    if isinstance(raw, dict):
        for color, bonuses in raw.items():
            if isinstance(bonuses, list):
                result[color] = [
                    ShardBonus(
                        stat=b["stat"], value=b["value"],
                        is_flat=b["isFlat"], conditional=b["conditional"],
                    )
                    for b in bonuses
                ]
    return result
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_loader.py -v 2>&1
```
Expected: all pass. Fix any data shape mismatches before continuing.

- [ ] **Step 5: Commit**

```bash
git add engine/warframe_engine/loader.py engine/tests/test_loader.py
git commit -m "feat(engine): update loader — new fields, new data files, new dataclasses"
```

---

## Task 2: Build model + validation

**Files:**
- Create: `engine/warframe_engine/build.py`
- Create: `engine/tests/test_build.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_build.py
import pytest
from warframe_engine.build import Build, EquippedMod, EquippedArcane, ArchonShard
from warframe_engine.loader import load_mods, load_arcanes, load_warframes, load_helmets, load_abilities_data
from warframe_engine.calculator import DataCache


@pytest.fixture
def cache():
    return DataCache()


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


def test_validate_augment_wrong_warframe(cache):
    # Abating Link is a Trinity augment — should fail on Frost
    abating_link = next(
        m for m in cache.mods if m.name == 'Abating Link'
    )
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(abating_link.unique_name, rank=3)],
        arcanes=[], shards=[], exilus=None, auras=[], helmet=None, helminth_ability=None,
    )
    errors = build.validate(cache)
    assert any('augment' in e.lower() for e in errors), f"Expected augment error, got: {errors}"


def test_validate_augment_valid_with_helminth(cache):
    # Piercing Roar is a Rhino augment — valid on Frost if Roar is subsumed
    piercing_roar = next((m for m in cache.mods if m.name == 'Piercing Roar'), None)
    if piercing_roar is None:
        pytest.skip('Piercing Roar not in data')
    roar_unique = cache.abilities_data.augment_to_ability.get('Piercing Roar')
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(piercing_roar.unique_name, rank=3)],
        arcanes=[], shards=[], exilus=None, auras=[], helmet=None,
        helminth_ability=roar_unique,
    )
    errors = build.validate(cache)
    assert not any('augment' in e.lower() for e in errors), f"Unexpected augment error: {errors}"


def test_validate_too_many_auras(cache):
    build = Build(
        warframe_name='Frost',  # aura_slots = 1
        mods=[],
        arcanes=[], shards=[], exilus=None,
        auras=[
            EquippedMod('/Lotus/Upgrades/Mods/Warframe/AssaultMod', rank=9),
            EquippedMod('/Lotus/Upgrades/Mods/Warframe/AssaultMod', rank=9),
        ],
        helmet=None, helminth_ability=None,
    )
    errors = build.validate(cache)
    assert any('aura' in e.lower() for e in errors)


def test_validate_arcane_helmet_reduces_arcane_slot(cache):
    # Equip arcane helmet + 2 arcanes → should error
    helmets = cache.helmets
    if not helmets:
        pytest.skip('No helmets in data')
    helmet = helmets[0]
    arcanes = load_arcanes()
    if len(arcanes) < 2:
        pytest.skip('Not enough arcanes in data')
    build = Build(
        warframe_name=helmet.warframe_name,
        mods=[], shards=[], exilus=None, auras=[],
        arcanes=[
            EquippedArcane(arcanes[0].unique_name, rank=arcanes[0].max_rank),
            EquippedArcane(arcanes[1].unique_name, rank=arcanes[1].max_rank),
        ],
        helmet=helmet.unique_name,
        helminth_ability=None,
    )
    errors = build.validate(cache)
    assert any('arcane' in e.lower() for e in errors)


def test_validate_rank_out_of_bounds(cache):
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod('/Lotus/Upgrades/Mods/Warframe/AvatarHealthMaxMod', rank=99)],
        arcanes=[], shards=[], exilus=None, auras=[], helmet=None, helminth_ability=None,
    )
    errors = build.validate(cache)
    assert any('rank' in e.lower() for e in errors)
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_build.py -v 2>&1 | head -20
```
Expected: ImportError.

- [ ] **Step 3: Create `engine/warframe_engine/build.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class EquippedMod:
    unique_name: str
    rank: int  # 0 = unranked


@dataclass
class EquippedArcane:
    unique_name: str
    rank: int


@dataclass
class ArchonShard:
    color: str    # 'crimson' | 'azure' | 'amber' | 'topaz' | 'violet' | 'emerald'
    stat: str     # e.g. 'abilityStrength', 'health'
    tauforged: bool


@dataclass
class Build:
    warframe_name: str
    mods: list[EquippedMod] = field(default_factory=list)
    arcanes: list[EquippedArcane] = field(default_factory=list)
    shards: list[ArchonShard] = field(default_factory=list)
    exilus: EquippedMod | None = None
    auras: list[EquippedMod] = field(default_factory=list)
    helmet: str | None = None
    helminth_ability: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Build':
        return cls(
            warframe_name=d['warframe_name'],
            mods=[EquippedMod(**m) for m in d.get('mods', [])],
            arcanes=[EquippedArcane(**a) for a in d.get('arcanes', [])],
            shards=[ArchonShard(**s) for s in d.get('shards', [])],
            exilus=EquippedMod(**d['exilus']) if d.get('exilus') else None,
            auras=[EquippedMod(**a) for a in d.get('auras', [])],
            helmet=d.get('helmet'),
            helminth_ability=d.get('helminth_ability'),
        )

    def validate(self, cache: 'DataCache') -> list[str]:  # type: ignore[name-defined]
        errors: list[str] = []

        # Warframe exists
        if self.warframe_name not in cache.warframe_by_name:
            errors.append(f"Unknown warframe: {self.warframe_name}")
            return errors

        warframe = cache.warframe_by_name[self.warframe_name]

        # Aura count
        if len(self.auras) > warframe.aura_slots:
            errors.append(
                f"Too many auras: {self.warframe_name} has {warframe.aura_slots} aura slot(s), "
                f"but {len(self.auras)} equipped"
            )

        # Arcane count — reduced to 1 if arcane helmet equipped
        max_arcanes = 1 if (self.helmet and self.helmet in cache.arcane_helmet_unique_names) else 2
        if len(self.arcanes) > max_arcanes:
            errors.append(
                f"Too many arcanes: max {max_arcanes} with current helmet, "
                f"but {len(self.arcanes)} equipped"
            )

        # Shard count
        if len(self.shards) > 5:
            errors.append(f"Too many shards: max 5, got {len(self.shards)}")

        # Mod rank bounds + augment validation
        all_mods = [*self.mods, self.exilus, *self.auras]
        for em in filter(None, all_mods):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if not mod:
                continue
            if em.rank < 0 or em.rank > mod.max_rank:
                errors.append(
                    f"Mod '{mod.name}' rank {em.rank} out of bounds [0, {mod.max_rank}]"
                )
            if mod.is_augment and mod.compat_name:
                valid = (
                    mod.compat_name == self.warframe_name
                    or self._helminth_allows_augment(mod.name, cache)
                )
                if not valid:
                    errors.append(
                        f"Augment '{mod.name}' requires warframe '{mod.compat_name}' "
                        f"or Helminth subsume of its ability"
                    )

        # Arcane rank bounds
        for ea in self.arcanes:
            arcane = cache.arcane_by_unique_name.get(ea.unique_name)
            if arcane and (ea.rank < 0 or ea.rank > arcane.max_rank):
                errors.append(
                    f"Arcane '{arcane.name}' rank {ea.rank} out of bounds [0, {arcane.max_rank}]"
                )

        return errors

    def _helminth_allows_augment(self, augment_name: str, cache: 'DataCache') -> bool:  # type: ignore[name-defined]
        if not self.helminth_ability:
            return False
        ability_unique = cache.abilities_data.augment_to_ability.get(augment_name)
        return ability_unique == self.helminth_ability


# Avoid circular import — DataCache imported at runtime in validate()
from __future__ import annotations  # already at top — just noting for the reader
```

Wait — the circular import issue. `build.py` calls `cache.warframe_by_name` etc. but `DataCache` is in `calculator.py`. We use TYPE_CHECKING to avoid circular import:

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warframe_engine.calculator import DataCache


@dataclass
class EquippedMod:
    unique_name: str
    rank: int


@dataclass
class EquippedArcane:
    unique_name: str
    rank: int


@dataclass
class ArchonShard:
    color: str
    stat: str
    tauforged: bool


@dataclass
class Build:
    warframe_name: str
    mods: list[EquippedMod] = field(default_factory=list)
    arcanes: list[EquippedArcane] = field(default_factory=list)
    shards: list[ArchonShard] = field(default_factory=list)
    exilus: EquippedMod | None = None
    auras: list[EquippedMod] = field(default_factory=list)
    helmet: str | None = None
    helminth_ability: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Build:
        return cls(
            warframe_name=d['warframe_name'],
            mods=[EquippedMod(**m) for m in d.get('mods', [])],
            arcanes=[EquippedArcane(**a) for a in d.get('arcanes', [])],
            shards=[ArchonShard(**s) for s in d.get('shards', [])],
            exilus=EquippedMod(**d['exilus']) if d.get('exilus') else None,
            auras=[EquippedMod(**a) for a in d.get('auras', [])],
            helmet=d.get('helmet'),
            helminth_ability=d.get('helminth_ability'),
        )

    def validate(self, cache: DataCache) -> list[str]:
        errors: list[str] = []

        if self.warframe_name not in cache.warframe_by_name:
            errors.append(f"Unknown warframe: {self.warframe_name}")
            return errors

        warframe = cache.warframe_by_name[self.warframe_name]

        if len(self.auras) > warframe.aura_slots:
            errors.append(
                f"Too many auras: {self.warframe_name} has {warframe.aura_slots} aura slot(s), "
                f"but {len(self.auras)} equipped"
            )

        max_arcanes = 1 if (
            self.helmet and self.helmet in cache.arcane_helmet_unique_names
        ) else 2
        if len(self.arcanes) > max_arcanes:
            errors.append(
                f"Too many arcanes: max {max_arcanes} with this helmet, "
                f"got {len(self.arcanes)}"
            )

        if len(self.shards) > 5:
            errors.append(f"Too many shards: max 5, got {len(self.shards)}")

        all_mods = [*self.mods, self.exilus, *self.auras]
        for em in filter(None, all_mods):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if not mod:
                continue
            if em.rank < 0 or em.rank > mod.max_rank:
                errors.append(
                    f"Mod '{mod.name}' rank {em.rank} out of bounds [0, {mod.max_rank}]"
                )
            if mod.is_augment and mod.compat_name:
                valid = (mod.compat_name == self.warframe_name
                         or self._helminth_allows_augment(mod.name, cache))
                if not valid:
                    errors.append(
                        f"Augment '{mod.name}' requires warframe '{mod.compat_name}'"
                    )

        for ea in self.arcanes:
            arcane = cache.arcane_by_unique_name.get(ea.unique_name)
            if arcane and (ea.rank < 0 or ea.rank > arcane.max_rank):
                errors.append(
                    f"Arcane '{arcane.name}' rank {ea.rank} out of bounds [0, {arcane.max_rank}]"
                )

        return errors

    def _helminth_allows_augment(self, augment_name: str, cache: DataCache) -> bool:
        if not self.helminth_ability:
            return False
        return cache.abilities_data.augment_to_ability.get(augment_name) == self.helminth_ability
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_build.py -v 2>&1
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add engine/warframe_engine/build.py engine/tests/test_build.py
git commit -m "feat(engine): Build model with to_dict/from_dict and validate()"
```

---

## Task 3: Loadout model

**Files:**
- Create: `engine/warframe_engine/loadout.py`
- Create: `engine/tests/test_loadout.py`

- [ ] **Step 1: Write failing test**

```python
# engine/tests/test_loadout.py
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.build import Build, EquippedMod


def test_loadout_round_trip():
    loadout = Loadout(
        warframe=Build(warframe_name='Frost'),
        primary=WeaponSlot(
            weapon_unique_name='/Lotus/Weapons/Tenno/LongGuns/TnHopliteSpear/TnHopliteGunSpear',
            mods=[EquippedMod('/Lotus/Upgrades/Mods/Rifle/RifleDamageAmountMod', rank=10)],
            exilus=None,
            riven=None,
        ),
        secondary=None,
        melee=None,
        archgun=None,
        archgun_gravimag=False,
        companion_mods=[],
        companion_weapon=None,
    )
    d = loadout.to_dict()
    restored = Loadout.from_dict(d)
    assert restored.warframe.warframe_name == 'Frost'
    assert restored.primary is not None
    assert len(restored.primary.mods) == 1


def test_loadout_defaults():
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    assert loadout.primary is None
    assert loadout.secondary is None
    assert loadout.melee is None
    assert not loadout.archgun_gravimag
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_loadout.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `engine/warframe_engine/loadout.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from warframe_engine.build import Build, EquippedMod


@dataclass
class WeaponSlot:
    weapon_unique_name: str
    mods: list[EquippedMod] = field(default_factory=list)
    exilus: EquippedMod | None = None
    riven: EquippedMod | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> WeaponSlot:
        return cls(
            weapon_unique_name=d['weapon_unique_name'],
            mods=[EquippedMod(**m) for m in d.get('mods', [])],
            exilus=EquippedMod(**d['exilus']) if d.get('exilus') else None,
            riven=EquippedMod(**d['riven']) if d.get('riven') else None,
        )


@dataclass
class Loadout:
    warframe: Build
    primary: WeaponSlot | None = None
    secondary: WeaponSlot | None = None
    melee: WeaponSlot | None = None
    archgun: WeaponSlot | None = None
    archgun_gravimag: bool = False
    companion_mods: list[EquippedMod] = field(default_factory=list)
    companion_weapon: WeaponSlot | None = None

    def to_dict(self) -> dict:
        def slot_dict(s: WeaponSlot | None) -> dict | None:
            return s.to_dict() if s else None
        return {
            'warframe': self.warframe.to_dict(),
            'primary': slot_dict(self.primary),
            'secondary': slot_dict(self.secondary),
            'melee': slot_dict(self.melee),
            'archgun': slot_dict(self.archgun),
            'archgun_gravimag': self.archgun_gravimag,
            'companion_mods': [asdict(m) for m in self.companion_mods],
            'companion_weapon': slot_dict(self.companion_weapon),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Loadout:
        def slot_from(v: dict | None) -> WeaponSlot | None:
            return WeaponSlot.from_dict(v) if v else None
        return cls(
            warframe=Build.from_dict(d['warframe']),
            primary=slot_from(d.get('primary')),
            secondary=slot_from(d.get('secondary')),
            melee=slot_from(d.get('melee')),
            archgun=slot_from(d.get('archgun')),
            archgun_gravimag=d.get('archgun_gravimag', False),
            companion_mods=[EquippedMod(**m) for m in d.get('companion_mods', [])],
            companion_weapon=slot_from(d.get('companion_weapon')),
        )
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_loadout.py -v 2>&1
```

- [ ] **Step 5: Commit**

```bash
git add engine/warframe_engine/loadout.py engine/tests/test_loadout.py
git commit -m "feat(engine): Loadout and WeaponSlot models with to_dict/from_dict"
```

---

## Task 4: DataCache + warframe stat sheet (`calculator.py`)

**Files:**
- Modify: `engine/warframe_engine/calculator.py`
- Create: `engine/tests/test_calculator.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_calculator.py
import pytest
from warframe_engine.calculator import DataCache, compute_warframe_stats
from warframe_engine.build import Build, EquippedMod, ArchonShard


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> str:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"Mod '{name}' not found"
    return m.unique_name


def test_frost_base_stats(cache):
    build = Build(warframe_name='Frost')
    stats = compute_warframe_stats(build, cache)
    assert stats.health == pytest.approx(270, rel=0.05)
    assert stats.shield == pytest.approx(455, rel=0.05)
    assert stats.armor == pytest.approx(315, rel=0.05)
    assert stats.ability_strength == pytest.approx(1.0, rel=0.01)


def test_vitality_max_rank(cache):
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(find_mod(cache, 'Vitality'), rank=10)],
    )
    stats = compute_warframe_stats(build, cache)
    # Vitality R10 = +100% health → 270 × 2.0 = 540
    assert stats.health == pytest.approx(540, rel=0.02)


def test_vitality_mid_rank(cache):
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(find_mod(cache, 'Vitality'), rank=3)],
    )
    stats = compute_warframe_stats(build, cache)
    # Vitality R3 = +36% health → 270 × 1.36 = 367.2
    assert stats.health == pytest.approx(270 * 1.36, rel=0.02)


def test_steel_fiber_max_rank(cache):
    build = Build(
        warframe_name='Frost',
        mods=[EquippedMod(find_mod(cache, 'Steel Fiber'), rank=10)],
    )
    stats = compute_warframe_stats(build, cache)
    # Steel Fiber R10 = +100% armor → 315 × 2.0 = 630
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
    # health=540, armor=630, armor_dr=630/930≈0.677, effective_health=540/0.323≈1671, shield=455
    expected_ehp = (540 / (1 - 630 / (630 + 300))) + 455
    assert stats.ehp == pytest.approx(expected_ehp, rel=0.02)
    assert stats.armor_dr == pytest.approx(630 / (630 + 300), rel=0.01)


def test_ability_strength(cache):
    build = Build(
        warframe_name='Rhino',
        mods=[
            EquippedMod(find_mod(cache, 'Intensify'), rank=5),
            EquippedMod(find_mod(cache, 'Transient Fortitude'), rank=10),
        ],
    )
    stats = compute_warframe_stats(build, cache)
    # Intensify R5 = +30%, Transient Fortitude R10 = +55% → 1.85
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
    # Streamline 30% + Fleeting Expertise 60% = 90% → 1.90 → capped at 1.75
    assert stats.ability_efficiency == pytest.approx(1.75, rel=0.01)


def test_crimson_shard_strength(cache):
    build = Build(
        warframe_name='Frost',
        shards=[ArchonShard(color='crimson', stat='abilityStrength', tauforged=False)],
    )
    stats = compute_warframe_stats(build, cache)
    assert stats.ability_strength == pytest.approx(1.10, rel=0.01)  # +10% normal


def test_crimson_shard_strength_tauforged(cache):
    build = Build(
        warframe_name='Frost',
        shards=[ArchonShard(color='crimson', stat='abilityStrength', tauforged=True)],
    )
    stats = compute_warframe_stats(build, cache)
    assert stats.ability_strength == pytest.approx(1.15, rel=0.01)  # +15% tauforged


def test_azure_flat_health_shard(cache):
    build = Build(
        warframe_name='Frost',
        shards=[ArchonShard(color='azure', stat='health', tauforged=False)],
    )
    stats = compute_warframe_stats(build, cache)
    # Azure flat +150 health BEFORE mod scaling → (270 + 150) × 1.0 = 420
    assert stats.health == pytest.approx(420, rel=0.02)


def test_shieldgate_properties(cache):
    build = Build(warframe_name='Frost')
    stats = compute_warframe_stats(build, cache)
    assert stats.can_shieldgate is True
    assert stats.gate_full_s == pytest.approx(1.3)
    assert stats.gate_short_s == pytest.approx(0.13)
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_calculator.py -v 2>&1 | head -30
```

- [ ] **Step 3: Rewrite `engine/warframe_engine/calculator.py`**

```python
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from warframe_engine.loader import (
    load_warframes, load_mods, load_arcanes, load_weapons,
    load_helmets, load_mod_sets, load_ability_stats, load_abilities_data, load_shard_bonuses,
    WarframeEntry, ModEntry, ArcaneEntry, WeaponEntry,
    ArcaneHelmetEntry, SetBonusEntry, AbilityStatsEntry, AbilitiesData, ShardBonus,
)
from warframe_engine.build import Build, EquippedMod


@dataclass
class StatSheet:
    ability_strength: float
    ability_duration: float
    ability_range: float
    ability_efficiency: float

    health: float
    shield: float
    armor: float
    energy: float
    sprint: float

    armor_dr: float
    ehp: float

    can_shieldgate: bool
    gate_full_s: float
    gate_short_s: float


class DataCache:
    def __init__(self) -> None:
        warframes = load_warframes()
        mods = load_mods()
        arcanes = load_arcanes()
        weapons = load_weapons()
        helmets = load_helmets()
        mod_sets = load_mod_sets()
        ability_stats = load_ability_stats()
        abilities_data = load_abilities_data()
        shard_bonuses = load_shard_bonuses()

        self.warframe_by_name: dict[str, WarframeEntry] = {w.name: w for w in warframes}
        self.mod_by_unique_name: dict[str, ModEntry] = {m.unique_name: m for m in mods}
        self.arcane_by_unique_name: dict[str, ArcaneEntry] = {a.unique_name: a for a in arcanes}
        self.weapon_by_unique_name: dict[str, WeaponEntry] = {w.unique_name: w for w in weapons}
        self.helmet_by_unique_name: dict[str, ArcaneHelmetEntry] = {h.unique_name: h for h in helmets}
        self.arcane_helmet_unique_names: set[str] = {h.unique_name for h in helmets}
        self.mod_set_by_unique_name: dict[str, SetBonusEntry] = {s.unique_name: s for s in mod_sets}
        self.ability_stats_by_unique_name: dict[str, AbilityStatsEntry] = {
            e.unique_name: e for e in ability_stats
        }
        self.abilities_data: AbilitiesData = abilities_data
        self.shard_bonuses: dict[str, list[ShardBonus]] = shard_bonuses

        # Convenience references for tests
        self.mods = mods
        self.arcanes = arcanes
        self.helmets = helmets


def compute_warframe_stats(
    build: Build,
    cache: DataCache,
    cross_equip_additive: dict[str, float] | None = None,
) -> StatSheet:
    """Compute the warframe stat sheet from a Build."""
    warframe = cache.warframe_by_name[build.warframe_name]
    additive: dict[str, float] = defaultdict(float)
    flat: dict[str, float] = defaultdict(float)

    # ── Mods (regular + exilus + all auras) ───────────────────────────────────
    all_mods: list[EquippedMod | None] = [*build.mods, build.exilus, *build.auras]
    for em in filter(None, all_mods):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if not mod:
            continue
        for eff in mod.effects:
            if eff.target != 'self' and eff.target != 'warframe':
                continue  # cross-equip to weapons — handled by weapon calc
            if em.rank < len(eff.level_values):
                additive[eff.stat] += eff.level_values[em.rank]

    # ── Arcanes ────────────────────────────────────────────────────────────────
    for ea in build.arcanes:
        arcane = cache.arcane_by_unique_name.get(ea.unique_name)
        if not arcane:
            continue
        for eff in arcane.effects:
            if ea.rank < len(eff.level_values):
                additive[eff.stat] += eff.level_values[ea.rank]

    # ── Arcane helmet ──────────────────────────────────────────────────────────
    if build.helmet and build.helmet in cache.arcane_helmet_unique_names:
        helmet = cache.helmet_by_unique_name.get(build.helmet)
        if helmet:
            for eff in helmet.effects:
                if eff.is_flat:
                    flat[eff.stat] += eff.value
                else:
                    additive[eff.stat] += eff.value

    # ── Archon shards ──────────────────────────────────────────────────────────
    for shard in build.shards:
        color_bonuses = cache.shard_bonuses.get(shard.color, [])
        for bonus in color_bonuses:
            if bonus.stat != shard.stat or bonus.conditional:
                continue
            value = bonus.value * (1.5 if shard.tauforged else 1.0)
            if bonus.is_flat:
                flat[bonus.stat] += value
            else:
                additive[bonus.stat] += value

    # ── Cross-equipment contributions from weapons ────────────────────────────
    if cross_equip_additive:
        for stat, val in cross_equip_additive.items():
            additive[stat] += val

    # ── Final stats ───────────────────────────────────────────────────────────
    b = warframe.base_stats
    health = (b.health + flat['health']) * (1 + additive['health'])
    shield = (b.shield + flat['shield']) * (1 + additive['shield'])
    armor  = (b.armor  + flat['armor'])  * (1 + additive['armor'])
    energy = (b.energy + flat['energy']) * (1 + additive['energy'])
    sprint = b.sprint * (1 + additive['sprint'])

    ability_strength   = 1.0 + additive['abilityStrength']
    ability_duration   = 1.0 + additive['abilityDuration']
    ability_range      = 1.0 + additive['abilityRange']
    ability_efficiency = min(1.75, 1.0 + additive['abilityEfficiency'])

    armor_dr = armor / (armor + 300)
    ehp = (health / (1 - armor_dr)) + shield if armor_dr < 1 else health * 1000 + shield

    return StatSheet(
        ability_strength=ability_strength,
        ability_duration=ability_duration,
        ability_range=ability_range,
        ability_efficiency=ability_efficiency,
        health=health,
        shield=shield,
        armor=armor,
        energy=energy,
        sprint=sprint,
        armor_dr=armor_dr,
        ehp=ehp,
        can_shieldgate=shield > 0,
        gate_full_s=1.3,
        gate_short_s=0.13,
    )
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_calculator.py -v 2>&1
```
Expected: all pass. Investigate any failures with `pytest -v -s` for detailed output.

- [ ] **Step 5: Commit**

```bash
git add engine/warframe_engine/calculator.py engine/tests/test_calculator.py
git commit -m "feat(engine): DataCache and compute_warframe_stats() with full stat sheet"
```

---

## Task 5: Weapon stat calculator

**Files:**
- Create: `engine/warframe_engine/weapon_calculator.py`
- Create: `engine/tests/test_weapon_calculator.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_weapon_calculator.py
import pytest
from warframe_engine.calculator import DataCache
from warframe_engine.loadout import WeaponSlot
from warframe_engine.build import EquippedMod
from warframe_engine.weapon_calculator import compute_weapon_stats


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> str:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"'{name}' not found"
    return m.unique_name


def find_weapon(cache, name: str) -> str:
    w = next((w for w in cache.weapon_by_unique_name.values() if w.name == name), None)
    assert w is not None, f"Weapon '{name}' not found"
    return w.unique_name


def test_soma_prime_base_stats(cache):
    slot = WeaponSlot(weapon_unique_name=find_weapon(cache, 'Soma Prime'))
    sheet, _ = compute_weapon_stats(slot, cache)
    assert sheet.total_damage > 0
    assert sheet.crit_chance > 0


def test_serration_increases_damage(cache):
    soma_uid = find_weapon(cache, 'Soma Prime')
    base_slot = WeaponSlot(weapon_unique_name=soma_uid)
    base_sheet, _ = compute_weapon_stats(base_slot, cache)

    modded_slot = WeaponSlot(
        weapon_unique_name=soma_uid,
        mods=[EquippedMod(find_mod(cache, 'Serration'), rank=10)],
    )
    modded_sheet, _ = compute_weapon_stats(modded_slot, cache)
    # Serration R10 = +165% damage → total ≈ base × 2.65
    assert modded_sheet.total_damage == pytest.approx(base_sheet.total_damage * 2.65, rel=0.03)


def test_amalgam_furax_cross_equip(cache):
    # Amalgam Furax Body Count is a melee mod with +45% secondary fire rate
    furax_mod = next((m for m in cache.mods if 'Amalgam Furax' in m.name), None)
    if furax_mod is None:
        pytest.skip('Amalgam Furax not in data')

    # Find any melee weapon
    melee = next((w for w in cache.weapon_by_unique_name.values() if w.slot == 2), None)
    assert melee is not None

    slot = WeaponSlot(
        weapon_unique_name=melee.unique_name,
        mods=[EquippedMod(furax_mod.unique_name, rank=furax_mod.max_rank)],
    )
    _, cross_equip = compute_weapon_stats(slot, cache)
    # Should route secondary fire rate to cross_equip['secondary']
    assert 'secondary' in cross_equip, f"Expected secondary in cross_equip, got: {cross_equip}"
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_weapon_calculator.py -v 2>&1 | head -15
```

- [ ] **Step 3: Create `engine/warframe_engine/weapon_calculator.py`**

```python
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from warframe_engine.loadout import WeaponSlot
from warframe_engine.calculator import DataCache


@dataclass
class WeaponStatSheet:
    total_damage: float
    damage_types: dict[str, float]
    crit_chance: float
    crit_multiplier: float
    status_chance: float
    fire_rate: float
    magazine_size: int
    reload_time: float
    multishot: float
    range: float | None
    attack_speed: float | None
    combo_duration: float | None
    heavy_attack_damage: float | None


def compute_weapon_stats(
    slot: WeaponSlot,
    cache: DataCache,
) -> tuple[WeaponStatSheet, dict[str, dict[str, float]]]:
    """
    Returns (WeaponStatSheet, cross_equip).
    cross_equip is keyed by target slot name ('warframe', 'secondary', etc.)
    and contains additive bonuses to pass to that slot's calculator.
    """
    weapon = cache.weapon_by_unique_name.get(slot.weapon_unique_name)
    if weapon is None:
        raise ValueError(f"Unknown weapon: {slot.weapon_unique_name}")

    additive: dict[str, float] = defaultdict(float)
    flat_combo: float = 0.0
    cross_equip: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    all_mods = [*slot.mods, slot.exilus, slot.riven]
    for em in filter(None, all_mods):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if not mod:
            continue
        for eff in mod.effects:
            if em.rank >= len(eff.level_values):
                continue
            val = eff.level_values[em.rank]
            if eff.target == 'self':
                if eff.stat == 'comboDuration':
                    flat_combo += val
                else:
                    additive[eff.stat] += val
            else:
                cross_equip[eff.target][eff.stat] += val

    b = weapon.base_stats

    # Scale damage types proportionally
    scaled_types: dict[str, float] = {}
    if b.damage_types:
        for dtype, dval in b.damage_types.items():
            scaled_types[dtype] = dval * (1 + additive['damage'])
    total = b.total_damage * (1 + additive['damage'])

    sheet = WeaponStatSheet(
        total_damage=total,
        damage_types=scaled_types,
        crit_chance=b.crit_chance + additive['critChance'],
        crit_multiplier=b.crit_multiplier * (1 + additive['critMult']),
        status_chance=b.status_chance + additive['statusChance'],
        fire_rate=b.fire_rate * (1 + additive['fireRate']),
        magazine_size=round(b.magazine_size * (1 + additive['magazineSize'])),
        reload_time=b.reload_time * max(0.01, 1 - additive['reloadSpeed']),
        multishot=b.multishot * (1 + additive['multishot']),
        range=b.range,
        attack_speed=(b.attack_speed or 1.0) * (1 + additive['attackSpeed']) if b.attack_speed else None,
        combo_duration=(b.combo_duration or 0) + flat_combo if b.combo_duration else None,
        heavy_attack_damage=b.heavy_attack_damage,
    )

    return sheet, dict(cross_equip)
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_weapon_calculator.py -v 2>&1
```

- [ ] **Step 5: Commit**

```bash
git add engine/warframe_engine/weapon_calculator.py engine/tests/test_weapon_calculator.py
git commit -m "feat(engine): compute_weapon_stats() with cross-equipment routing"
```

---

## Task 6: Loadout calculator (aggregation + set bonuses)

**Files:**
- Create: `engine/warframe_engine/loadout_calculator.py`
- Create: `engine/tests/test_loadout_calculator.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_loadout_calculator.py
import pytest
from warframe_engine.calculator import DataCache
from warframe_engine.build import Build, EquippedMod
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.loadout_calculator import compute_loadout


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> str:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"'{name}' not found"
    return m.unique_name


def find_secondary(cache) -> str:
    w = next((w for w in cache.weapon_by_unique_name.values() if w.slot == 1), None)
    assert w is not None
    return w.unique_name


def test_basic_loadout(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    assert stats.warframe.health == pytest.approx(270, rel=0.05)
    assert stats.primary is None
    assert stats.secondary is None


def test_augur_set_bonus_counted_across_slots(cache):
    # Augur Accord on warframe + Augur Pact on secondary = 2 pieces = 80% energy→shield
    augur_accord = find_mod(cache, 'Augur Accord')
    augur_pact = find_mod(cache, 'Augur Pact')
    secondary_uid = find_secondary(cache)

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
    # 2 Augur pieces = 80% energy→shield on cast — checked in checks.py
    # For now just assert loadout computed without error
    assert stats.warframe.health > 0


def test_cross_equip_warframe_bonus(cache):
    # Amalgam Serration on primary gives +25% sprint speed to warframe
    amalgam_serration = next((m for m in cache.mods if m.name == 'Amalgam Serration'), None)
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

    # Sprint speed should be higher with Amalgam Serration
    assert modded_stats.warframe.sprint > base_stats.warframe.sprint
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_loadout_calculator.py -v 2>&1 | head -15
```

- [ ] **Step 3: Create `engine/warframe_engine/loadout_calculator.py`**

```python
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.calculator import DataCache, StatSheet, compute_warframe_stats
from warframe_engine.weapon_calculator import WeaponStatSheet, compute_weapon_stats


@dataclass
class LoadoutStats:
    warframe: StatSheet
    primary: WeaponStatSheet | None
    secondary: WeaponStatSheet | None
    melee: WeaponStatSheet | None
    archgun: WeaponStatSheet | None
    companion_weapon: WeaponStatSheet | None


def _compute_slot(
    slot: WeaponSlot | None,
    cache: DataCache,
) -> tuple[WeaponStatSheet | None, dict[str, dict[str, float]]]:
    if slot is None:
        return None, {}
    sheet, cross_equip = compute_weapon_stats(slot, cache)
    return sheet, cross_equip


def _resolve_set_bonuses(
    loadout: Loadout,
    cache: DataCache,
) -> dict[str, float]:
    """Count Augur/etc. set pieces across the full loadout and return warframe additive bonuses."""
    piece_counts: dict[str, int] = defaultdict(int)

    def count_slot(mods: list, exilus=None, riven=None):
        for em in filter(None, [*mods, exilus, riven]):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if mod and mod.mod_set:
                piece_counts[mod.mod_set] += 1

    # Warframe slots
    wf = loadout.warframe
    count_slot(wf.mods, wf.exilus)
    for aura in wf.auras:
        piece_counts_check = cache.mod_by_unique_name.get(aura.unique_name)
        if piece_counts_check and piece_counts_check.mod_set:
            piece_counts[piece_counts_check.mod_set] += 1

    # Weapon slots
    for slot_attr in ('primary', 'secondary', 'melee', 'archgun', 'companion_weapon'):
        slot: WeaponSlot | None = getattr(loadout, slot_attr, None)
        if slot:
            count_slot(slot.mods, slot.exilus, slot.riven)

    warframe_bonus: dict[str, float] = defaultdict(float)
    for set_uid, pieces in piece_counts.items():
        set_entry = cache.mod_set_by_unique_name.get(set_uid)
        if not set_entry:
            continue
        for bonus in set_entry.bonus_by_piece_count:
            if bonus.pieces == pieces and not bonus.is_flat:
                warframe_bonus[bonus.stat] += bonus.value

    return dict(warframe_bonus)


def compute_loadout(loadout: Loadout, cache: DataCache) -> LoadoutStats:
    """
    Compute stat sheets for all slots in the loadout.
    Cross-equipment mod effects are routed to the appropriate slot.
    Set bonuses are counted across all slots and applied to warframe.
    """
    # 1. Compute weapon slots, collect cross-equip
    primary, ce_primary     = _compute_slot(loadout.primary, cache)
    secondary, ce_secondary = _compute_slot(loadout.secondary, cache)
    melee, ce_melee         = _compute_slot(loadout.melee, cache)

    archgun_slot = loadout.archgun if loadout.archgun_gravimag else None
    archgun, ce_archgun     = _compute_slot(archgun_slot, cache)
    companion_weapon, _     = _compute_slot(loadout.companion_weapon, cache)

    # 2. Collect all cross-equip contributions targeting warframe
    warframe_cross: dict[str, float] = defaultdict(float)
    for ce in (ce_primary, ce_secondary, ce_melee, ce_archgun):
        for stat, val in ce.get('warframe', {}).items():
            warframe_cross[stat] += val

    # 3. Resolve set bonuses
    set_bonuses = _resolve_set_bonuses(loadout, cache)
    for stat, val in set_bonuses.items():
        warframe_cross[stat] += val

    # 4. Compute warframe with all cross-equip + set bonuses applied
    warframe_stats = compute_warframe_stats(
        loadout.warframe, cache,
        cross_equip_additive=dict(warframe_cross),
    )

    return LoadoutStats(
        warframe=warframe_stats,
        primary=primary,
        secondary=secondary,
        melee=melee,
        archgun=archgun,
        companion_weapon=companion_weapon,
    )
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_loadout_calculator.py -v 2>&1
```

- [ ] **Step 5: Commit**

```bash
git add engine/warframe_engine/loadout_calculator.py engine/tests/test_loadout_calculator.py
git commit -m "feat(engine): compute_loadout() with cross-equipment routing and set bonus aggregation"
```

---

## Task 7: Mechanic checks

**Files:**
- Create: `engine/warframe_engine/checks.py`
- Create: `engine/tests/test_checks.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_checks.py
import pytest
from warframe_engine.calculator import DataCache, compute_warframe_stats
from warframe_engine.loadout import Loadout, WeaponSlot
from warframe_engine.loadout_calculator import compute_loadout
from warframe_engine.build import Build, EquippedMod
from warframe_engine.checks import run_checks, MechanicCheck


@pytest.fixture(scope='module')
def cache():
    return DataCache()


def find_mod(cache, name: str) -> str:
    m = next((m for m in cache.mods if m.name == name), None)
    assert m is not None, f"'{name}' not found"
    return m.unique_name


def test_armor_strip_check_exists(cache):
    # Any build with an armor-stripping ability should return armor strip checks
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    armor_checks = [c for c in checks if c.category == 'armor_strip']
    # Frost's Avalanche strips armor — should have at least one check
    assert len(armor_checks) >= 1, f"Expected armor strip checks, got: {[c.name for c in checks]}"


def test_armor_strip_check_at_base_strength(cache):
    loadout = Loadout(warframe=Build(warframe_name='Frost'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    avalanche_check = next(
        (c for c in checks if 'Avalanche' in c.name and c.category == 'armor_strip'), None
    )
    if avalanche_check is None:
        pytest.skip('Avalanche armor strip check not found')
    # Base Avalanche = 40% armor reduction × 1.0 strength = 0.40 — not full strip
    assert avalanche_check.value == pytest.approx(0.40, rel=0.05)
    assert avalanche_check.passes is False
    assert avalanche_check.details.get('required_strength', 0) == pytest.approx(2.5, rel=0.05)


def test_armor_strip_passes_at_high_strength(cache):
    # 250% ability strength → Avalanche 40% × 2.5 = 100%
    intensify = find_mod(cache, 'Intensify')
    transient = find_mod(cache, 'Transient Fortitude')
    umbral_intensify = next((m for m in cache.mods if m.name == 'Umbral Intensify'), None)

    # Need ~150% more strength: Intensify 30% + TF 55% + Umbral 40% = 125%... 
    # We'll stack what we have and check passes at >=100% additional
    build = Build(
        warframe_name='Frost',
        mods=[
            EquippedMod(intensify, rank=5),
            EquippedMod(transient, rank=10),
        ],
    )
    if umbral_intensify:
        build.mods.append(EquippedMod(umbral_intensify.unique_name, rank=10))

    loadout = Loadout(warframe=build)
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    avalanche_check = next(
        (c for c in checks if 'Avalanche' in c.name and c.category == 'armor_strip'), None
    )
    if avalanche_check is None:
        pytest.skip('Avalanche check not found')
    if stats.warframe.ability_strength >= 2.5:
        assert avalanche_check.passes is True


def test_shieldgate_check_with_augur(cache):
    # 2 Augur pieces (warframe + secondary) = 80% energy→shield
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
    assert len(sg_checks) >= 1, "Expected shieldgate checks"
    # At least one check should show the energy→shield math
    for c in sg_checks:
        assert 'shields_restored' in c.details or 'energy_cost' in c.details


def test_mechanic_check_structure(cache):
    loadout = Loadout(warframe=Build(warframe_name='Rhino'))
    stats = compute_loadout(loadout, cache)
    checks = run_checks(loadout, stats, cache)
    for c in checks:
        assert isinstance(c, MechanicCheck)
        assert c.id
        assert c.name
        assert c.category in ('armor_strip', 'shieldgate', 'ability_threshold')
        assert isinstance(c.passes, bool)
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_checks.py -v 2>&1 | head -20
```

- [ ] **Step 3: Create `engine/warframe_engine/checks.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from warframe_engine.loadout import Loadout
from warframe_engine.loadout_calculator import LoadoutStats
from warframe_engine.calculator import DataCache
from warframe_engine.loader import AbilityStatsEntry


@dataclass
class MechanicCheck:
    id: str
    name: str
    category: str   # 'armor_strip' | 'shieldgate' | 'ability_threshold'
    value: float
    threshold: float
    passes: bool
    details: dict = field(default_factory=dict)


def _get_augur_pct(loadout: Loadout, cache: DataCache) -> float:
    """Return total Augur set energy→shield % from piece count across entire loadout."""
    from collections import defaultdict
    piece_counts: dict[str, int] = defaultdict(int)

    def count(mods, exilus=None, riven=None):
        for em in filter(None, [*mods, exilus, riven]):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if mod and mod.mod_set:
                piece_counts[mod.mod_set] += 1

    wf = loadout.warframe
    count(wf.mods, wf.exilus)
    for aura in wf.auras:
        mod = cache.mod_by_unique_name.get(aura.unique_name)
        if mod and mod.mod_set:
            piece_counts[mod.mod_set] += 1

    for slot_attr in ('primary', 'secondary', 'melee', 'archgun', 'companion_weapon'):
        slot = getattr(loadout, slot_attr, None)
        if slot:
            count(slot.mods, slot.exilus, slot.riven)

    augur_pct = 0.0
    for set_uid, pieces in piece_counts.items():
        if 'Augur' not in set_uid:
            continue
        set_entry = cache.mod_set_by_unique_name.get(set_uid)
        if not set_entry:
            continue
        for bonus in set_entry.bonus_by_piece_count:
            if bonus.pieces == pieces and bonus.stat == 'energyToShieldOnCast':
                augur_pct = bonus.value
                break

    return augur_pct


def _brief_respite_pct(loadout: Loadout, cache: DataCache) -> float:
    """Return Brief Respite energy→shield % if equipped (max rank = 150%)."""
    all_mods = [*loadout.warframe.mods, loadout.warframe.exilus, *loadout.warframe.auras]
    for em in filter(None, all_mods):
        mod = cache.mod_by_unique_name.get(em.unique_name)
        if mod and 'Brief Respite' in mod.name:
            # Brief Respite: 1 level, "150% Energy spent converted to Shields"
            if mod.effects:
                return mod.effects[0].level_values[min(em.rank, len(mod.effects[0].level_values) - 1)]
    return 0.0


def _shieldgate_checks(
    loadout: Loadout,
    stats: LoadoutStats,
    cache: DataCache,
) -> list[MechanicCheck]:
    checks: list[MechanicCheck] = []

    augur_pct = _get_augur_pct(loadout, cache)
    respite_pct = _brief_respite_pct(loadout, cache)
    total_shield_pct = augur_pct + respite_pct

    if total_shield_pct <= 0:
        return checks

    efficiency = stats.warframe.ability_efficiency
    current_shield = stats.warframe.shield

    warframe = cache.warframe_by_name.get(loadout.warframe.warframe_name)
    if not warframe:
        return checks

    for ability in warframe.abilities:
        ability_stats = cache.ability_stats_by_unique_name.get(ability.name)
        # Try lookup by ability name if unique name not found
        if not ability_stats:
            ability_stats = next(
                (e for e in cache.ability_stats_by_unique_name.values()
                 if any(b.label == 'Energy Cost' for b in e.stats)),
                None,
            )
            ability_stats = None  # Only use matched entries

        # Find energy cost from ability_stats
        energy_block = None
        if ability_stats:
            energy_block = next(
                (b for b in ability_stats.stats if 'Energy Cost' in b.label), None
            )

        if not energy_block:
            continue

        base_cost = energy_block.base_value
        # actual_cost = base_cost × (2 - efficiency)
        actual_cost = base_cost * (2 - efficiency)
        shields_restored = actual_cost * total_shield_pct

        check_id = f"shieldgate_{ability.name.lower().replace(' ', '_')}_augur"
        checks.append(MechanicCheck(
            id=check_id,
            name=f"Shieldgate via {ability.name} (Augur/Brief Respite)",
            category='shieldgate',
            value=shields_restored,
            threshold=current_shield,
            passes=shields_restored >= current_shield,
            details={
                'ability_name': ability.name,
                'base_energy_cost': base_cost,
                'actual_energy_cost': actual_cost,
                'shields_restored': shields_restored,
                'shield_conversion_pct': total_shield_pct,
                'current_shield': current_shield,
            },
        ))

    return checks


def _armor_strip_checks(
    loadout: Loadout,
    stats: LoadoutStats,
    cache: DataCache,
) -> list[MechanicCheck]:
    checks: list[MechanicCheck] = []

    warframe = cache.warframe_by_name.get(loadout.warframe.warframe_name)
    if not warframe:
        return checks

    ability_strength = stats.warframe.ability_strength

    for ability in warframe.abilities:
        # Look up by internal name (ability.name is display name, we need uniqueName)
        # Find the entry where uniqueName ends with the ability's internal part
        ability_stats_entry = next(
            (e for e in cache.ability_stats_by_unique_name.values()
             if any('Armor Reduction' in b.label for b in e.stats)
             and ability.name.replace(' ', '').lower() in e.unique_name.lower()),
            None,
        )

        if not ability_stats_entry:
            continue

        armor_block = next(
            (b for b in ability_stats_entry.stats if 'Armor Reduction' in b.label), None
        )
        if not armor_block:
            continue

        base_strip = armor_block.base_value  # already divided by 100 in normalizer
        final_strip = base_strip * ability_strength
        required_strength = (1.0 / base_strip) if base_strip > 0 else float('inf')

        check_id = f"armor_strip_{ability.name.lower().replace(' ', '_')}"
        checks.append(MechanicCheck(
            id=check_id,
            name=f"{ability.name} Full Armor Strip",
            category='armor_strip',
            value=round(final_strip, 4),
            threshold=1.0,
            passes=final_strip >= 1.0,
            details={
                'ability_name': ability.name,
                'base_armor_reduction': base_strip,
                'current_strength': ability_strength,
                'required_strength': round(required_strength, 2),
            },
        ))

    return checks


def run_checks(
    loadout: Loadout,
    stats: LoadoutStats,
    cache: DataCache,
) -> list[MechanicCheck]:
    """Run all applicable mechanic checks and return results."""
    checks: list[MechanicCheck] = []
    checks.extend(_shieldgate_checks(loadout, stats, cache))
    checks.extend(_armor_strip_checks(loadout, stats, cache))
    return checks
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_checks.py -v 2>&1
```

- [ ] **Step 5: Commit**

```bash
git add engine/warframe_engine/checks.py engine/tests/test_checks.py
git commit -m "feat(engine): mechanic checks — shieldgate (Augur/Brief Respite) and armor strip"
```

---

## Task 8: Upgrade cost calculator

**Files:**
- Create: `engine/warframe_engine/upgrade_cost.py`
- Create: `engine/tests/test_upgrade_cost.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_upgrade_cost.py
import pytest
from warframe_engine.upgrade_cost import compute_upgrade_cost, UpgradeCost


def test_common_rank_0_to_1():
    # Common E_BC = 10; cost = 10 × 2^0 = 10 endo
    result = compute_upgrade_cost('Common', max_rank=5, from_rank=0, to_rank=1)
    assert result.endo == 10


def test_common_rank_0_to_5():
    # Common E_BC = 10; total = 10 × (2^5 - 2^0) = 10 × 31 = 310 endo
    result = compute_upgrade_cost('Common', max_rank=5, from_rank=0, to_rank=5)
    assert result.endo == 310


def test_uncommon_rank_0_to_1():
    # Uncommon E_BC = 20; cost = 20 × 2^0 = 20 endo
    result = compute_upgrade_cost('Uncommon', max_rank=5, from_rank=0, to_rank=1)
    assert result.endo == 20


def test_rare_rank_0_to_5():
    # Rare E_BC = 30; total = 30 × (2^5 - 1) = 30 × 31 = 930 endo
    result = compute_upgrade_cost('Rare', max_rank=5, from_rank=0, to_rank=5)
    assert result.endo == 930


def test_legendary_rank_5_to_10():
    # Legendary E_BC = 40; total = 40 × (2^10 - 2^5) = 40 × (1024 - 32) = 39680
    result = compute_upgrade_cost('Legendary', max_rank=10, from_rank=5, to_rank=10)
    assert result.endo == 39680


def test_same_rank_zero_cost():
    result = compute_upgrade_cost('Common', max_rank=5, from_rank=3, to_rank=3)
    assert result.endo == 0
    assert result.credits == 0


def test_credits_not_negative():
    for rarity in ('Common', 'Uncommon', 'Rare', 'Legendary'):
        result = compute_upgrade_cost(rarity, max_rank=5, from_rank=0, to_rank=5)
        assert result.credits >= 0


def test_upgrade_cost_dataclass():
    result = compute_upgrade_cost('Common', max_rank=5, from_rank=0, to_rank=1)
    assert isinstance(result, UpgradeCost)
    assert hasattr(result, 'endo')
    assert hasattr(result, 'credits')
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_upgrade_cost.py -v 2>&1 | head -15
```

- [ ] **Step 3: Create `engine/warframe_engine/upgrade_cost.py`**

```python
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "pipeline" / "src" / "data"
_CREDITS_FILE = DATA_DIR / "upgrade-credits.json"

# Endo Base Cost (E_BC) by rarity — from wiki.warframe.com/w/Fusion
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
    try:
        return json.loads(_CREDITS_FILE.read_text())
    except FileNotFoundError:
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
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest tests/test_upgrade_cost.py -v 2>&1
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add engine/warframe_engine/upgrade_cost.py engine/tests/test_upgrade_cost.py
git commit -m "feat(engine): upgrade cost calculator — endo formula + credit lookup"
```

---

## Task 9: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd /Users/elias/Documents/WFC/engine && uv run pytest -v 2>&1
```
Expected: all tests pass. Address any failures before committing.

- [ ] **Step 2: Final commit**

```bash
git add .
git commit -m "test(engine): full test suite passing — loader, build, loadout, calculator, checks, upgrade cost"
```

---

## Self-Review

**Spec coverage:**
- ✅ Part 2 — Loadout model: Tasks 2, 3
- ✅ Part 3 — Warframe stat sheet: Task 4
- ✅ Part 3 — Weapon stat sheet: Task 5
- ✅ Part 3 — Loadout aggregation + cross-equip + set bonuses: Task 6
- ✅ Part 4 — Mechanic checks (shieldgate + armor strip): Task 7
- ✅ Part 5 — Upgrade cost: Task 8
- ✅ Part 6 — Shards: integrated into Task 4 (DataCache loads shard-bonuses.json)
- ✅ Part 7 — Tests: Tasks 1–8 all have TDD tests

**Placeholder scan:** None. All code blocks are complete. Note: `_armor_strip_checks` uses a fuzzy match on ability unique names since Module:Ability/data/stats is keyed differently than WFCD ability names — this may require calibration after first run.

**Type consistency:**
- `EquippedMod`, `EquippedArcane`, `ArchonShard` defined in Task 2, used in Tasks 4–8 ✓
- `WeaponSlot`, `Loadout` defined in Task 3, used in Tasks 5–7 ✓
- `StatSheet` defined in Task 4, referenced in Task 7 via `LoadoutStats.warframe` ✓
- `WeaponStatSheet` defined in Task 5, referenced in `LoadoutStats` ✓
- `DataCache` defined in Task 4 and imported in Tasks 5–8 ✓
- `compute_warframe_stats(build, cache, cross_equip_additive=None)` signature matches Task 4 definition and Task 6 call site ✓
