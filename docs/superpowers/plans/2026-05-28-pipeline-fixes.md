# Warframe Planner — Pipeline Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the TypeScript data pipeline: add luaparse-based Lua evaluation, replace `valuePerRank` with exact `levelValues[]`, parse ability scaling flags from wiki, add cross-equipment `target` field, add arcane helmets, archon shards, mod set bonuses, ability stats, and wire all new outputs into `data/`.

**Architecture:** Each task is a self-contained change to one or two files. The pipeline is exercised end-to-end at the final task. Tasks 1–2 are independent and can be done in any order; Tasks 3–15 follow the dependency order listed.

**Tech Stack:** TypeScript 5, tsx, luaparse (already installed), warframe-items, lzma (CJS via createRequire), node:fs, node:fetch.

---

## File Map

```
pipeline/src/
  types/
    luaparse.d.ts          CREATE — TypeScript declarations for luaparse
  lua/
    eval.ts                CREATE — AST → plain JS object
  data/
    stat-targets.json      CREATE — ~30 cross-equipment stat routing entries
    upgrade-credits.json   CREATE — credit costs by rarity/rank
  fetchers/
    wiki-lua.ts            MODIFY — evaluate modules instead of storing raw text
    wiki-pages.ts          CREATE — fetch + parse Arcane Helmet and Archon Shard wiki pages
    public-export.ts       MODIFY — add ExportCustoms to fetch list
  normalizers/
    abilities.ts           CREATE — ability scaling flags + augment→ability map
    ability-stats.ts       CREATE — per-ability energy cost + stat values
    helmets.ts             CREATE — arcane helmet entries
    mod-sets.ts            CREATE — set bonus entries
    shards.ts              CREATE — archon shard entries from wiki page
    mods.ts                MODIFY — levelValues, target, isAugment, compatName
    arcanes.ts             MODIFY — levelValues
    warframes.ts           MODIFY — aura slots, ability flags, initialEnergy
    weapons.ts             MODIFY — comboDuration, heavyAttackDamage, range, slot
  schema/
    index.ts               MODIFY — levelValues replaces valuePerRank; add EffectTarget; new entry types
  index.ts                 MODIFY — import all new normalizers, write all new data/ files
data/
  abilities.json           CREATE (output)
  ability-stats.json       CREATE (output)
  helmets.json             CREATE (output)
  mod-sets.json            CREATE (output)
  shard-bonuses.json       CREATE (output)
```

---

## Task 1: luaparse TypeScript declaration + Lua AST evaluator

**Files:**
- Create: `pipeline/src/types/luaparse.d.ts`
- Create: `pipeline/src/lua/eval.ts`

- [ ] **Step 1: Create `pipeline/src/types/luaparse.d.ts`**

```typescript
declare module 'luaparse' {
  interface ParseOptions {
    luaVersion?: '5.1' | '5.2' | '5.3';
    encodingMode?: string;
  }
  interface Chunk { type: 'Chunk'; body: Statement[]; }
  type Statement = ReturnStatement | { type: string; [k: string]: unknown };
  interface ReturnStatement { type: 'ReturnStatement'; arguments: Expression[]; }
  type Expression =
    | TableConstructor | StringLiteral | NumericLiteral | BooleanLiteral
    | NilLiteral | UnaryExpression | Identifier | VarargLiteral
    | { type: string; [k: string]: unknown };
  interface TableConstructor { type: 'TableConstructor'; fields: Field[]; }
  type Field = TableKeyString | TableKey | TableValue;
  interface TableKeyString { type: 'TableKeyString'; key: Identifier; value: Expression; }
  interface TableKey     { type: 'TableKey';     key: Expression;  value: Expression; }
  interface TableValue   { type: 'TableValue';   value: Expression; }
  interface StringLiteral  { type: 'StringLiteral';  value: string;  raw: string; }
  interface NumericLiteral { type: 'NumericLiteral'; value: number;  raw: string; }
  interface BooleanLiteral { type: 'BooleanLiteral'; value: boolean; }
  interface NilLiteral     { type: 'NilLiteral';     value: null; }
  interface VarargLiteral  { type: 'VarargLiteral';  value: string; }
  interface Identifier     { type: 'Identifier';     name: string; }
  interface UnaryExpression {
    type: 'UnaryExpression';
    operator: string;
    argument: Expression;
  }
  const luaparse: { parse(code: string, opts?: ParseOptions): Chunk };
  export = luaparse;
}
```

- [ ] **Step 2: Create `pipeline/src/lua/eval.ts`**

```typescript
import luaparse from 'luaparse';

export type LuaVal = string | number | boolean | null | LuaObj | LuaVal[];
export type LuaObj = { [key: string]: LuaVal };

export function evalLua(src: string): LuaVal {
  const ast = luaparse.parse(src, { luaVersion: '5.3' });
  const ret = ast.body.find(n => n.type === 'ReturnStatement');
  if (!ret || ret.type !== 'ReturnStatement') return null;
  const r = ret as { type: 'ReturnStatement'; arguments: luaparse.Expression[] };
  return r.arguments.length ? evalExpr(r.arguments[0]) : null;
}

function evalExpr(node: luaparse.Expression): LuaVal {
  switch (node.type) {
    case 'StringLiteral':  return (node as luaparse.StringLiteral).value;
    case 'NumericLiteral': return (node as luaparse.NumericLiteral).value;
    case 'BooleanLiteral': return (node as luaparse.BooleanLiteral).value;
    case 'NilLiteral':     return null;
    case 'VarargLiteral':  return null;
    case 'Identifier':     return (node as luaparse.Identifier).name; // unresolved ref → string name
    case 'UnaryExpression': {
      const u = node as luaparse.UnaryExpression;
      if (u.operator === '-') {
        const v = evalExpr(u.argument);
        return typeof v === 'number' ? -v : null;
      }
      return null;
    }
    case 'TableConstructor': return evalTable(node as luaparse.TableConstructor);
    default: return null;
  }
}

function evalTable(node: luaparse.TableConstructor): LuaObj | LuaVal[] {
  const obj: LuaObj = {};
  let arrayIdx = 1;

  for (const field of node.fields) {
    switch (field.type) {
      case 'TableKeyString': {
        const f = field as luaparse.TableKeyString;
        obj[f.key.name] = evalExpr(f.value);
        break;
      }
      case 'TableKey': {
        const f = field as luaparse.TableKey;
        const k = evalExpr(f.key);
        obj[String(k)] = evalExpr(f.value);
        break;
      }
      case 'TableValue': {
        const f = field as luaparse.TableValue;
        obj[String(arrayIdx++)] = evalExpr(f.value);
        break;
      }
    }
  }

  // If all keys are "1", "2", ... convert to array
  const keys = Object.keys(obj);
  if (keys.length > 0 && keys.every((k, i) => k === String(i + 1))) {
    return keys.map(k => obj[k]);
  }
  return obj;
}
```

- [ ] **Step 3: Verify it compiles**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1
```
Expected: no errors.

- [ ] **Step 4: Smoke test the evaluator**

```bash
cd /Users/elias/Documents/WFC/pipeline && node --input-type=module << 'EOF'
import { evalLua } from './src/lua/eval.ts';
// Using tsx would be needed, so test via a quick script
EOF
```

Actually test by running a quick tsx script:
```bash
npx tsx -e "
import { evalLua } from './src/lua/eval.js';
const result = evalLua('return { [\"Snow Globe\"] = { Name = \"Snow Globe\", Cost = 50, Key = 3 } }');
console.log(JSON.stringify(result));
" 2>&1
```
Expected: `{"Snow Globe":{"Name":"Snow Globe","Cost":50,"Key":3}}`

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/types/ pipeline/src/lua/
git commit -m "feat(pipeline): add luaparse TypeScript declaration and Lua AST evaluator"
```

---

## Task 2: Static data files

**Files:**
- Create: `pipeline/src/data/stat-targets.json`
- Create: `pipeline/src/data/upgrade-credits.json`

- [ ] **Step 1: Create `pipeline/src/data/stat-targets.json`**

Maps description-string fragments to target loadout slots for cross-equipment mod routing:

```json
{
  "fire rate for secondary weapons": "secondary",
  "fire rate for secondaries": "secondary",
  "secondary fire rate": "secondary",
  "reload speed on shotguns": "primary",
  "reload speed on rifles": "primary",
  "reload speed on primary": "primary",
  "sprint speed": "warframe",
  "dodge speed": "warframe",
  "movement speed": "warframe",
  "holster speed": "warframe",
  "combo duration": "melee",
  "life steal on nikanas": "melee",
  "life steal on daggers": "melee",
  "life steal on swords": "melee",
  "damage from daggers": "melee",
  "gore chance": "melee"
}
```

- [ ] **Step 2: Create `pipeline/src/data/upgrade-credits.json`**

Credit cost per rank-up, per rarity tier. Sourced from in-game testing (wiki formula is marked as incomplete):

```json
{
  "Common": [1000, 1000, 2000, 3000, 4000, 6000, 8000, 10000, 15000, 20000],
  "Uncommon": [2000, 2000, 4000, 6000, 8000, 12000, 16000, 20000, 30000, 40000],
  "Rare": [4000, 4000, 8000, 12000, 16000, 24000, 32000, 40000, 60000, 80000],
  "Legendary": [8000, 8000, 16000, 24000, 32000, 48000, 64000, 80000, 120000, 160000],
  "AntiqueMods": [10000, 20000, 40000, 80000, 160000]
}
```

Note: index i = cost to go from rank i to rank i+1.

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/data/
git commit -m "feat(pipeline): add static data files for cross-equipment routing and credit costs"
```

---

## Task 3: Schema updates

**Files:**
- Modify: `pipeline/src/schema/index.ts`

Replace `valuePerRank` with `levelValues`, add `EffectTarget`, add new entry types.

- [ ] **Step 1: Rewrite `pipeline/src/schema/index.ts`**

```typescript
export interface BaseStats {
  health: number;
  shield: number;
  armor: number;
  energy: number;
  sprint: number;
}

export interface AbilityRef {
  name: string;
  slot: number;
  strengthScaling: boolean;
  durationScaling: boolean;
  rangeScaling: boolean;
  efficiencyScaling: boolean;
}

export interface WarframeEntry {
  uniqueName: string;
  name: string;
  baseStats: BaseStats;
  polarities: string[];
  aura: string | null;
  auraSlots: number;           // 1 for most, 2 for Jade
  abilities: AbilityRef[];
  passiveDescription: string;
  masteryRank: number;
  initialEnergy: number;       // energy on spawn (from wiki)
  exilusPolarity: string | null;
}

export type StackType = 'additive_base' | 'additive_stacking' | 'multiplicative';
export type EffectTarget = 'self' | 'warframe' | 'primary' | 'secondary' | 'melee' | 'archgun' | 'companion';

export interface ModEffect {
  stat: string;
  stackType: StackType;
  levelValues: number[];       // index = rank; levelValues[0] = unranked, levelValues[maxRank] = max
  target: EffectTarget;        // 'self' = same slot as the mod; others = cross-equipment
}

export interface ModEntry {
  uniqueName: string;
  name: string;
  polarity: string;
  rarity: string;
  maxRank: number;
  type: string;
  modSet: string | null;
  tradable: boolean;
  isAugment: boolean;
  compatName: string | null;
  effects: ModEffect[];
  rawDescription: string;
}

export interface ArcaneEffect {
  stat: string;
  levelValues: number[];       // one entry per rank
}

export interface ArcaneEntry {
  uniqueName: string;
  name: string;
  maxRank: number;
  maxStacks: number;
  trigger: string;
  effects: ArcaneEffect[];
  rawDescription: string;
}

export interface WeaponStats {
  totalDamage: number;
  damageTypes: Record<string, number>;
  critChance: number;
  critMultiplier: number;
  statusChance: number;
  fireRate: number;
  magazineSize: number;
  reloadTime: number;
  multishot: number;
  range?: number;
  attackSpeed?: number;
  comboDuration?: number;
  heavyAttackDamage?: number;
}

export interface WeaponEntry {
  uniqueName: string;
  name: string;
  type: string;
  slot: number;                // 0=primary, 1=secondary, 2=melee, 5=archgun
  baseStats: WeaponStats;
  disposition: number;
  masteryRank: number;
}

export interface ArcaneHelmetEffect {
  stat: string;
  value: number;               // positive = bonus, negative = penalty
  isFlat: boolean;
}

export interface ArcaneHelmetEntry {
  uniqueName: string;
  name: string;
  warframeName: string;
  effects: ArcaneHelmetEffect[];
}

export interface SetBonusEffect {
  pieces: number;
  stat: string;
  value: number;
  isFlat: boolean;
}

export interface SetBonusEntry {
  uniqueName: string;          // set mod uniqueName e.g. /Lotus/.../AugurSetMod
  numPiecesInSet: number;
  bonusByPieceCount: SetBonusEffect[];
}

export interface AbilityStatBlock {
  label: string;               // e.g. "Energy Cost", "Armor Reduction"
  modifier: string;            // e.g. "AVATAR_ABILITY_STRENGTH"
  baseValue: number;
  isPercent: boolean;
}

export interface AbilityStatsEntry {
  uniqueName: string;
  stats: AbilityStatBlock[];
}

export interface ShardBonus {
  stat: string;
  value: number;
  isFlat: boolean;
  conditional: boolean;        // true = not applied to static stat sheet
}

export interface AbilitiesData {
  subsumable: string[];
  augmentToAbility: Record<string, string>;
}

export interface Manifest {
  lastUpdated: string;
  sourceVersions: {
    wfcd: string;
    publicExport: string;
    wiki: Record<string, number>;
    wikiPages: Record<string, string>;
  };
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1
```
Expected: type errors in normalizers (they use old schema) — that's fine, we'll fix them in subsequent tasks.

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/schema/index.ts
git commit -m "feat(pipeline): update schema — levelValues, EffectTarget, new entry types"
```

---

## Task 4: Update wiki-lua fetcher to evaluate modules

**Files:**
- Modify: `pipeline/src/fetchers/wiki-lua.ts`

Add `Module:Ability/data/stats`, evaluate all modules using `evalLua`, change cache shape.

- [ ] **Step 1: Rewrite `pipeline/src/fetchers/wiki-lua.ts`**

```typescript
import { evalLua, type LuaObj } from '../lua/eval.js';

const WIKI_API = 'https://wiki.warframe.com/api.php';

export const MODULES = [
  'Module:Mods/data',
  'Module:Warframes/data',
  'Module:Ability/data',
  'Module:Ability/data/stats',
] as const;

export type ModuleName = (typeof MODULES)[number];

async function fetchModuleSource(title: string): Promise<{ content: string; revId: number }> {
  const params = new URLSearchParams({
    action: 'query', titles: title, prop: 'revisions',
    rvprop: 'content|ids', rvslots: 'main', format: 'json', formatversion: '2',
  });
  const res = await fetch(`${WIKI_API}?${params}`, {
    headers: { 'User-Agent': 'warframe-planner/0.1 (github.com/warframe-planner)' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${title}`);
  const json = await res.json() as {
    query: { pages: Array<{ missing?: boolean; revisions?: Array<{ revid: number; slots: { main: { content: string } } }> }> };
  };
  const page = json.query.pages[0];
  if (page.missing || !page.revisions?.length) throw new Error(`Wiki module not found: ${title}`);
  const rev = page.revisions[0];
  return { content: rev.slots.main.content, revId: rev.revid };
}

export interface WikiLuaRaw {
  modules: Partial<Record<ModuleName, LuaObj>>;
  revIds: Partial<Record<ModuleName, number>>;
}

export async function fetchWikiLua(): Promise<WikiLuaRaw> {
  const modules: Partial<Record<ModuleName, LuaObj>> = {};
  const revIds: Partial<Record<ModuleName, number>> = {};

  for (const mod of MODULES) {
    process.stdout.write(`  fetching ${mod}...`);
    const { content, revId } = await fetchModuleSource(mod);
    const evaluated = evalLua(content);
    modules[mod] = (evaluated as LuaObj) ?? {};
    revIds[mod] = revId;
    process.stdout.write(` done (${(content.length / 1024).toFixed(0)}KB)\n`);
  }

  return { modules, revIds };
}
```

- [ ] **Step 2: Delete old wiki cache so it gets regenerated with new shape**

```bash
rm -f /Users/elias/Documents/WFC/pipeline/cache/wiki-lua-raw.json
```

- [ ] **Step 3: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep -v "normalizers" | head -20
```
Expected: errors only in normalizers that reference old schema — that's expected at this stage.

- [ ] **Step 4: Commit**

```bash
git add pipeline/src/fetchers/wiki-lua.ts
git commit -m "feat(pipeline): wiki fetcher now evaluates Lua modules via luaparse; adds Module:Ability/data/stats"
```

---

## Task 5: Updated mods normalizer

**Files:**
- Modify: `pipeline/src/normalizers/mods.ts`

Replace `valuePerRank` with `levelValues[]`, add `target` routing, add `isAugment` and `compatName`.

- [ ] **Step 1: Rewrite `pipeline/src/normalizers/mods.ts`**

```typescript
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { WfcdMod, WfcdLevelStat } from '../schema/wfcd.js';
import type { ModEntry, ModEffect, StackType, EffectTarget } from '../schema/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const STAT_TARGETS_PATH = resolve(__dirname, '../data/stat-targets.json');

function loadStatTargets(): Record<string, EffectTarget> {
  try {
    return JSON.parse(readFileSync(STAT_TARGETS_PATH, 'utf8')) as Record<string, EffectTarget>;
  } catch {
    return {};
  }
}

const STAT_TARGETS = loadStatTargets();

const STAT_MAP: Array<[RegExp, string]> = [
  [/ability strength|power strength/i, 'abilityStrength'],
  [/ability duration|power duration/i, 'abilityDuration'],
  [/ability range|power range/i, 'abilityRange'],
  [/ability efficiency|power efficiency/i, 'abilityEfficiency'],
  [/health(?! steal)/i, 'health'],
  [/shield capacity|shield(?! gating)/i, 'shield'],
  [/armor/i, 'armor'],
  [/energy max|energy pool/i, 'energy'],
  [/sprint speed/i, 'sprint'],
];

function resolveStatName(fragment: string): string {
  const lower = fragment.toLowerCase().trim();
  for (const [re, name] of STAT_MAP) {
    if (re.test(lower)) return name;
  }
  return lower.replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
}

function resolveTarget(fragment: string): EffectTarget {
  const lower = fragment.toLowerCase().trim();
  for (const [key, target] of Object.entries(STAT_TARGETS)) {
    if (lower.includes(key)) return target as EffectTarget;
  }
  return 'self';
}

function parseEffects(levelStats: WfcdLevelStat[] | undefined): ModEffect[] {
  if (!levelStats?.length) return [];

  const effectCount = levelStats[0].stats?.length ?? 0;
  const results: ModEffect[] = [];

  for (let effIdx = 0; effIdx < effectCount; effIdx++) {
    const levelValues: number[] = [];
    let stat = '';
    let target: EffectTarget = 'self';
    let hasValue = false;

    for (let rankIdx = 0; rankIdx < levelStats.length; rankIdx++) {
      // Strip formatting tags (e.g. <DT_FREEZE_COLOR>, <LINE_SEPARATOR>)
      const raw = (levelStats[rankIdx].stats?.[effIdx] ?? '').replace(/<[^>]+>/g, '');
      const match = raw.match(/([+-]?\d+(?:\.\d+)?)\s*%/);
      if (match) {
        const val = parseFloat(match[1]) / 100;
        levelValues.push(val);
        if (rankIdx === 0 && !hasValue) {
          hasValue = true;
          const frag = raw.replace(/[+-]?\d+(?:\.\d+)?\s*%\s*/, '');
          stat = resolveStatName(frag);
          target = resolveTarget(frag);
        }
      } else {
        levelValues.push(0);
      }
    }

    if (stat && levelValues.some(v => v !== 0)) {
      results.push({ stat, stackType: 'additive_base' as StackType, levelValues, target });
    }
  }

  return results;
}

function resolveModType(m: WfcdMod): string {
  const t = (m.type ?? '').toLowerCase();
  if (t.includes('stance')) return 'stance';
  if (t.includes('aura')) return 'aura';
  if (t.includes('warframe')) return 'warframe';
  if (t.includes('primary')) return 'primary';
  if (t.includes('secondary')) return 'secondary';
  if (t.includes('melee')) return 'melee';
  if (t.includes('sentinel')) return 'sentinel';
  if (t.includes('companion')) return 'companion';
  if (t.includes('archwing')) return 'archwing';
  return 'misc';
}

export function normalizeMods(wfcdMods: WfcdMod[]): ModEntry[] {
  return wfcdMods
    .filter(m => m.uniqueName && m.name)
    .map(m => ({
      uniqueName: m.uniqueName,
      name: m.name,
      polarity: m.polarity ?? 'none',
      rarity: m.rarity ?? 'Common',
      maxRank: m.fusionLimit ?? 5,
      type: resolveModType(m),
      modSet: m.modSet ?? null,
      tradable: m.tradable ?? false,
      isAugment: m.isAugment ?? false,
      compatName: m.compatName ?? null,
      effects: parseEffects(m.levelStats),
      rawDescription: m.description ?? '',
    }));
}
```

- [ ] **Step 2: Update `pipeline/src/schema/wfcd.ts`** — add `isAugment` and `compatName` to `WfcdMod`

```typescript
// In WfcdMod interface, add after tradable:
  isAugment?: boolean;
  compatName?: string;
```

Open `pipeline/src/schema/wfcd.ts` and add those two fields to the `WfcdMod` interface after `tradable: boolean`.

- [ ] **Step 3: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "mods.ts"
```
Expected: no errors in mods.ts.

- [ ] **Step 4: Commit**

```bash
git add pipeline/src/normalizers/mods.ts pipeline/src/schema/wfcd.ts
git commit -m "feat(pipeline): mods normalizer — levelValues, effect target routing, isAugment, compatName"
```

---

## Task 6: Updated arcanes normalizer

**Files:**
- Modify: `pipeline/src/normalizers/arcanes.ts`

- [ ] **Step 1: Rewrite `pipeline/src/normalizers/arcanes.ts`**

```typescript
import type { WfcdArcane, WfcdLevelStat } from '../schema/wfcd.js';
import type { ArcaneEntry, ArcaneEffect } from '../schema/index.js';

const TRIGGER_PATTERNS: Array<[RegExp, string]> = [
  [/on\s+kill/i, 'on_kill'],
  [/on\s+headshot/i, 'on_headshot'],
  [/energy\s+pickup/i, 'on_energy_pickup'],
  [/shield\s+break/i, 'on_shield_break'],
  [/on\s+hit/i, 'on_hit'],
  [/on\s+cast/i, 'on_cast'],
  [/on\s+dodge/i, 'on_dodge'],
  [/on\s+melee/i, 'on_melee'],
];

function extractTrigger(desc: string): string {
  for (const [re, name] of TRIGGER_PATTERNS) {
    if (re.test(desc)) return name;
  }
  return 'passive';
}

function extractMaxStacks(desc: string): number {
  const m = desc.match(/(?:up to|max(?:imum)?)\s+(\d+)\s+stack/i);
  return m ? parseInt(m[1], 10) : 1;
}

function parseArcaneEffects(levelStats: WfcdLevelStat[] | undefined): ArcaneEffect[] {
  if (!levelStats?.length) return [];
  const effectCount = levelStats[0].stats?.length ?? 0;
  const results: ArcaneEffect[] = [];

  for (let effIdx = 0; effIdx < effectCount; effIdx++) {
    const levelValues: number[] = [];
    let stat = '';

    for (let rankIdx = 0; rankIdx < levelStats.length; rankIdx++) {
      const raw = (levelStats[rankIdx].stats?.[effIdx] ?? '').replace(/<[^>]+>/g, '');
      const match = raw.match(/([+-]?\d+(?:\.\d+)?)\s*%?/);
      const value = match ? parseFloat(match[1]) : 0;
      levelValues.push(value);
      if (rankIdx === 0 && !stat) {
        stat = raw.replace(/[+-]?\d+(?:\.\d+)?\s*%?\s*/, '').trim()
          .toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
      }
    }

    if (stat && levelValues.some(v => v !== 0)) {
      results.push({ stat, levelValues });
    }
  }
  return results;
}

export function normalizeArcanes(wfcdArcanes: WfcdArcane[]): ArcaneEntry[] {
  return wfcdArcanes
    .filter(a => a.uniqueName && a.name)
    .map(a => {
      const desc = a.description ?? '';
      return {
        uniqueName: a.uniqueName,
        name: a.name,
        maxRank: (a.levelStats?.length ?? 1) - 1,
        maxStacks: extractMaxStacks(desc),
        trigger: extractTrigger(desc),
        effects: parseArcaneEffects(a.levelStats),
        rawDescription: desc,
      };
    });
}
```

- [ ] **Step 2: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "arcanes.ts"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/normalizers/arcanes.ts
git commit -m "feat(pipeline): arcanes normalizer — levelValues per rank"
```

---

## Task 7: Abilities normalizer (scaling flags + augment map)

**Files:**
- Create: `pipeline/src/normalizers/abilities.ts`

Reads evaluated `Module:Ability/data` and `Module:Ability/data/stats` from wiki cache.

- [ ] **Step 1: Create `pipeline/src/normalizers/abilities.ts`**

```typescript
import type { LuaObj, LuaVal } from '../lua/eval.js';
import type { AbilitiesData } from '../schema/index.js';

export interface AbilityScalingFlags {
  strengthScaling: boolean;
  durationScaling: boolean;
  rangeScaling: boolean;
  efficiencyScaling: boolean;
}

export type AbilityScalingMap = Map<string, AbilityScalingFlags>;

// Build a map from ability uniqueName → scaling flags
// Uses Module:Ability/data/stats keyed by internal name
export function buildAbilityScalingMap(abilityStatsModule: LuaObj): AbilityScalingMap {
  const map = new Map<string, AbilityScalingFlags>();

  for (const [uniqueName, entry] of Object.entries(abilityStatsModule)) {
    if (!Array.isArray(entry)) continue;

    const flags: AbilityScalingFlags = {
      strengthScaling: false,
      durationScaling: false,
      rangeScaling: false,
      efficiencyScaling: false,
    };

    for (const block of entry as LuaVal[]) {
      if (typeof block !== 'object' || Array.isArray(block) || !block) continue;
      const modifier = (block as LuaObj)['Modifier'];
      if (typeof modifier !== 'string') continue;
      if (modifier === 'AVATAR_ABILITY_STRENGTH')   flags.strengthScaling = true;
      if (modifier === 'AVATAR_ABILITY_DURATION')   flags.durationScaling = true;
      if (modifier === 'AVATAR_ABILITY_RANGE')      flags.rangeScaling = true;
      if (modifier === 'AVATAR_ABILITY_EFFICIENCY') flags.efficiencyScaling = true;
    }

    map.set(uniqueName, flags);
  }

  return map;
}

// Build AbilitiesData: subsumable list + augmentName → ability uniqueName map
// Uses Module:Ability/data keyed by display name
export function buildAbilitiesData(abilityDataModule: LuaObj): AbilitiesData {
  const subsumable: string[] = [];
  const augmentToAbility: Record<string, string> = {};

  for (const [, entry] of Object.entries(abilityDataModule)) {
    if (typeof entry !== 'object' || Array.isArray(entry) || !entry) continue;
    const e = entry as LuaObj;

    const uniqueName = e['InternalName'];
    if (typeof uniqueName !== 'string') continue;

    if (e['Subsumable'] === true) subsumable.push(uniqueName);

    const augments = e['Augments'];
    if (Array.isArray(augments)) {
      for (const aug of augments) {
        if (typeof aug === 'string') augmentToAbility[aug] = uniqueName;
      }
    }
  }

  return { subsumable, augmentToAbility };
}
```

- [ ] **Step 2: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "abilities.ts"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/normalizers/abilities.ts
git commit -m "feat(pipeline): abilities normalizer — scaling flag map + augment→ability map"
```

---

## Task 8: Updated warframes normalizer

**Files:**
- Modify: `pipeline/src/normalizers/warframes.ts`

Add aura slots, initialEnergy, exilusPolarity from wiki; apply scaling flags from Task 7.

- [ ] **Step 1: Rewrite `pipeline/src/normalizers/warframes.ts`**

```typescript
import type { WfcdWarframe, WfcdAbility } from '../schema/wfcd.js';
import type { WarframeEntry, AbilityRef } from '../schema/index.js';
import type { LuaObj } from '../lua/eval.js';
import { buildAbilityScalingMap, type AbilityScalingMap } from './abilities.js';

function getWikiEntry(wikiWarframes: LuaObj | undefined, wfName: string): LuaObj | null {
  if (!wikiWarframes) return null;
  // Wiki uses display name as key; try exact match then case-insensitive
  if (wfName in wikiWarframes) return wikiWarframes[wfName] as LuaObj;
  const lower = wfName.toLowerCase();
  for (const [k, v] of Object.entries(wikiWarframes)) {
    if (k.toLowerCase() === lower) return v as LuaObj;
  }
  return null;
}

function parseAuraSlots(wikiEntry: LuaObj | null): number {
  if (!wikiEntry) return 1;
  const aura = wikiEntry['AuraPolarity'];
  if (Array.isArray(aura)) return aura.length;
  return 1;
}

function normalizeAbility(
  ab: WfcdAbility,
  slot: number,
  scalingMap: AbilityScalingMap,
): AbilityRef {
  const flags = scalingMap.get(ab.uniqueName) ?? {
    strengthScaling: false, durationScaling: false,
    rangeScaling: false, efficiencyScaling: false,
  };
  return { name: ab.name, slot, ...flags };
}

export function normalizeWarframes(
  wfcdWarframes: WfcdWarframe[],
  wikiModulesData: { warframes?: LuaObj; abilityStats?: LuaObj } = {},
): WarframeEntry[] {
  const scalingMap: AbilityScalingMap = wikiModulesData.abilityStats
    ? buildAbilityScalingMap(wikiModulesData.abilityStats)
    : new Map();

  const wikiWarframes = wikiModulesData.warframes
    ? ((wikiModulesData.warframes['Warframes'] as LuaObj) ?? wikiModulesData.warframes)
    : null;

  return wfcdWarframes
    .filter(w => w.uniqueName && w.name && w.category === 'Warframes')
    .map(w => {
      const wikiEntry = wikiWarframes ? getWikiEntry(wikiWarframes, w.name) : null;
      const initialEnergy = wikiEntry && typeof wikiEntry['InitialEnergy'] === 'number'
        ? (wikiEntry['InitialEnergy'] as number)
        : Math.floor((w.power ?? 100) / 4);
      const exilusPolarity = wikiEntry && typeof wikiEntry['ExilusPolarity'] === 'string'
        ? (wikiEntry['ExilusPolarity'] as string)
        : null;

      return {
        uniqueName: w.uniqueName,
        name: w.name,
        baseStats: {
          health: w.health ?? 100,
          shield: w.shield ?? 100,
          armor: w.armor ?? 0,
          energy: w.power ?? 100,
          sprint: w.sprintSpeed ?? w.sprint ?? 1.0,
        },
        polarities: w.polarities ?? [],
        aura: w.aura ?? null,
        auraSlots: parseAuraSlots(wikiEntry),
        abilities: (w.abilities ?? []).map((ab, i) => normalizeAbility(ab, i + 1, scalingMap)),
        passiveDescription: w.passiveDescription ?? '',
        masteryRank: w.masteryReq ?? 0,
        initialEnergy,
        exilusPolarity,
      };
    });
}
```

- [ ] **Step 2: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "warframes.ts"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/normalizers/warframes.ts
git commit -m "feat(pipeline): warframes normalizer — aura slots, initialEnergy, ability scaling flags from wiki"
```

---

## Task 9: Public Export fetcher — add ExportCustoms

**Files:**
- Modify: `pipeline/src/fetchers/public-export.ts`

- [ ] **Step 1: Add `ExportCustoms_en.json` to the EXPORT_KEYS array**

In `pipeline/src/fetchers/public-export.ts`, change:

```typescript
const EXPORT_KEYS = [
  'ExportWarframes_en.json',
  'ExportUpgrades_en.json',
  'ExportWeapons_en.json',
] as const;
```

to:

```typescript
const EXPORT_KEYS = [
  'ExportWarframes_en.json',
  'ExportUpgrades_en.json',
  'ExportWeapons_en.json',
  'ExportCustoms_en.json',
] as const;
```

- [ ] **Step 2: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "public-export.ts"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/fetchers/public-export.ts
git commit -m "feat(pipeline): public export fetcher now includes ExportCustoms"
```

---

## Task 10: Arcane helmets normalizer

**Files:**
- Create: `pipeline/src/normalizers/helmets.ts`

- [ ] **Step 1: Create `pipeline/src/normalizers/helmets.ts`**

```typescript
import type { ArcaneHelmetEntry, ArcaneHelmetEffect } from '../schema/index.js';

// Stat name mapping from wiki display names
const STAT_MAP: Array<[RegExp, string]> = [
  [/ability strength/i, 'abilityStrength'],
  [/ability duration/i, 'abilityDuration'],
  [/ability range/i, 'abilityRange'],
  [/ability efficiency/i, 'abilityEfficiency'],
  [/maximum health|max.*health/i, 'health'],
  [/maximum shields|shield capacity/i, 'shield'],
  [/armor/i, 'armor'],
  [/maximum energy|energy max/i, 'energy'],
  [/sprint speed|movement speed/i, 'sprint'],
  [/aim glide|wall latch/i, 'aimGlideDuration'],
  [/parkour/i, 'parkourVelocity'],
];

function resolveStatName(raw: string): string {
  const lower = raw.toLowerCase().trim();
  for (const [re, name] of STAT_MAP) {
    if (re.test(lower)) return name;
  }
  return lower.replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
}

function parseWikiTextEffects(wikitext: string): ArcaneHelmetEffect[] {
  const effects: ArcaneHelmetEffect[] = [];
  // Match: [[Stat Name]] (<span style="...">±X%</span>)
  const pattern = /\[\[([^\]]+)\]\][^\(]*\(<span[^>]+>([+-]?\d+(?:\.\d+)?)%<\/span>\)/g;
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(wikitext)) !== null) {
    const rawStat = m[1];
    const value = parseFloat(m[2]) / 100;
    effects.push({
      stat: resolveStatName(rawStat),
      value,
      isFlat: false,
    });
  }
  // Match flat values like "+150" (no %)
  const flatPattern = /\[\[([^\]]+)\]\][^\(]*\(<span[^>]+>([+-]?\d+(?:\.\d+)?)<\/span>\)/g;
  while ((m = flatPattern.exec(wikitext)) !== null) {
    if (m[0].includes('%')) continue; // skip percent, already caught above
    const rawStat = m[1];
    const value = parseFloat(m[2]);
    effects.push({
      stat: resolveStatName(rawStat),
      value,
      isFlat: true,
    });
  }
  return effects;
}

function extractWarframeName(description: string): string {
  const m = description.match(/This helmet is worn by ([^,.\n]+)/i);
  return m ? m[1].trim() : 'Unknown';
}

interface RawCustom {
  uniqueName: string;
  name: string;
  description?: string;
}

export function normalizeHelmets(
  exportCustoms: unknown[],
  arcaneHelmetWikitext: string,
): ArcaneHelmetEntry[] {
  // Identify arcane helmets from ExportCustoms
  const arcaneHelmets = (exportCustoms as RawCustom[]).filter(
    c => c.uniqueName?.includes('AltHelmet') && c.name?.startsWith('Arcane'),
  );

  // Build a map from helmet name → wikitext effects block
  // The wikitext has rows keyed by data-sort-value="Arcane X Helmet"
  const helmetsWithEffects = arcaneHelmets.map(h => {
    // Find the relevant wikitext block for this helmet
    const escapedName = h.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const blockPattern = new RegExp(
      `data-sort-value="${escapedName}".*?(?=data-sort-value=|$)`,
      's',
    );
    const blockMatch = arcaneHelmetWikitext.match(blockPattern);
    const effects = blockMatch ? parseWikiTextEffects(blockMatch[0]) : [];

    return {
      uniqueName: h.uniqueName,
      name: h.name,
      warframeName: extractWarframeName(h.description ?? ''),
      effects,
    };
  });

  return helmetsWithEffects;
}
```

- [ ] **Step 2: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "helmets.ts"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/normalizers/helmets.ts
git commit -m "feat(pipeline): arcane helmets normalizer — ExportCustoms + wiki wikitext parsing"
```

---

## Task 11: Mod sets normalizer

**Files:**
- Create: `pipeline/src/normalizers/mod-sets.ts`

- [ ] **Step 1: Create `pipeline/src/normalizers/mod-sets.ts`**

```typescript
import type { SetBonusEntry, SetBonusEffect } from '../schema/index.js';

interface WfcdSetMod {
  uniqueName: string;
  numUpgradesInSet?: number;
  stats?: string[];
  type?: string;
}

const STAT_MAP: Array<[RegExp, string, boolean]> = [
  // [pattern, statName, isFlat]
  [/energy spent.*converted to shields/i, 'energyToShieldOnCast', false],
  [/heavy attack.*teleport/i, 'heavyAttackTeleport', false],
  [/killing.*heavy attack.*reduces.*accuracy/i, 'heavyKillArmorStrip', false],
  [/combo count/i, 'comboCritChance', false],
  [/critical chance.*(\d+)/i, 'critChance', false],
  [/armor.*(\d+)/i, 'armor', false],
  [/health.*(\d+)/i, 'health', false],
];

function parseSetBonusStat(text: string): { stat: string; isFlat: boolean } | null {
  for (const [re, stat, isFlat] of STAT_MAP) {
    if (re.test(text)) return { stat, isFlat };
  }
  return null;
}

function parseSetBonusValue(text: string): number {
  const pct = text.match(/(\d+(?:\.\d+)?)\s*%/);
  if (pct) return parseFloat(pct[1]) / 100;
  const num = text.match(/(\d+(?:\.\d+)?)/);
  if (num) return parseFloat(num[1]);
  return 0;
}

export function normalizeModSets(allItems: unknown[]): SetBonusEntry[] {
  const setMods = (allItems as WfcdSetMod[]).filter(
    i => i.type === 'Mod Set Mod' && i.stats?.length,
  );

  return setMods.map(s => {
    const bonusByPieceCount: SetBonusEffect[] = (s.stats ?? []).map((statText, idx) => {
      const pieces = idx + 1;
      const parsed = parseSetBonusStat(statText);
      const value = parseSetBonusValue(statText);
      return {
        pieces,
        stat: parsed?.stat ?? 'unknown',
        value,
        isFlat: parsed?.isFlat ?? false,
      };
    }).filter(e => e.stat !== 'unknown');

    return {
      uniqueName: s.uniqueName,
      numPiecesInSet: s.numUpgradesInSet ?? bonusByPieceCount.length,
      bonusByPieceCount,
    };
  });
}
```

- [ ] **Step 2: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "mod-sets.ts"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/normalizers/mod-sets.ts
git commit -m "feat(pipeline): mod sets normalizer — parse set bonus values from WFCD set mod items"
```

---

## Task 12: Ability stats normalizer

**Files:**
- Create: `pipeline/src/normalizers/ability-stats.ts`

- [ ] **Step 1: Create `pipeline/src/normalizers/ability-stats.ts`**

```typescript
import type { LuaObj, LuaVal } from '../lua/eval.js';
import type { AbilityStatsEntry, AbilityStatBlock } from '../schema/index.js';

const MODIFIER_LABELS: Record<string, string> = {
  'AVATAR_ABILITY_EFFICIENCY': 'Energy Cost',
  'AVATAR_ABILITY_STRENGTH': 'Strength',
  'AVATAR_ABILITY_DURATION': 'Duration',
  'AVATAR_ABILITY_RANGE': 'Range',
};

export function normalizeAbilityStats(abilityStatsModule: LuaObj): AbilityStatsEntry[] {
  const entries: AbilityStatsEntry[] = [];

  for (const [uniqueName, statBlocks] of Object.entries(abilityStatsModule)) {
    if (!Array.isArray(statBlocks)) continue;

    const stats: AbilityStatBlock[] = [];

    for (const block of statBlocks as LuaVal[]) {
      if (typeof block !== 'object' || Array.isArray(block) || !block) continue;
      const b = block as LuaObj;
      const label = b['Label'];
      const modifier = b['Modifier'];
      const values = b['Values'];

      if (typeof label !== 'string' || typeof modifier !== 'string') continue;

      // Extract Val1 from Values table
      let baseValue = 0;
      if (typeof values === 'object' && !Array.isArray(values) && values) {
        const v = (values as LuaObj)['Val1'];
        if (typeof v === 'number') baseValue = v;
      }

      const isPercent = label.includes('%') || label.includes('|val1|%');
      const cleanLabel = label
        .replace(/\|val\d+\|%?/g, '')
        .replace(/[:\s]+$/g, '')
        .trim();

      if (isPercent) baseValue = baseValue / 100;

      stats.push({ label: cleanLabel, modifier: String(modifier), baseValue, isPercent });
    }

    if (stats.length > 0) entries.push({ uniqueName, stats });
  }

  return entries;
}
```

- [ ] **Step 2: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "ability-stats.ts"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/normalizers/ability-stats.ts
git commit -m "feat(pipeline): ability stats normalizer — per-ability energy cost + scaled values"
```

---

## Task 13: Wiki pages fetcher (Archon Shard scraping) + shards normalizer

**Files:**
- Create: `pipeline/src/fetchers/wiki-pages.ts`
- Create: `pipeline/src/normalizers/shards.ts`

- [ ] **Step 1: Create `pipeline/src/fetchers/wiki-pages.ts`**

```typescript
const WIKI_API = 'https://wiki.warframe.com/api.php';

async function fetchPageWikitext(page: string): Promise<string> {
  const params = new URLSearchParams({
    action: 'parse', page, prop: 'wikitext', format: 'json',
  });
  const res = await fetch(`${WIKI_API}?${params}`, {
    headers: { 'User-Agent': 'warframe-planner/0.1 (github.com/warframe-planner)' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching page ${page}`);
  const json = await res.json() as { parse?: { wikitext?: { '*'?: string } }; error?: { info: string } };
  if (json.error) throw new Error(`Wiki API error: ${json.error.info}`);
  return json.parse?.wikitext?.['*'] ?? '';
}

export interface WikiPagesRaw {
  arcaneHelmet: string;
  archonShard: string;
}

export async function fetchWikiPages(): Promise<WikiPagesRaw> {
  process.stdout.write('  fetching Arcane Helmet page...');
  const arcaneHelmet = await fetchPageWikitext('Arcane Helmet');
  process.stdout.write(` ${(arcaneHelmet.length / 1024).toFixed(0)}KB\n`);

  process.stdout.write('  fetching Archon Shard page...');
  const archonShard = await fetchPageWikitext('Archon Shard');
  process.stdout.write(` ${(archonShard.length / 1024).toFixed(0)}KB\n`);

  return { arcaneHelmet, archonShard };
}
```

- [ ] **Step 2: Create `pipeline/src/normalizers/shards.ts`**

```typescript
import type { ShardBonus } from '../schema/index.js';

const SHARD_SECTIONS: Record<string, string> = {
  crimson: 'crimson_archon_shard_buffs',
  amber: 'amber_archon_shard_buffs',
  azure: 'azure_archon_shard_buffs',
  topaz: 'topaz_archon_shard_buffs',
  violet: 'violet_archon_shard_buffs',
  emerald: 'emerald_archon_shard_buffs',
};

const STAT_MAP: Array<[RegExp, string, boolean]> = [
  // [pattern, statName, isFlat]
  [/ability strength/i, 'abilityStrength', false],
  [/ability duration/i, 'abilityDuration', false],
  [/melee.*critical damage/i, 'meleeCritDamage', false],
  [/primary.*status chance/i, 'primaryStatusChance', false],
  [/secondary.*critical chance/i, 'secondaryCritChance', false],
  [/casting speed/i, 'castSpeed', false],
  [/parkour velocity/i, 'parkourVelocity', false],
  [/armor.*(\d+)\s*\(/i, 'armor', true],      // flat armor (has number before parens)
  [/max.*health.*(\d+)\s*\(/i, 'health', true],
  [/shield capacity.*(\d+)\s*\(/i, 'shield', true],
  [/energy max.*(\d+)\s*\(/i, 'energy', true],
  [/health.*regen/i, 'healthRegen', true],
  [/health orb/i, 'healthOrbEffectiveness', false],
  [/energy orb/i, 'energyOrbEffectiveness', false],
  [/armor.*\+\d+%/i, 'armor', false],         // percent armor (no flat number)
];

function resolveShardStat(text: string): { stat: string; isFlat: boolean } {
  for (const [re, stat, isFlat] of STAT_MAP) {
    if (re.test(text)) return { stat, isFlat };
  }
  return { stat: 'unknown', isFlat: false };
}

// Detect if the buff is conditional (kill-triggered, status-triggered, etc.)
function isConditional(text: string): boolean {
  return /kill|killing|killed|status|affected by|gains\s+\d|stacking|reset/i.test(text);
}

function extractNormalValue(text: string): number | null {
  // "+X% (+Y%)" or "+X (+Y)" — normal value is X
  const pctMatch = text.match(/\+(\d+(?:\.\d+)?)\s*%?\s*\(/);
  if (pctMatch) {
    const fullText = text;
    if (fullText.includes('%')) return parseFloat(pctMatch[1]) / 100;
    return parseFloat(pctMatch[1]);
  }
  const flatMatch = text.match(/\+(\d+(?:\.\d+)?)\s+[A-Z]/);
  if (flatMatch) return parseFloat(flatMatch[1]);
  return null;
}

export type ShardsOutput = Record<string, ShardBonus[]>;

export function normalizeShards(archonShardWikitext: string): ShardsOutput {
  const output: ShardsOutput = {};

  for (const [color, sectionId] of Object.entries(SHARD_SECTIONS)) {
    const sectionStart = archonShardWikitext.indexOf(`<section begin="${sectionId}" />`);
    const sectionEnd = archonShardWikitext.indexOf(`<section end="${sectionId}" />`);
    if (sectionStart === -1 || sectionEnd === -1) continue;

    const section = archonShardWikitext.slice(sectionStart, sectionEnd);
    const bonuses: ShardBonus[] = [];

    // Each buff line starts with "| +"
    const lines = section.split('\n').filter(l => l.trim().startsWith('| +') || l.trim().startsWith('| Gain'));

    for (const line of lines) {
      const value = extractNormalValue(line);
      if (value === null) continue;

      const { stat, isFlat } = resolveShardStat(line);
      if (stat === 'unknown') continue;

      bonuses.push({
        stat,
        value,
        isFlat,
        conditional: isConditional(line),
      });
    }

    output[color] = bonuses;
  }

  return output;
}
```

- [ ] **Step 3: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep -E "(wiki-pages|shards).ts"
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/src/fetchers/wiki-pages.ts pipeline/src/normalizers/shards.ts
git commit -m "feat(pipeline): wiki pages fetcher (Arcane Helmet + Archon Shard) and shards normalizer"
```

---

## Task 14: Updated weapons normalizer

**Files:**
- Modify: `pipeline/src/normalizers/weapons.ts`

- [ ] **Step 1: Rewrite `pipeline/src/normalizers/weapons.ts`**

```typescript
import type { WfcdWeapon } from '../schema/wfcd.js';
import type { WeaponEntry, WeaponStats } from '../schema/index.js';

function normalizeWeaponStats(w: WfcdWeapon): WeaponStats {
  const raw = w.damageTypes ?? {};
  const damageTypes: Record<string, number> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (typeof v === 'number' && v > 0) damageTypes[k] = v;
  }
  const totalDamage = w.totalDamage ?? Object.values(damageTypes).reduce((a, b) => a + b, 0);

  const stats: WeaponStats = {
    totalDamage,
    damageTypes,
    critChance: w.criticalChance ?? 0,
    critMultiplier: w.criticalMultiplier ?? 1,
    statusChance: w.statusChance ?? w.procChance ?? 0,
    fireRate: w.fireRate ?? w.attackSpeed ?? 1,
    magazineSize: w.magazineSize ?? 0,
    reloadTime: w.reloadTime ?? 0,
    multishot: w.multishot ?? 1,
  };

  if (w.range != null) stats.range = w.range;
  if (w.attackSpeed != null) stats.attackSpeed = w.attackSpeed;
  if (w.comboDuration != null) stats.comboDuration = w.comboDuration;
  if (w.heavyAttackDamage != null) stats.heavyAttackDamage = w.heavyAttackDamage;

  return stats;
}

function resolveSlot(category: string): number {
  const c = category.toLowerCase();
  if (c.includes('primary') || c.includes('arch-gun')) {
    if (c.includes('arch-gun')) return 5;
    return 0;
  }
  if (c.includes('secondary')) return 1;
  if (c.includes('melee') || c.includes('arch-melee')) return 2;
  return 0;
}

export function normalizeWeapons(guns: WfcdWeapon[], melee: WfcdWeapon[]): WeaponEntry[] {
  return [...guns, ...melee]
    .filter(w => w.uniqueName && w.name)
    .map(w => ({
      uniqueName: w.uniqueName,
      name: w.name,
      type: w.category ?? 'Unknown',
      slot: resolveSlot(w.category ?? ''),
      baseStats: normalizeWeaponStats(w),
      disposition: w.disposition ?? 3,
      masteryRank: w.masteryReq ?? 0,
    }));
}
```

- [ ] **Step 2: Update `pipeline/src/schema/wfcd.ts`** — add `comboDuration` and `heavyAttackDamage` to `WfcdWeapon`

Open `pipeline/src/schema/wfcd.ts` and add to `WfcdWeapon` interface:
```typescript
  comboDuration?: number;
  heavyAttackDamage?: number;
```

- [ ] **Step 3: Build check**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1 | grep "weapons.ts"
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/src/normalizers/weapons.ts pipeline/src/schema/wfcd.ts
git commit -m "feat(pipeline): weapons normalizer — comboDuration, heavyAttackDamage, slot field"
```

---

## Task 15: Wire everything together in index.ts

**Files:**
- Modify: `pipeline/src/index.ts`

- [ ] **Step 1: Rewrite `pipeline/src/index.ts`**

```typescript
import { writeFileSync, readFileSync, mkdirSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { fetchWfcd } from './fetchers/wfcd.js';
import { fetchPublicExport } from './fetchers/public-export.js';
import { fetchWikiLua } from './fetchers/wiki-lua.js';
import { fetchWikiPages } from './fetchers/wiki-pages.js';
import { normalizeWarframes } from './normalizers/warframes.js';
import { normalizeMods } from './normalizers/mods.js';
import { normalizeArcanes } from './normalizers/arcanes.js';
import { normalizeWeapons } from './normalizers/weapons.js';
import { normalizeHelmets } from './normalizers/helmets.js';
import { normalizeModSets } from './normalizers/mod-sets.js';
import { normalizeAbilityStats } from './normalizers/ability-stats.js';
import { normalizeShards } from './normalizers/shards.js';
import { buildAbilitiesData } from './normalizers/abilities.js';
import type { Manifest, LuaObj } from './schema/index.js';

// LuaObj re-export for convenience
export type { LuaObj } from './lua/eval.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '../../');
const DATA_DIR = resolve(ROOT, 'data');
const CACHE_DIR = resolve(__dirname, '../cache');

function readManifest(): Manifest {
  try {
    return JSON.parse(readFileSync(resolve(DATA_DIR, 'manifest.json'), 'utf8')) as Manifest;
  } catch {
    return { lastUpdated: '', sourceVersions: { wfcd: '', publicExport: '', wiki: {}, wikiPages: {} } };
  }
}

function writeData<T>(filename: string, data: T extends unknown[] ? T : T) {
  writeFileSync(resolve(DATA_DIR, filename), JSON.stringify(data, null, 2));
  const count = Array.isArray(data) ? `${(data as unknown[]).length} entries` : 'object';
  console.log(`  wrote ${count} → data/${filename}`);
}

function writeCache(filename: string, data: unknown) {
  if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
  writeFileSync(resolve(CACHE_DIR, filename), JSON.stringify(data, null, 2));
}

function readCache<T>(filename: string): T | null {
  const path = resolve(CACHE_DIR, filename);
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, 'utf8')) as T;
  } catch {
    return null;
  }
}

async function run(fresh: boolean, skipWiki: boolean) {
  console.log(`\nWarframe Planner — data pipeline (${fresh ? 'fresh' : 'incremental'}${skipWiki ? ', --skip-wiki' : ''})\n`);

  const manifest = readManifest();

  // ── WFCD (local npm package, always fast) ──────────────────────────────────
  console.log('Loading WFCD...');
  const wfcd = fetchWfcd();

  // ── Public Export ──────────────────────────────────────────────────────────
  console.log('Fetching Public Export...');
  type PECache = Awaited<ReturnType<typeof fetchPublicExport>>;
  let publicExport = fresh ? null : readCache<PECache>('public-export-raw.json');
  if (!publicExport) {
    publicExport = await fetchPublicExport();
    writeCache('public-export-raw.json', publicExport);
  }

  if (!fresh && publicExport.indexHash === manifest.sourceVersions.publicExport) {
    console.log('No upstream changes. Use --fresh to force.\n');
    return;
  }

  // ── Wiki Lua modules ───────────────────────────────────────────────────────
  type WikiCache = Awaited<ReturnType<typeof fetchWikiLua>>;
  let wikiLua: WikiCache;
  if (skipWiki) {
    console.log('Skipping wiki Lua modules (--skip-wiki).');
    wikiLua = { modules: {}, revIds: {} };
  } else {
    console.log('Fetching Wiki Lua modules...');
    const cachedWiki = fresh ? null : readCache<WikiCache>('wiki-lua-raw.json');
    if (cachedWiki?.modules) {
      wikiLua = cachedWiki;
      console.log('  (using cache)');
    } else {
      wikiLua = await fetchWikiLua();
      writeCache('wiki-lua-raw.json', wikiLua);
    }
  }

  // ── Wiki article pages (Arcane Helmet + Archon Shard) ─────────────────────
  type WikiPagesCache = Awaited<ReturnType<typeof fetchWikiPages>>;
  let wikiPages: WikiPagesCache;
  if (skipWiki) {
    wikiPages = { arcaneHelmet: '', archonShard: '' };
  } else {
    console.log('Fetching Wiki pages...');
    const cachedPages = fresh ? null : readCache<WikiPagesCache>('wiki-pages-raw.json');
    if (cachedPages?.archonShard) {
      wikiPages = cachedPages;
      console.log('  (using cache)');
    } else {
      wikiPages = await fetchWikiPages();
      writeCache('wiki-pages-raw.json', wikiPages);
    }
  }

  // ── Normalize ──────────────────────────────────────────────────────────────
  console.log('\nNormalizing...');

  const wikiModData = {
    warframes: wikiLua.modules['Module:Warframes/data'] as Record<string, unknown> | undefined,
    abilityStats: wikiLua.modules['Module:Ability/data/stats'] as Record<string, unknown> | undefined,
  };

  const exports = publicExport.exports as Record<string, { [key: string]: unknown[] }>;
  const exportCustoms = (exports['ExportCustoms_en.json']?.['ExportCustoms'] ?? []) as unknown[];
  const allWfcdItems = [...(wfcd.mods as unknown[]), ...(wfcd.arcanes as unknown[])];
  const allWfcdAll = new (await import('warframe-items')).default({ category: ['All'] }) as unknown[];

  writeData('warframes.json', normalizeWarframes(wfcd.warframes, wikiModData));
  writeData('mods.json', normalizeMods(wfcd.mods));
  writeData('arcanes.json', normalizeArcanes(wfcd.arcanes));
  writeData('weapons.json', normalizeWeapons(wfcd.guns, wfcd.melee));
  writeData('helmets.json', normalizeHelmets(exportCustoms, wikiPages.arcaneHelmet));
  writeData('mod-sets.json', normalizeModSets(allWfcdAll));
  writeData('ability-stats.json', normalizeAbilityStats(
    (wikiLua.modules['Module:Ability/data/stats'] ?? {}) as Record<string, unknown>,
  ));

  const shardsOutput = normalizeShards(wikiPages.archonShard);
  writeData('shard-bonuses.json', shardsOutput as unknown as unknown[]);

  const abilitiesData = buildAbilitiesData(
    (wikiLua.modules['Module:Ability/data'] ?? {}) as Record<string, unknown>,
  );
  writeFileSync(resolve(DATA_DIR, 'abilities.json'), JSON.stringify(abilitiesData, null, 2));
  console.log(`  wrote abilities.json (${abilitiesData.subsumable.length} subsumable, ${Object.keys(abilitiesData.augmentToAbility).length} augments)`);

  // ── Manifest ───────────────────────────────────────────────────────────────
  const newManifest: Manifest = {
    lastUpdated: new Date().toISOString(),
    sourceVersions: {
      wfcd: '1.1269.x',
      publicExport: publicExport.indexHash,
      wiki: wikiLua.revIds as Record<string, number>,
      wikiPages: {
        arcaneHelmet: String(wikiPages.arcaneHelmet.length),
        archonShard: String(wikiPages.archonShard.length),
      },
    },
  };
  writeFileSync(resolve(DATA_DIR, 'manifest.json'), JSON.stringify(newManifest, null, 2));
  console.log('\nDone. manifest.json updated.\n');
}

const args = process.argv.slice(2);
if (args[0] === 'run') {
  run(args.includes('--fresh'), args.includes('--skip-wiki')).catch(err => {
    console.error(err);
    process.exit(1);
  });
}
```

- [ ] **Step 2: Build — all errors must be resolved**

```bash
cd /Users/elias/Documents/WFC/pipeline && npm run build 2>&1
```
Expected: **zero errors**. Fix any remaining type errors before proceeding.

- [ ] **Step 3: Commit**

```bash
git add pipeline/src/index.ts
git commit -m "feat(pipeline): wire all new normalizers into index.ts, write all data/ output files"
```

---

## Task 16: Run pipeline and verify output

- [ ] **Step 1: Run with --skip-wiki first (fast sanity check)**

```bash
cd /Users/elias/Documents/WFC/pipeline && npx tsx src/index.ts run --fresh --skip-wiki 2>&1
```
Expected:
```
  wrote 110 entries → data/warframes.json
  wrote 1733 entries → data/mods.json
  wrote 172 entries → data/arcanes.json
  wrote 585 entries → data/weapons.json
  wrote 0 entries → data/helmets.json      (expected: skip-wiki gives no wiki pages)
  wrote ... entries → data/mod-sets.json
  ...
Done. manifest.json updated.
```

- [ ] **Step 2: Verify levelValues in mods.json**

```bash
python3 -c "
import json
mods = json.load(open('/Users/elias/Documents/WFC/data/mods.json'))
vit = next(m for m in mods if m['name'] == 'Vitality')
effects = vit['effects']
print('Vitality effects:', effects)
assert len(effects) > 0, 'No effects'
assert 'levelValues' in effects[0], 'levelValues missing'
assert len(effects[0]['levelValues']) == 11, f'Expected 11 levels, got {len(effects[0][\"levelValues\"])}'
assert abs(effects[0]['levelValues'][10] - 1.0) < 0.01, f'Max rank should be ~1.0, got {effects[0][\"levelValues\"][10]}'
print('PASS: Vitality levelValues correct')
"
```

- [ ] **Step 3: Verify auraSlots in warframes.json**

```bash
python3 -c "
import json
frames = json.load(open('/Users/elias/Documents/WFC/data/warframes.json'))
frost = next(f for f in frames if f['name'] == 'Frost')
assert 'auraSlots' in frost, 'auraSlots missing'
print('Frost auraSlots:', frost['auraSlots'])
print('PASS')
"
```

- [ ] **Step 4: Run full pipeline with wiki**

```bash
cd /Users/elias/Documents/WFC/pipeline && npx tsx src/index.ts run --fresh 2>&1
```
Expected: all files written including helmets, shard-bonuses, ability-stats.

- [ ] **Step 5: Verify ability scaling flags are populated**

```bash
python3 -c "
import json
frames = json.load(open('/Users/elias/Documents/WFC/data/warframes.json'))
rhino = next(f for f in frames if f['name'] == 'Rhino')
roar = next(a for a in rhino['abilities'] if a['name'] == 'Roar')
print('Roar:', roar)
assert roar['strengthScaling'], 'Roar should scale with strength'
assert roar['durationScaling'], 'Roar should scale with duration'
print('PASS: ability scaling flags populated from wiki')
"
```

- [ ] **Step 6: Verify augment map**

```bash
python3 -c "
import json
abilities = json.load(open('/Users/elias/Documents/WFC/data/abilities.json'))
print('Subsumable count:', len(abilities['subsumable']))
print('Augment map entries:', len(abilities['augmentToAbility']))
print('Piercing Roar maps to:', abilities['augmentToAbility'].get('Piercing Roar', 'NOT FOUND'))
assert len(abilities['subsumable']) >= 10, 'Expected at least 10 subsumable abilities'
print('PASS')
"
```

- [ ] **Step 7: Commit final data output**

```bash
git add data/ && git commit -m "data: regenerated with levelValues, ability flags, helmets, shards, mod-sets, ability-stats"
```

---

## Self-Review

**Spec coverage:**
- ✅ 1.1 Lua evaluator — Task 1
- ✅ 1.2 Module:Ability/data/stats added — Task 4
- ✅ 1.3 levelValues — Tasks 3, 5, 6
- ✅ 1.4 ModEffect.target — Task 5
- ✅ 1.5 Ability scaling flags — Tasks 7, 8
- ✅ 1.6 Warframes/data enrichment (aura slots, initialEnergy) — Task 8
- ✅ 1.7 Augment mod fields (isAugment, compatName) — Task 5
- ✅ 1.8 Arcane helmets — Tasks 9, 10
- ✅ 1.9 Mod set bonuses — Task 11
- ✅ 1.10 Ability stats — Task 12
- ✅ 1.11 Weapon schema expansion — Task 14
- ✅ 1.13 Wiki page scraping (helmets + shards) — Task 13
- ✅ 1.14 Endo formula — in upgrade_cost.py (Plan B); pipeline exports rarity from WFCD
- ✅ 1.15 Static data files — Task 2

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:**
- `WikiLuaRaw.modules` uses `LuaObj` (from eval.ts) consistently across Tasks 4, 7, 8, 12
- `ModEffect.levelValues: number[]` defined in Task 3, used in Tasks 5, 6
- `EffectTarget` defined in Task 3, used in Task 5
- `normalizeWarframes` signature updated in Task 8 to accept `wikiModulesData` — callers in Task 15 pass correct shape
