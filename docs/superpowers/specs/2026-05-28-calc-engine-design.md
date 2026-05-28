# Warframe Planner — Full Loadout Calc Engine Design

## Goal

Complete data pipeline with accurate per-rank mod values, ability scaling, and full wiki data; a Python calc engine that models an entire loadout (warframe + all weapons + companion), computes per-slot stat sheets, routes cross-equipment mod effects, and runs mechanic checks (shieldgate feasibility, armor strip thresholds, etc.).

## Architecture

Three tiers:
1. **Data pipeline** (TypeScript) — fetches, parses, normalises all sources → `data/*.json`
2. **Calc engine** (Python) — pure functions over data; per-slot stat sheets + loadout aggregation
3. **Interactions** (YAML in `engine/interactions/`) — mechanic formulas and cross-equipment routing rules for effects not expressible from stat names alone

**Tech stack:** TypeScript 5, luaparse (Lua AST, 12ms for 911KB), warframe-items npm, Python 3.12, pytest. No new Python dependencies.

---

## Part 1 — Pipeline

### 1.1 Lua AST evaluator (`pipeline/src/lua/eval.ts`)

Converts a `luaparse` AST into a plain JS value. Handles the subset used by wiki data modules:

| AST node | JS output |
|---|---|
| `TableConstructor` with all string/identifier keys | `object` |
| `TableConstructor` with all numeric keys | `array` |
| `TableConstructor` mixed | `object` (numeric keys become string keys) |
| `StringLiteral`, `NumericLiteral`, `BooleanLiteral` | primitive |
| `NilLiteral` | `null` |
| `UnaryExpression` with `-` | negative number |

All four wiki modules are now parsed to JS objects. Cache file shape changes:
```
wiki-lua-raw.json: { sources: Record<ModuleName, string> }   ← old
wiki-lua-raw.json: { modules: Record<ModuleName, unknown>, revIds: Record<ModuleName, number> }   ← new
```

### 1.2 Wiki modules fetched

| Module | Size | Purpose |
|---|---|---|
| `Module:Mods/data` | 911KB | Mod metadata cross-reference |
| `Module:Warframes/data` | ~150KB | Aura slots, initial energy, exilus polarity |
| `Module:Ability/data` | ~186KB | Subsumable flags, augment lists per ability |
| `Module:Ability/data/stats` | ~179KB | Per-ability energy costs + scaled stat values |

### 1.3 `levelValues` replaces `valuePerRank`

**Old:** `{ stat, stackType, valuePerRank: number }` — linear approximation, wrong at non-max ranks.

**New:** `{ stat, stackType, levelValues: number[] }` — `levelValues[i]` is the exact parsed value from `levelStats[i]`. `levelValues[0]` = unranked, `levelValues[maxRank]` = fully ranked. Example for Vitality (rank 0–10): `[0.09, 0.18, 0.27, 0.36, 0.45, 0.55, 0.64, 0.73, 0.82, 0.91, 1.00]`.

Same change to `ArcaneEffect`.

Calc engine uses `effect.level_values[equipped_rank]` for exact values at any rank.

### 1.4 `ModEffect` gains `target` field

Cross-equipment mod effects (e.g. Amalgam Furax Body Count giving +45% Secondary Fire Rate while installed on a Melee weapon) need routing. The `target` field on each parsed effect indicates which loadout slot the stat applies to:

```typescript
type EffectTarget = 'self' | 'warframe' | 'primary' | 'secondary' | 'melee' | 'archgun' | 'companion';

interface ModEffect {
  stat: string;
  stackType: StackType;
  levelValues: number[];
  target: EffectTarget;   // 'self' = same slot as the mod; others = cross-equipment
}
```

Target is resolved in `normalizers/mods.ts` by:
1. Checking `pipeline/src/data/stat-targets.json` — a static mapping of description fragments to targets (e.g. `"Fire Rate for Secondary Weapons" → secondary`, `"Sprint Speed" → warframe`, `"Reload Speed on Shotguns" → primary`). ~30 entries, changes only when DE adds new Amalgam/cross-equipment mods.
2. Fallback: `target = 'self'`.

### 1.5 Ability scaling flags (`normalizers/abilities.ts`)

Reads parsed `Module:Ability/data/stats`. For each uniqueName entry, scans stat blocks for `Modifier` values:

```
AVATAR_ABILITY_STRENGTH  → strengthScaling = true
AVATAR_ABILITY_DURATION  → durationScaling = true
AVATAR_ABILITY_RANGE     → rangeScaling    = true
AVATAR_ABILITY_EFFICIENCY → efficiencyScaling = true
```

Produces `AbilityScalingMap: Map<uniqueName, { strengthScaling, durationScaling, rangeScaling, efficiencyScaling }>`. Warframes normalizer merges these flags into each `AbilityRef`.

### 1.6 `Module:Warframes/data` enrichment

Cross-referenced to fill: `initialEnergy`, `exilusPolarity` (if present), corrected `sprintSpeed`.

`AuraPolarity` is either a string → `auraSlots = 1`, or a Lua table (e.g. `{ "Aura", "Vazarin" }` for Jade) → `auraSlots = table.length`. The `WarframeEntry` schema gains `auraSlots: number`.

### 1.7 `Module:Ability/data` — Helminth + augment map

Each ability entry carries `Augments = { "Augment Name", ... }` and optionally `Subsumable = true`.

New output file `data/abilities.json`:
```typescript
interface AbilitiesData {
  subsumable: string[];                      // uniqueNames of subsumable abilities
  augmentToAbility: Record<string, string>;  // augment display name → ability uniqueName
}
```

### 1.8 Arcane helmets (`normalizers/helmets.ts`)

`ExportCustoms_en.json` added to the Public Export fetch list.

Arcane helmets identified by: `uniqueName.includes('AltHelmet')` AND `name.startsWith('Arcane')`. 27 entries currently.

`warframeName` parsed from description: `"This helmet is worn by X"` → X.

Stat effects: descriptions contain natural language only (no numbers). Values are sourced from `pipeline/src/data/arcane-helmet-stats.json` — a static committed file with the 27 entries. These helmets have not changed since 2013; the file is updated if DE ever adds more. Format mirrors `ModEffect` with `levelValues` of length 1.

Output: `data/helmets.json`.

### 1.9 Mod set bonuses (`normalizers/mod-sets.ts`)

WFCD's `Mod Set Mod` items carry a `stats: string[]` array — one string per cumulative piece count. Example for Augur: `["40% Energy spent...converted to Shields.", "80%...", ...]`.

Parser extracts the numeric value per piece count with a regex, producing:

```typescript
interface SetBonusEntry {
  uniqueName: string;
  numPiecesInSet: number;
  bonusByPieceCount: Array<{
    pieces: number;
    stat: string;          // normalised stat name, e.g. 'energyToShieldOnCast'
    value: number;
    isFlat: boolean;
  }>;
}
```

Output: `data/mod-sets.json`.

### 1.10 Ability stats (`normalizers/ability-stats.ts`)

Reads parsed `Module:Ability/data/stats`. For each ability, extracts all stat blocks:

```typescript
interface AbilityStatBlock {
  label: string;           // e.g. "Armor Reduction"
  modifier: string;        // e.g. "AVATAR_ABILITY_STRENGTH"
  baseValue: number;       // Val1 from Values table (already divided by 100 if %)
  isPercent: boolean;      // true if label contains '%'
}

interface AbilityStatsEntry {
  uniqueName: string;
  stats: AbilityStatBlock[];
}
```

Output: `data/ability-stats.json`.

### 1.11 Weapon schema expansion

`data/weapons.json` entries gain:
- `comboDuration: number` (melee only) — from WFCD
- `heavyAttackDamage: number` (melee only)
- `range: number` (melee only)
- `attacks: Attack[]` — full WFCD attack data (for heavy attack, slam, etc.)
- `slot: number` — 0=primary, 1=secondary, 2=melee, 5=archgun

### 1.12 Augment mod fields

`data/mods.json` entries gain `isAugment: boolean` and `compatName: string | null` — already in WFCD, just forwarded.

### 1.13 Additional wiki page scraping

Two wiki article pages (not Lua modules) are fetched via `action=parse` and parsed from wikitext:

**Arcane Helmet page** (`https://wiki.warframe.com/w/Arcane_Helmet`): table rows contain `+X%` / `−X%` values for each of the 27 helmets. Regex extracts stat name, sign, and value. Output feeds `data/helmets.json`.

**Archon Shard page** (`https://wiki.warframe.com/w/Archon_Shard`): section tags like `<section begin="crimson_archon_shard_buffs" />` delimit each color. Static (non-conditional) entries — those whose buffs are always-active flat or % bonuses — are parsed and stored in `data/shard-bonuses.json`. Conditional entries (Topaz kill-based health stacking, Violet ability damage on Electricity status, Emerald Toxin bonuses) are recorded but flagged `conditional: true` — they feed the interactions layer, not the stat sheet directly.

**Correct shard values** (from wiki, replacing earlier incorrect estimates):

| Color | Stat | Normal | Tauforged | Flat? |
|---|---|---|---|---|
| Crimson | Ability Strength | +10% | +15% | No |
| Crimson | Ability Duration | +10% | +15% | No |
| Crimson | Melee Crit Damage | +25% | +37.5% | No |
| Crimson | Primary Status Chance | +25% | +37.5% | No |
| Crimson | Secondary Crit Chance | +25% | +37.5% | No |
| Azure | Health | +150 | +225 | Yes |
| Azure | Shield Capacity | +150 | +225 | Yes |
| Azure | Energy Max | +50 | +75 | Yes |
| Azure | Armor | +150 | +225 | Yes |
| Amber | Armor (%) | +30% | +45% | No |
| Amber | Health Orb Effectiveness | +100% | +150% | No |
| Amber | Energy Orb Effectiveness | +50% | +75% | No |
| Amber | Casting Speed | +25% | +37.5% | No |
| Amber | Parkour Velocity | +15% | +22.5% | No |

### 1.14 Upgrade cost formulae

**Endo** — fully formulaic, sourced from the wiki's Fusion page. No static table needed:
```
endo_per_rank_up(from_rank) = E_BC × 2^from_rank
endo_total(from_rank, to_rank) = E_BC × (2^to_rank - 2^from_rank)

E_BC by rarity:
  Common                       = 10
  Uncommon / Peculiar          = 20
  Rare / Amalgam / Riven / Galvanized = 30
  Legendary                    = 40
  Antique Common/Uncommon/Rare = 160 / 320 / 480
```
`rarity` comes from WFCD (`mod.rarity`). `max_rank` from `mod.fusionLimit`.

**Credits** — formula not documented in wiki (section is marked `{{UpdateMe}}`). One static file: `pipeline/src/data/upgrade-credits.json`, keyed by rarity, mapping rank → credit cost. ~40 numbers total. Updated via in-game testing when DE changes costs (rare).

### 1.15 Static data file (one remaining)

| File | Purpose | Change frequency |
|---|---|---|
| `pipeline/src/data/upgrade-credits.json` | Credit cost per rank up, by rarity | Rare |
| `pipeline/src/data/stat-targets.json` | Cross-equipment routing (~30 entries) | Rare (new Amalgam mod) |

### Updated `data/` output

```
data/
  warframes.json       — auraSlots, correct ability flags, initialEnergy, exilusPolarity
  mods.json            — levelValues, isAugment, compatName, effect.target
  arcanes.json         — levelValues
  weapons.json         — comboDuration, heavyAttackDamage, range, slot
  helmets.json         — 27 arcane helmets with stat effects
  abilities.json       — subsumable list, augment→ability map
  ability-stats.json   — per-ability energy cost + scaled stat values
  mod-sets.json        — set bonus values by piece count
```

---

## Part 2 — Loadout model

### 2.1 File structure

```
engine/warframe_engine/
  loader.py              (updated — all new data files)
  build.py               (updated — helminth, helmet, auras list, validate())
  loadout.py             (new — Loadout, WeaponSlot)
  shards.py              (new — SHARD_TABLE)
  calculator.py          (updated — compute_warframe_stats() → StatSheet)
  weapon_calculator.py   (new — compute_weapon_stats() → WeaponStatSheet)
  loadout_calculator.py  (new — compute_loadout() → LoadoutStats, cross-equipment routing)
  checks.py              (new — MechanicCheck, run_checks())
  upgrade_cost.py        (new — compute_upgrade_cost())
engine/interactions/
  mechanics/
    shieldgate.yaml
    armor-strip.yaml
engine/tests/
  test_loader.py         (existing)
  test_build.py
  test_weapon_calculator.py
  test_loadout_calculator.py
  test_checks.py
  test_upgrade_cost.py
```

### 2.2 Build model (`build.py`)

```python
@dataclass
class EquippedMod:
    unique_name: str
    rank: int             # 0 = unranked

@dataclass
class EquippedArcane:
    unique_name: str
    rank: int

@dataclass
class ArchonShard:
    color: str            # 'crimson' | 'azure' | 'amber' | 'topaz' | 'violet'
    stat: str             # e.g. 'abilityStrength', 'health'
    tauforged: bool

@dataclass
class Build:
    warframe_name: str
    mods: list[EquippedMod]         # regular slots (max 8)
    arcanes: list[EquippedArcane]   # max 2; max 1 if arcane helmet equipped
    shards: list[ArchonShard]       # max 5
    exilus: EquippedMod | None
    auras: list[EquippedMod]        # len = warframe.aura_slots (1 for most, 2 for Jade)
    helmet: str | None              # uniqueName; arcane helmet reduces arcane slots to 1
    helminth_ability: str | None    # uniqueName of subsumed ability (slot 3 replacement)
```

**`validate(build, cache) → list[str]`** — returns error strings:
- Augment mod valid if: `mod.compat_name == build.warframe_name` OR mod's display name is in `cache.augment_name_to_ability[mod_name]`'s ability and that ability's `uniqueName == build.helminth_ability`.
- `len(build.auras) <= warframe.aura_slots`
- Arcane helmet → max 1 arcane
- Each rank in `[0, entry.max_rank]`

### 2.3 Loadout model (`loadout.py`)

```python
@dataclass
class WeaponSlot:
    weapon_unique_name: str
    mods: list[EquippedMod]    # max 8
    exilus: EquippedMod | None
    riven: EquippedMod | None  # riven occupies one regular slot

@dataclass
class Loadout:
    warframe: Build
    primary: WeaponSlot | None
    secondary: WeaponSlot | None
    melee: WeaponSlot | None
    archgun: WeaponSlot | None
    archgun_gravimag: bool         # True = Gravimag installed; archgun usable in ground mission
    companion_mods: list[EquippedMod]
    companion_weapon: WeaponSlot | None
```

---

## Part 3 — Stat calculators

### 3.1 Warframe stat sheet (`calculator.py`)

**`DataCache`** loads all eight `data/*.json` files. Lookup structures:
- `warframe_by_name`, `mod_by_unique_name`, `arcane_by_unique_name`
- `helmet_by_unique_name`, `arcane_helmet_unique_names: set[str]`
- `augment_name_to_ability: dict[str, str]`
- `mod_set_by_unique_name: dict[str, SetBonusEntry]`
- `ability_stats_by_unique_name: dict[str, AbilityStatsEntry]`

**`StatSheet`:**
```python
@dataclass
class StatSheet:
    ability_strength: float    # 1.0 = 100%
    ability_duration: float
    ability_range: float
    ability_efficiency: float  # hard cap 1.75

    health: float
    shield: float
    armor: float
    energy: float
    sprint: float

    armor_dr: float            # armor / (armor + 300)
    ehp: float                 # health / (1 - armor_dr) + shield

    can_shieldgate: bool
    gate_full_s: float         # 1.3
    gate_short_s: float        # 0.13
```

**`compute_warframe_stats(build, cache, cross_equip_additive=None) → StatSheet`:**

```
1. Additive pool from: all mods (regular + exilus + auras) level_values[rank]
                       all arcanes level_values[rank]
                       arcane helmet effects (level_values[0]) if equipped
                       non-flat shard bonuses
   Flat pool from:     flat shard bonuses (health, shield, armor, energy)
   Cross-equip from:   additive bonuses with target='warframe' from weapon mods (passed in)

2. Final stats:
   health = (base.health + flat['health']) × (1 + additive['health'])
   shield = (base.shield + flat['shield']) × (1 + additive['shield'])
   armor  = (base.armor  + flat['armor'])  × (1 + additive['armor'])
   energy = (base.energy + flat['energy']) × (1 + additive['energy'])
   sprint = base.sprint × (1 + additive['sprint'])

3. Ability multipliers:
   ability_strength   = 1.0 + additive['abilityStrength']
   ability_duration   = 1.0 + additive['abilityDuration']
   ability_range      = 1.0 + additive['abilityRange']
   ability_efficiency = min(1.75, 1.0 + additive['abilityEfficiency'])

4. EHP: armor_dr = armor / (armor + 300); ehp = health / (1 - armor_dr) + shield
5. Shieldgate: can_shieldgate = shield > 0; gate_full_s = 1.3; gate_short_s = 0.13
```

### 3.2 Weapon stat sheet (`weapon_calculator.py`)

**`WeaponStatSheet`:**
```python
@dataclass
class WeaponStatSheet:
    total_damage: float
    damage_types: dict[str, float]   # e.g. {'Impact': 120.0, 'Slash': 80.0}
    crit_chance: float
    crit_multiplier: float
    status_chance: float
    fire_rate: float
    magazine_size: int
    reload_time: float
    multishot: float
    # Melee only
    combo_duration: float
    heavy_attack_damage: float
    range_: float
```

**`compute_weapon_stats(slot, weapon_entry, cache) → tuple[WeaponStatSheet, dict[str, dict[str, float]]]`:**

Returns the weapon's stat sheet AND a `cross_equip` dict keyed by target slot (`'warframe'`, `'secondary'`, etc.) containing additive bonuses to pass to other calculators.

Mod effect routing:
- `effect.target == 'self'` → add to this weapon's additive pool
- `effect.target != 'self'` → add to `cross_equip[effect.target][effect.stat]`

Weapon final stats formula:
```
total_damage  = base_total × (1 + additive['damage'])
crit_chance   = base_crit + additive['critChance']   (additive, not multiplicative)
crit_mult     = base_mult × (1 + additive['critMult'])
status_chance = base_status + additive['statusChance']
fire_rate     = base_fire_rate × (1 + additive['fireRate'])
combo_duration = base_combo_duration + flat_additive['comboDuration']  (flat, not %)
```

### 3.3 Loadout aggregation (`loadout_calculator.py`)

**`LoadoutStats`:**
```python
@dataclass
class LoadoutStats:
    warframe: StatSheet
    primary: WeaponStatSheet | None
    secondary: WeaponStatSheet | None
    melee: WeaponStatSheet | None
    archgun: WeaponStatSheet | None
    companion_weapon: WeaponStatSheet | None
```

**`compute_loadout(loadout, cache) → LoadoutStats`:**

```
1. Compute each weapon slot independently, collecting cross_equip dicts.
2. Merge all cross_equip['warframe'] additive pools into one dict.
3. Compute warframe stats, passing merged cross_equip warframe bonuses.
4. Return LoadoutStats.
```

Order: weapons first → collect cross-equip → warframe last (so all cross-equip contributions are known).

**Set bonus resolution:**

For each mod set (keyed by `mod.modSet`), count how many pieces are equipped across the ENTIRE loadout (including warframe + all weapon slots). Look up `mod-sets.json` for the appropriate tier bonus and add it to the relevant slot's additive pool.

Example: 2 Augur pieces (e.g. Augur Accord on warframe + Augur Pact on secondary) → 80% energy-to-shield bonus, attributed to warframe.

---

## Part 4 — Mechanic checks (`checks.py`)

### 4.1 MechanicResult

```python
@dataclass
class MechanicCheck:
    id: str                  # e.g. 'shieldgate_ability_snowglobe_augur'
    name: str
    category: str            # 'shieldgate' | 'armor_strip' | 'ability_threshold'
    value: float             # computed value
    threshold: float         # target for check to pass
    passes: bool
    details: dict            # extra data: required_strength, ability_name, pieces_needed, etc.
```

### 4.2 `run_checks(loadout, loadout_stats, cache) → list[MechanicCheck]`

Runs all applicable checks and returns results. Checks are generated dynamically from data — not hardcoded per warframe.

### 4.3 Shieldgate checks

**Sources:**
- Brief Respite (aura): `levelStats` parsed to `energyToShieldOnCast = 1.5` (150% at max rank, if equipped)
- Augur set: from `mod-sets.json` by piece count across loadout
- Catalyzing Shields: special case — forces `shield = 1`, makes full gate (1.3s) always trigger

**Formula:**
```
actual_energy_cost = base_cost × (2 - ability_efficiency)  # efficiency capped at 1.75 → min cost = 25%
shields_restored   = actual_energy_cost × (brief_respite_pct + augur_set_pct)
```

**Check per ability:** for each of the warframe's 4 abilities (including helminth replacement):
```
passes = shields_restored >= warframe_stats.shield
```

`base_cost` comes from `ability-stats.json`: the stat block where `modifier == "AVATAR_ABILITY_EFFICIENCY"`.

### 4.4 Armor strip checks

For each ability with a stat block labelled `"Armor Reduction"` in `ability-stats.json`:

```
final_strip = base_armor_reduction × warframe_stats.ability_strength
passes      = final_strip >= 1.0
required_strength = 1.0 / base_armor_reduction
```

`details` includes `required_strength` so the UI can show "you need 250% strength for full strip."

### 4.5 Interaction YAML format

For mechanics not expressible from stat data alone, YAML files in `engine/interactions/mechanics/` define the formula:

```yaml
# engine/interactions/mechanics/shieldgate.yaml
id: shieldgate
description: Shield gate mechanic parameters
params:
  full_gate_duration_s: 1.3
  short_gate_duration_s: 0.13
  brief_respite_stat: energyToShieldOnCast
  augur_set_stat: energyToShieldOnCast
  efficiency_formula: "base_cost * (2 - efficiency)"  # human-readable only
  catalyzing_shields_override: true  # sets shield to 1, always full gate
```

The Python checks module reads these files but implements the actual computation in code — the YAML is documentation + parameter source, not an interpreter target.

---

## Part 5 — Upgrade cost (`upgrade_cost.py`)

Endo and credit costs per rank are fixed per-rarity lookup tables from `pipeline/src/data/upgrade-costs.json`:

```python
@dataclass
class UpgradeCost:
    endo: int
    credits: int

def compute_upgrade_cost(mod: ModEntry, from_rank: int, to_rank: int) -> UpgradeCost:
    """Sum costs for ranks [from_rank+1 .. to_rank] inclusive."""
```

---

## Part 6 — Archon shard table (`shards.py`)

Values sourced from `data/shard-bonuses.json` — generated by the pipeline scraping the Archon Shard wiki page. Python `DataCache` loads it at runtime. Conditional shards (flagged `conditional: true` in the JSON) are excluded from the static stat sheet and handled by the checks layer.

```python
@dataclass
class ShardBonus:
    stat: str
    value: float     # base (normal); tauforged = × 1.5
    is_flat: bool    # True → adds to base stat before mod scaling
    conditional: bool  # True → not applied to static stat sheet

# Loaded from data/shard-bonuses.json at runtime — not hardcoded
SHARD_BONUSES: dict[str, list[ShardBonus]]  # keyed by color
```

---

## Part 7 — Tests

**`test_build.py`:**
- Round-trip `to_dict` / `from_dict`
- `validate()`: augment on wrong warframe rejected; same augment accepted with Helminth; too many auras; arcane helmet + 2 arcanes; out-of-range rank

**`test_weapon_calculator.py`:**
- Soma Prime + Serration R10 + Split Chamber R5 → correct damage, multishot
- Amalgam Furax Body Count on melee → `cross_equip['secondary']['fireRate'] = 0.45`
- Amalgam Ripkas True Steel on melee → `cross_equip['primary']['reloadSpeed'] = 0.20`

**`test_loadout_calculator.py`:**
- Full loadout: Frost warframe + any primary + secondary with 2× Augur mods → set bonus included in warframe check
- Frost + Steel Fiber R10 + Vitality R10 → health=540, armor=630, EHP≈2127
- Rhino + Intensify R5 + Transient Fortitude R5 → ability_strength=1.85
- Jade + 2 auras → passes validation; strength from both auras stacks
- Frost + Vitality R3 (not max) → health = 270 × (1 + 0.27) = 342.9

**`test_checks.py`:**
- Frost + 2× Augur pieces + low efficiency: shieldgate check passes/fails at correct shield value
- Frost + high strength build: Avalanche armor strip check passes at ≥250% strength
- Nekros + enough strength: Terrify armor strip check (base 50%) passes at ≥200% strength

**`test_upgrade_cost.py`:**
- Common R3→R5, Rare R0→R5: correct totals

---

## Self-Review

**Placeholder scan:** One static JSON file (`upgrade-credits.json`, ~40 numbers for credit costs per rank/rarity) is populated at implementation time from in-game testing — not automated because the wiki's credit cost formula is marked `{{UpdateMe}}`. All other data — including arcane helmet stats, archon shard values, and endo upgrade costs — is fully automated from WFCD, Public Export, or wiki APIs (`action=parse` on article pages for helmets and shards; formula from Fusion wiki page for endo).

**Internal consistency:** `effect.target` added at normalizer level is used by both `compute_weapon_stats` (cross-equip routing) and the shieldgate check (Augur set counted across entire loadout). `data/mod-sets.json` feeds both the loadout aggregator (set bonus) and the shieldgate check. Consistent use throughout.

**Scope check:** This is large but cohesive — all pieces feed into `compute_loadout() → LoadoutStats → run_checks()`. Natural implementation order: pipeline fixes → warframe calc (existing base) → weapon calc → loadout aggregation → checks.

**Ambiguity resolutions:**
- Augur set pieces counted across the ENTIRE loadout, not per slot.
- Archgun with `gravimag = false` is ignored in ground-mission load calculations.
- Ability efficiency formula: `actual_cost = base_cost × (2 - efficiency)` where efficiency is already capped at 1.75.
- Armor formula: flat shard bonuses add to base before mod multiplier: `(base + flat) × (1 + pct_mods)`.
- Combo duration from Amalgam mods: stored as a flat-seconds additive to base (not a multiplier).
