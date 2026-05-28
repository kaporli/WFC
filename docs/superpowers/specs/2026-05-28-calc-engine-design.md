# Warframe Planner — Pipeline Fix + Calc Engine Design

## Goal

Fix the data pipeline's accuracy issues (mod level values, ability scaling flags, full Lua parsing) and implement the Python calc engine that computes a complete stat sheet from a build definition (warframe + mods at any rank + arcanes + archon shards).

## Architecture

Two independent pieces shipped together: pipeline fixes that improve data quality, and a new Python calc engine in `engine/` that reads the improved data.

**Tech stack:** TypeScript pipeline (luaparse for Lua → JS, existing fetchers), Python 3.12 calc engine (pure functions + dataclasses, no new dependencies), pytest for tests.

---

## Part 1 — Pipeline fixes

### 1.1 Full Lua evaluation (`pipeline/src/lua/eval.ts`)

New file that converts a `luaparse` AST into a plain JS object. `luaparse` parses 911KB in 12ms (benchmarked), making it suitable for all wiki modules.

Handles the subset of Lua used in wiki data modules:
- `TableConstructor` → object (keyed fields) or array (sequential fields)
- `StringLiteral`, `NumericLiteral`, `BooleanLiteral`, `NilLiteral` → JS primitives
- `UnaryExpression` with `-` operator → negative numbers

The wiki fetcher (`fetchers/wiki-lua.ts`) stops storing raw Lua text and instead stores evaluated JS objects. Cache file `wiki-lua-raw.json` changes shape from `{ sources: Record<ModuleName, string> }` to `{ modules: Record<ModuleName, unknown>, revIds: Record<ModuleName, number> }`.

### 1.2 Additional wiki module: `Module:Ability/data/stats`

Added to the fetch list alongside the existing three modules. Contains 220 ability entries keyed by `uniqueName`, each with stat blocks carrying a `Modifier` field (`AVATAR_ABILITY_STRENGTH` | `AVATAR_ABILITY_DURATION` | `AVATAR_ABILITY_RANGE` | `AVATAR_ABILITY_EFFICIENCY`).

### 1.3 `levelValues` replaces `valuePerRank` in mod/arcane schema

**Old schema:**
```typescript
interface ModEffect {
  stat: string;
  stackType: StackType;
  valuePerRank: number;   // linear approximation, inexact at non-max ranks
}
```

**New schema:**
```typescript
interface ModEffect {
  stat: string;
  stackType: StackType;
  levelValues: number[];  // index = rank, exact value from levelStats[i]
}
```

`levelValues[0]` = stat at rank 0 (unranked), `levelValues[maxRank]` = stat at max rank.
Example for Vitality: `[0.09, 0.18, 0.27, 0.36, 0.45, 0.55, 0.64, 0.73, 0.82, 0.91, 1.00]`

Same change applies to `ArcaneEffect`.

### 1.4 Ability scaling flags normalizer (`pipeline/src/normalizers/abilities.ts`)

Reads the evaluated `Module:Ability/data/stats` object. For each ability entry, scans its stat blocks for `Modifier` values and produces a map:

```typescript
type AbilityScalingMap = Map<string, {  // keyed by ability uniqueName
  strengthScaling: boolean;
  durationScaling: boolean;
  rangeScaling: boolean;
  efficiencyScaling: boolean;
}>;
```

The warframes normalizer imports this map and uses `uniqueName` to set the four flags on each `AbilityRef`. Abilities not found in the stats module default to all-false.

### 1.5 `Module:Warframes/data` enrichment

The warframes normalizer cross-references the parsed wiki `Warframes` table to fill fields WFCD may leave empty: `exilusPolarity`, `initiallEnergy` (energy on spawn), and corrects `sprintSpeed` where WFCD has null.

### Updated `data/` output

`data/warframes.json` — ability entries now have correct scaling flags.
`data/mods.json` — effects use `levelValues: number[]`.
`data/arcanes.json` — effects use `levelValues: number[]`.

---

## Part 2 — Calc engine

### 2.1 File structure

```
engine/warframe_engine/
  loader.py          (existing — updated to load levelValues)
  build.py           — Build, EquippedMod, EquippedArcane, ArchonShard + from_dict/to_dict
  shards.py          — SHARD_TABLE: all 5 colors, all stat options, tauforged multiplier
  calculator.py      — DataCache, compute_stats() → StatSheet
  upgrade_cost.py    — ENDO_TABLE, CREDIT_TABLE, compute_upgrade_cost()
engine/tests/
  test_loader.py     (existing)
  test_build.py
  test_calculator.py
  test_upgrade_cost.py
```

### 2.2 Build model (`build.py`)

```python
@dataclass
class EquippedMod:
    unique_name: str
    rank: int          # 0 = unranked, mod.max_rank = fully ranked

@dataclass
class EquippedArcane:
    unique_name: str
    rank: int

@dataclass
class ArchonShard:
    color: str         # 'crimson' | 'azure' | 'amber' | 'topaz' | 'violet'
    stat: str          # e.g. 'abilityStrength', 'health', 'armor'
    tauforged: bool

@dataclass
class Build:
    warframe_name: str
    mods: list[EquippedMod]        # regular mod slots (max 8)
    arcanes: list[EquippedArcane]  # max 2
    shards: list[ArchonShard]      # max 5
    exilus: EquippedMod | None     # exilus slot
    aura: EquippedMod | None       # aura slot
```

`from_dict` / `to_dict` enable JSON serialization for saving/loading builds.

### 2.3 Archon shard table (`shards.py`)

```python
@dataclass
class ShardBonus:
    value: float    # base (non-tauforged) value; tauforged = value × 1.5
    is_flat: bool   # True → adds to base stat before mod scaling
                    # False → adds to additive mod pool

SHARD_TABLE: dict[str, dict[str, ShardBonus]] = {
    'crimson': {
        'abilityStrength': ShardBonus(0.25,   False),
        'health':          ShardBonus(150.0,  True),
        'abilityDuration': ShardBonus(0.10,   False),
        'castSpeed':       ShardBonus(0.10,   False),
    },
    'azure': {
        'shield':  ShardBonus(150.0, True),
        'energy':  ShardBonus(50.0,  True),
        'sprint':  ShardBonus(0.05,  False),
    },
    'amber': {
        'armor':           ShardBonus(75.0,  True),
        'energyOrb':       ShardBonus(0.25,  False),
        'abilityStrength': ShardBonus(0.25,  False),
    },
    'topaz': {
        'status':   ShardBonus(0.15, False),
        'fireRate': ShardBonus(0.10, False),
    },
    'violet': {
        'parkourVelocity': ShardBonus(0.25, False),
        'abilityRange':    ShardBonus(0.20, False),
    },
}
```

Tauforged multiplier of 1.5× applied at call time: `value * (1.5 if shard.tauforged else 1.0)`.

### 2.4 Calculator (`calculator.py`)

**`DataCache`** — loads all four `data/*.json` files once at construction, builds lookup dicts:
- `warframe_by_name: dict[str, WarframeEntry]`
- `mod_by_unique_name: dict[str, ModEntry]`
- `arcane_by_unique_name: dict[str, ArcaneEntry]`

**`StatSheet`:**
```python
@dataclass
class StatSheet:
    ability_strength: float    # 1.0 = 100% (no bonuses)
    ability_duration: float
    ability_range: float
    ability_efficiency: float  # hard-capped at 1.75

    health: float
    shield: float
    armor: float
    energy: float
    sprint: float

    armor_dr: float            # armor / (armor + 300)
    ehp: float                 # health / (1 - armor_dr) + shield

    can_shieldgate: bool       # True if shield > 0
    gate_full_s: float         # 1.3  — full gate (shields fully depleted)
    gate_short_s: float        # 0.13 — short gate (partially depleted)
```

**`compute_stats(build, cache) → StatSheet`:**

```
1. Collect additive modifiers (dict[stat, float]) from:
     - All mods (regular + exilus + aura): level_values[rank]
     - All arcanes: level_values[rank]
     - Non-flat shard bonuses

2. Collect flat bonuses (dict[stat, float]) from:
     - Flat shard bonuses (health, shield, armor, energy)

3. Compute final stats:
     health = (base.health + flat['health']) × (1 + additive['health'])
     shield = (base.shield + flat['shield']) × (1 + additive['shield'])
     armor  = (base.armor  + flat['armor'])  × (1 + additive['armor'])
     energy = (base.energy + flat['energy']) × (1 + additive['energy'])
     sprint = base.sprint × (1 + additive['sprint'])

4. Ability multipliers:
     ability_strength   = 1.0 + additive['abilityStrength']
     ability_duration   = 1.0 + additive['abilityDuration']
     ability_range      = 1.0 + additive['abilityRange']
     ability_efficiency = min(1.75, 1.0 + additive['abilityEfficiency'])

5. EHP:
     armor_dr = armor / (armor + 300)
     ehp      = health / (1 - armor_dr) + shield

6. Shieldgate:
     can_shieldgate = shield > 0
     gate_full_s    = 1.3
     gate_short_s   = 0.13
```

### 2.5 Upgrade cost (`upgrade_cost.py`)

DE's endo and credit costs per rank are fixed values (not formulaic). Two lookup tables — `ENDO_PER_RANK: list[int]` (index = rank being applied, e.g. index 0 = cost to go from rank 0 to rank 1) and `CREDIT_PER_RANK: list[int]` — sourced from the wiki's Mod Fusion page.

```python
@dataclass
class UpgradeCost:
    endo: int
    credits: int

def compute_upgrade_cost(mod: ModEntry, from_rank: int, to_rank: int) -> UpgradeCost:
    """Sum per-rank costs from from_rank to to_rank (exclusive of from_rank)."""
```

Rarity affects credit costs (Common < Uncommon < Rare < Legendary/Primed). Two tables per rarity.

### 2.6 Tests

**`test_build.py`:** Build round-trips through `to_dict` / `from_dict` without data loss.

**`test_calculator.py`** — verified against wiki values:
- Frost + Vitality R10 + Steel Fiber R10: health = 270 × 2.0 = 540, armor = 315 × 2.0 = 630, armor_dr ≈ 67.7%, EHP ≈ 1672 + 455
- Rhino + Intensify R5 + Transient Fortitude R5: ability_strength = 1.0 + 0.30 + 0.55 = 1.85
- Frost + 1 crimson shard (abilityStrength, tauforged): ability_strength = 1.0 + 0.375 = 1.375
- Frost + Vitality R3 (not max rank): health = 270 × (1 + 0.27) = 342.9

**`test_upgrade_cost.py`:**
- Common mod R3 → R5: correct endo + credits sum
- Rare mod R0 → R5: correct totals for higher credit cost tier

---

## Spec Self-Review

**Placeholder scan:** No TBDs. Shard table values need validation against current wiki — marked as "to verify" in implementation comments, not in spec. Endo/credit tables are sourced at implementation time from wiki Mod Fusion page.

**Internal consistency:** `levelValues` schema change is consistent throughout — schema/index.ts, normalizers, loader.py, calculator.py all use the same field name. `from_dict` in build.py must match the field names defined in section 2.2.

**Scope:** Two cohesive pieces (pipeline fix + calc engine) that must ship together since the calc engine depends on `levelValues` which requires the pipeline fix. Appropriate for one plan.

**Ambiguity:** Armor formula for shards — flat shard armor adds to base before Steel Fiber scaling. This matches Warframe's in-game behavior and is explicitly stated in section 2.4 step 3. Ability efficiency cap of 1.75 (75% cost reduction) is a hard game cap, encoded in `compute_stats`.
