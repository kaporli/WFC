# Warframe Planner — Data Pipeline Setup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the warframe-planner monorepo with a working TypeScript data pipeline that ingests from WFCD, DE Public Export, and Warframe Wiki Lua modules, normalizes into versioned JSON, and auto-updates via GitHub Actions nightly.

**Architecture:** Monorepo with a `pipeline/` TypeScript package (fetch → cache → normalize → data/) and an `engine/` Python package (reads data/, implements calc formulas). GitHub Actions runs `pipeline run --fresh` nightly and commits diffs to `data/`. A `cache/` directory in pipeline avoids re-fetching during local dev.

**Tech Stack:** Node 20, TypeScript 5, tsx (TS runner), warframe-items (WFCD npm), lzma-js (Public Export decompression), fengari-node (Lua eval for wiki modules), zod (schema validation). Python 3.12, uv (package manager).

---

## File Map

```
/
├── .gitignore
├── README.md
├── package.json                         # root workspace
│
├── pipeline/
│   ├── package.json                     # TS deps
│   ├── tsconfig.json
│   └── src/
│       ├── schema/
│       │   └── index.ts                 # all shared TypeScript types (WarframeEntry, ModEntry, etc.)
│       ├── fetchers/
│       │   ├── wfcd.ts                  # reads warframe-items npm package, returns raw categorised items
│       │   ├── public-export.ts         # fetches + LZMA-decompresses DE Public Export
│       │   └── wiki-lua.ts             # MediaWiki API → raw Lua → parsed JS objects
│       ├── normalizers/
│       │   ├── warframes.ts             # merges WFCD + PublicExport warframe data → WarframeEntry[]
│       │   ├── mods.ts                  # merges sources, parses levelStats → ModEntry[]
│       │   ├── arcanes.ts               # extracts trigger/maxStacks → ArcaneEntry[]
│       │   └── weapons.ts               # merges sources → WeaponEntry[]
│       └── index.ts                     # CLI: `pipeline run [--fresh]`
│
├── data/
│   ├── warframes.json
│   ├── mods.json
│   ├── arcanes.json
│   ├── weapons.json
│   └── manifest.json
│
├── engine/
│   ├── pyproject.toml
│   ├── warframe_engine/
│   │   ├── __init__.py
│   │   └── loader.py                    # loads data/ JSON into typed dataclasses
│   ├── interactions/
│   │   └── README.md                    # format spec for conditional mechanics YAML
│   └── tests/
│       ├── __init__.py
│       └── test_loader.py
│
└── .github/
    └── workflows/
        └── data-pipeline.yml
```

---

## Task 1: Git init + root scaffold

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `package.json`

- [ ] **Step 1: Init git repo**

```bash
cd /Users/elias/Documents/WFC
git init
```

- [ ] **Step 2: Write `.gitignore`**

```
node_modules/
pipeline/cache/
pipeline/dist/
*.lzma
.env
__pycache__/
*.pyc
.venv/
dist/
.DS_Store
```

- [ ] **Step 3: Write root `package.json`**

```json
{
  "name": "warframe-planner",
  "private": true,
  "workspaces": ["pipeline"],
  "scripts": {
    "pipeline": "npm run -w pipeline",
    "ingest": "npm run -w pipeline run"
  }
}
```

- [ ] **Step 4: Write `README.md`**

```markdown
# warframe-planner

Warframe build planner — data pipeline and calc engine.

## Data pipeline

Pulls from WFCD (warframe-items), DE Public Export, and Warframe Wiki Lua modules. Outputs normalized JSON to `data/`.

```bash
cd pipeline && npm install
npm run pipeline run          # incremental (skips if upstream unchanged)
npm run pipeline run --fresh  # force full re-fetch
```

## Engine

Python calc engine reads from `data/`.

```bash
cd engine && uv sync
uv run pytest
```
```

- [ ] **Step 5: Initial commit**

```bash
git add .gitignore README.md package.json
git commit -m "chore: init repo"
```

---

## Task 2: Pipeline package setup + TypeScript types

**Files:**
- Create: `pipeline/package.json`
- Create: `pipeline/tsconfig.json`
- Create: `pipeline/src/schema/index.ts`

- [ ] **Step 1: Write `pipeline/package.json`**

```json
{
  "name": "@wfp/pipeline",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "run": "tsx src/index.ts run",
    "build": "tsc --noEmit"
  },
  "dependencies": {
    "warframe-items": "^2.0.0",
    "lzma-js": "^0.7.2",
    "fengari-node": "^0.1.4",
    "zod": "^3.23.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "tsx": "^4.0.0",
    "typescript": "^5.4.0"
  }
}
```

- [ ] **Step 2: Write `pipeline/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Write `pipeline/src/schema/index.ts`**

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
  slot: number; // 1-4
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
  abilities: AbilityRef[];
  passiveDescription: string;
  masteryRank: number;
}

export type StackType = 'additive_base' | 'additive_stacking' | 'multiplicative';

export interface ModEffect {
  stat: string;                // e.g. "abilityStrength", "health", "armor"
  stackType: StackType;
  valuePerRank: number;        // e.g. 0.044 for +4.4% per rank
}

export interface ModEntry {
  uniqueName: string;
  name: string;
  polarity: string;
  rarity: string;
  maxRank: number;
  type: string;                // "warframe" | "primary" | "secondary" | "melee" | "aura" | "stance" | "companion"
  modSet: string | null;
  tradable: boolean;
  effects: ModEffect[];
  rawDescription: string;
}

export interface ArcaneEffect {
  stat: string;
  value: number;
  atMaxRank: boolean;
}

export interface ArcaneEntry {
  uniqueName: string;
  name: string;
  maxRank: number;
  maxStacks: number;
  trigger: string;             // "on_kill" | "on_headshot" | "on_energy_pickup" | etc.
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
}

export interface WeaponEntry {
  uniqueName: string;
  name: string;
  type: string;                // "Primary" | "Secondary" | "Melee" | "Arch-Gun" | "Arch-Melee"
  baseStats: WeaponStats;
  disposition: number;         // riven disposition 1-5
  masteryRank: number;
}

export interface Manifest {
  lastUpdated: string;
  sourceVersions: {
    wfcd: string;
    publicExport: string;
    wiki: Record<string, number>;
  };
}
```

- [ ] **Step 4: Install deps**

```bash
cd pipeline && npm install
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd pipeline && npm run build
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add pipeline/
git commit -m "feat: add pipeline package with TypeScript schema types"
```

---

## Task 3: WFCD fetcher

**Files:**
- Create: `pipeline/src/fetchers/wfcd.ts`

The `warframe-items` package exports a constructor. `new Items()` returns all items. Each item has a `.category` field.

- [ ] **Step 1: Write `pipeline/src/fetchers/wfcd.ts`**

```typescript
import Items from 'warframe-items';

export interface WfcdRaw {
  warframes: Items.Warframe[];
  mods: Items.Mod[];
  arcanes: Items.Arcane[];
  primary: Items.Primary[];
  secondary: Items.Secondary[];
  melee: Items.Melee[];
}

export async function fetchWfcd(): Promise<WfcdRaw> {
  const all = new Items({ category: ['Warframes', 'Mods', 'Arcanes', 'Primary', 'Secondary', 'Melee'] });

  return {
    warframes: all.filter((i): i is Items.Warframe => i.category === 'Warframes'),
    mods: all.filter((i): i is Items.Mod => i.category === 'Mods'),
    arcanes: all.filter((i): i is Items.Arcane => i.category === 'Arcanes'),
    primary: all.filter((i): i is Items.Primary => i.category === 'Primary'),
    secondary: all.filter((i): i is Items.Secondary => i.category === 'Secondary'),
    melee: all.filter((i): i is Items.Melee => i.category === 'Melee'),
  };
}
```

- [ ] **Step 2: Smoke test manually**

Add this to `pipeline/src/fetchers/wfcd.ts` temporarily and run:

```bash
cd pipeline && npx tsx src/fetchers/wfcd.ts
```

Add at bottom of file (remove after verifying):
```typescript
// smoke test
const raw = await fetchWfcd();
console.log(`Warframes: ${raw.warframes.length}, Mods: ${raw.mods.length}, Arcanes: ${raw.arcanes.length}`);
```

Expected: `Warframes: 60+, Mods: 1000+, Arcanes: 100+`

- [ ] **Step 3: Remove smoke test, commit**

```bash
git add pipeline/src/fetchers/wfcd.ts
git commit -m "feat: add WFCD fetcher"
```

---

## Task 4: Public Export fetcher

**Files:**
- Create: `pipeline/src/fetchers/public-export.ts`

The Public Export flow: fetch the LZMA-compressed index → parse to get hashed file paths → fetch + decompress each export JSON.

- [ ] **Step 1: Write `pipeline/src/fetchers/public-export.ts`**

```typescript
import { decompress } from 'lzma-js';

const INDEX_URL = 'https://origin.warframe.com/PublicExport/index_en.txt.lzma';
const CONTENT_BASE = 'https://content.warframe.com/PublicExport/Manifest/';

const EXPORT_KEYS = [
  'ExportWarframes_en.json',
  'ExportUpgrades_en.json',
  'ExportWeapons_en.json',
] as const;

type ExportKey = typeof EXPORT_KEYS[number];

async function fetchAndDecompress(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  const buf = Buffer.from(await res.arrayBuffer());
  return new Promise((resolve, reject) => {
    decompress(buf, (result, err) => {
      if (err) reject(new Error(String(err)));
      else resolve(Array.isArray(result) ? Buffer.from(result).toString('utf8') : String(result));
    });
  });
}

export interface PublicExportRaw {
  indexHash: string;
  exports: Record<ExportKey, unknown>;
}

export async function fetchPublicExport(): Promise<PublicExportRaw> {
  const indexText = await fetchAndDecompress(INDEX_URL);
  const lines = indexText.trim().split('\n');

  // Each line: /PublicExport/Manifest/ExportFoo_en.json.lzma!<hash>
  const pathMap = new Map<string, string>();
  for (const line of lines) {
    const [path, hash] = line.split('!');
    if (path && hash) pathMap.set(path.trim().split('/').pop() ?? '', hash.trim());
  }

  const indexHash = pathMap.get('index_en.txt.lzma') ?? lines[0] ?? '';

  const exports: Partial<Record<ExportKey, unknown>> = {};
  for (const key of EXPORT_KEYS) {
    const lzmaKey = key + '.lzma';
    const hash = pathMap.get(lzmaKey);
    if (!hash) throw new Error(`Export key not found in index: ${lzmaKey}`);
    const url = `${CONTENT_BASE}${lzmaKey}!${hash}`;
    const text = await fetchAndDecompress(url);
    exports[key] = JSON.parse(text);
  }

  return { indexHash, exports: exports as Record<ExportKey, unknown> };
}
```

- [ ] **Step 2: Smoke test**

Add temporarily and run:
```bash
cd pipeline && npx tsx src/fetchers/public-export.ts
```

```typescript
const raw = await fetchPublicExport();
console.log('indexHash:', raw.indexHash.slice(0, 16));
console.log('keys:', Object.keys(raw.exports));
```

Expected: prints hash and three export key names.

- [ ] **Step 3: Remove smoke test, commit**

```bash
git add pipeline/src/fetchers/public-export.ts
git commit -m "feat: add Public Export fetcher with LZMA decompression"
```

---

## Task 5: Wiki Lua fetcher

**Files:**
- Create: `pipeline/src/fetchers/wiki-lua.ts`

The wiki exposes Lua data modules via MediaWiki API. We fetch the raw Lua source and evaluate it with `fengari-node` to get a plain JS object.

- [ ] **Step 1: Write `pipeline/src/fetchers/wiki-lua.ts`**

```typescript
import { load } from 'fengari-node';

const WIKI_API = 'https://warframe.wiki.gg/api.php';

const MODULES = [
  'Module:Mods/data',
  'Module:Warframes/data',
  'Module:Ability/data',
] as const;

type ModuleName = typeof MODULES[number];

async function fetchModuleSource(title: string): Promise<{ content: string; revId: number }> {
  const params = new URLSearchParams({
    action: 'query',
    titles: title,
    prop: 'revisions',
    rvprop: 'content|ids',
    rvslots: 'main',
    format: 'json',
    formatversion: '2',
  });
  const res = await fetch(`${WIKI_API}?${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${title}`);
  const json = await res.json();
  const page = json.query.pages[0];
  if (page.missing) throw new Error(`Wiki module not found: ${title}`);
  const rev = page.revisions[0];
  return { content: rev.slots.main.content, revId: rev.revid };
}

function evalLuaModule(src: string): unknown {
  // Wrap in a function that returns the table, then evaluate
  const wrapped = `return (function() ${src.replace(/^return\s+/, 'local _m = ').replace(/^local _m = /, 'local _m = ')} return _m end)()`;
  // fengari-node evaluates Lua and returns the result as a JS value
  return load(wrapped)();
}

export interface WikiLuaRaw {
  modules: Partial<Record<ModuleName, unknown>>;
  revIds: Partial<Record<ModuleName, number>>;
}

export async function fetchWikiLua(): Promise<WikiLuaRaw> {
  const modules: Partial<Record<ModuleName, unknown>> = {};
  const revIds: Partial<Record<ModuleName, number>> = {};

  for (const mod of MODULES) {
    const { content, revId } = await fetchModuleSource(mod);
    modules[mod] = evalLuaModule(content);
    revIds[mod] = revId;
  }

  return { modules, revIds };
}
```

- [ ] **Step 2: Smoke test**

```bash
cd pipeline && npx tsx src/fetchers/wiki-lua.ts
```

Add temporarily:
```typescript
const raw = await fetchWikiLua();
console.log('revIds:', raw.revIds);
console.log('Module:Mods/data keys:', raw.modules['Module:Mods/data'] ? Object.keys(raw.modules['Module:Mods/data'] as object).slice(0, 5) : 'empty');
```

Expected: prints revision IDs and a few mod name keys.

- [ ] **Step 3: Remove smoke test, commit**

```bash
git add pipeline/src/fetchers/wiki-lua.ts
git commit -m "feat: add Wiki Lua fetcher via MediaWiki API"
```

---

## Task 6: Normalizers

**Files:**
- Create: `pipeline/src/normalizers/warframes.ts`
- Create: `pipeline/src/normalizers/mods.ts`
- Create: `pipeline/src/normalizers/arcanes.ts`
- Create: `pipeline/src/normalizers/weapons.ts`

The normalizers merge WFCD (primary source for most fields) with Public Export and Wiki data. WFCD is authoritative for base stats; Public Export fills in gaps; Wiki provides ability scaling flags.

- [ ] **Step 1: Write `pipeline/src/normalizers/warframes.ts`**

```typescript
import type Items from 'warframe-items';
import type { WarframeEntry, AbilityRef } from '../schema/index.js';

function normalizeAbility(ab: Items.Ability, slot: number): AbilityRef {
  const desc = ab.description?.toLowerCase() ?? '';
  return {
    name: ab.name ?? 'Unknown',
    slot,
    strengthScaling: desc.includes('ability strength') || desc.includes('power strength'),
    durationScaling: desc.includes('ability duration') || desc.includes('power duration'),
    rangeScaling: desc.includes('ability range') || desc.includes('power range'),
    efficiencyScaling: desc.includes('ability efficiency') || desc.includes('power efficiency'),
  };
}

export function normalizeWarframes(wfcdWarframes: Items.Warframe[]): WarframeEntry[] {
  return wfcdWarframes
    .filter(w => w.uniqueName && w.name)
    .map(w => ({
      uniqueName: w.uniqueName!,
      name: w.name!,
      baseStats: {
        health: w.health ?? 100,
        shield: w.shield ?? 100,
        armor: w.armor ?? 0,
        energy: w.energy ?? 100,
        sprint: w.sprint ?? 1.0,
      },
      polarities: w.polarities ?? [],
      aura: w.aura ?? null,
      abilities: (w.abilities ?? []).map((ab, i) => normalizeAbility(ab, i + 1)),
      passiveDescription: w.passiveDescription ?? '',
      masteryRank: w.masteryReq ?? 0,
    }));
}
```

- [ ] **Step 2: Write `pipeline/src/normalizers/mods.ts`**

The key work here is parsing the `levelStats` description strings into `ModEffect[]`. DE's descriptions follow a stable template: `"+X% Stat"` or `"+X Stat"`.

```typescript
import type Items from 'warframe-items';
import type { ModEntry, ModEffect, StackType } from '../schema/index.js';

const STAT_PATTERN = /([+-]?\d+(?:\.\d+)?)\s*%?\s*(.*)/;

// Map DE description fragments to normalized stat names
const STAT_MAP: Record<string, string> = {
  'ability strength': 'abilityStrength',
  'power strength': 'abilityStrength',
  'ability duration': 'abilityDuration',
  'power duration': 'abilityDuration',
  'ability range': 'abilityRange',
  'power range': 'abilityRange',
  'ability efficiency': 'abilityEfficiency',
  'power efficiency': 'abilityEfficiency',
  'health': 'health',
  'shield capacity': 'shield',
  'armor': 'armor',
  'energy max': 'energy',
  'sprint speed': 'sprint',
};

function resolveStatName(fragment: string): string {
  const lower = fragment.toLowerCase().trim();
  for (const [key, val] of Object.entries(STAT_MAP)) {
    if (lower.includes(key)) return val;
  }
  return lower.replace(/\s+/g, '_');
}

function parseEffects(levelStats: Items.LevelStats[] | undefined): ModEffect[] {
  if (!levelStats?.length) return [];
  // Use max rank stats (last entry)
  const maxStats = levelStats[levelStats.length - 1].stats ?? [];
  const firstStats = levelStats[0].stats ?? [];

  return maxStats
    .map((desc, i): ModEffect | null => {
      const match = desc.match(/([+-]?\d+(?:\.\d+)?)\s*%/);
      if (!match) return null;
      const maxVal = parseFloat(match[1]) / 100;
      const firstDesc = firstStats[i] ?? desc;
      const firstMatch = firstDesc.match(/([+-]?\d+(?:\.\d+)?)\s*%/);
      const firstVal = firstMatch ? parseFloat(firstMatch[1]) / 100 : maxVal;
      const rank0Val = Math.abs(firstVal);
      const rankMax = levelStats.length;
      const perRank = rankMax > 1 ? maxVal / rankMax : maxVal;

      return {
        stat: resolveStatName(desc.replace(/[+-]?\d+(?:\.\d+)?\s*%/, '')),
        stackType: 'additive_base' as StackType,
        valuePerRank: perRank,
      };
    })
    .filter((e): e is ModEffect => e !== null);
}

function resolveType(item: Items.Mod): string {
  const cat = item.category?.toLowerCase() ?? '';
  if (cat.includes('warframe')) return 'warframe';
  if (cat.includes('primary')) return 'primary';
  if (cat.includes('secondary')) return 'secondary';
  if (cat.includes('melee')) return 'melee';
  if (cat.includes('aura')) return 'aura';
  if (cat.includes('stance')) return 'stance';
  return 'misc';
}

export function normalizeMods(wfcdMods: Items.Mod[]): ModEntry[] {
  return wfcdMods
    .filter(m => m.uniqueName && m.name)
    .map(m => ({
      uniqueName: m.uniqueName!,
      name: m.name!,
      polarity: m.polarity ?? 'none',
      rarity: m.rarity ?? 'Common',
      maxRank: m.fusionLimit ?? 5,
      type: resolveType(m),
      modSet: m.set ?? null,
      tradable: m.tradable ?? false,
      effects: parseEffects(m.levelStats),
      rawDescription: m.description ?? '',
    }));
}
```

- [ ] **Step 3: Write `pipeline/src/normalizers/arcanes.ts`**

```typescript
import type Items from 'warframe-items';
import type { ArcaneEntry, ArcaneEffect } from '../schema/index.js';

const TRIGGER_PATTERNS: Array<[RegExp, string]> = [
  [/on\s+kill/i, 'on_kill'],
  [/on\s+headshot/i, 'on_headshot'],
  [/energy\s+pickup/i, 'on_energy_pickup'],
  [/shield\s+break/i, 'on_shield_break'],
  [/on\s+hit/i, 'on_hit'],
  [/on\s+cast/i, 'on_cast'],
  [/on\s+dodge/i, 'on_dodge'],
];

function extractTrigger(desc: string): string {
  for (const [pattern, name] of TRIGGER_PATTERNS) {
    if (pattern.test(desc)) return name;
  }
  return 'passive';
}

function extractMaxStacks(desc: string): number {
  const match = desc.match(/(?:up to|max(?:imum)?)\s+(\d+)\s+stack/i);
  return match ? parseInt(match[1], 10) : 1;
}

function parseArcaneEffects(levelStats: Items.LevelStats[] | undefined): ArcaneEffect[] {
  if (!levelStats?.length) return [];
  const maxStats = levelStats[levelStats.length - 1].stats ?? [];
  return maxStats.map(desc => {
    const match = desc.match(/([+-]?\d+(?:\.\d+)?)\s*%?/);
    const value = match ? parseFloat(match[1]) : 0;
    return {
      stat: desc.replace(/[+-]?\d+(?:\.\d+)?\s*%?\s*/, '').trim().toLowerCase().replace(/\s+/g, '_'),
      value,
      atMaxRank: true,
    };
  });
}

export function normalizeArcanes(wfcdArcanes: Items.Arcane[]): ArcaneEntry[] {
  return wfcdArcanes
    .filter(a => a.uniqueName && a.name)
    .map(a => {
      const desc = a.description ?? '';
      return {
        uniqueName: a.uniqueName!,
        name: a.name!,
        maxRank: a.fusionLimit ?? 5,
        maxStacks: extractMaxStacks(desc),
        trigger: extractTrigger(desc),
        effects: parseArcaneEffects(a.levelStats),
        rawDescription: desc,
      };
    });
}
```

- [ ] **Step 4: Write `pipeline/src/normalizers/weapons.ts`**

```typescript
import type Items from 'warframe-items';
import type { WeaponEntry, WeaponStats } from '../schema/index.js';

function normalizeWeaponStats(w: Items.Primary | Items.Secondary | Items.Melee): WeaponStats {
  const damageTypes: Record<string, number> = {};
  for (const [key, val] of Object.entries(w.damageTypes ?? {})) {
    if (typeof val === 'number' && val > 0) damageTypes[key] = val;
  }
  const totalDamage = Object.values(damageTypes).reduce((a, b) => a + b, 0);

  const stats: WeaponStats = {
    totalDamage,
    damageTypes,
    critChance: w.criticalChance ?? 0,
    critMultiplier: w.criticalMultiplier ?? 1,
    statusChance: w.procChance ?? 0,
    fireRate: (w as Items.Primary).fireRate ?? (w as Items.Melee).attackSpeed ?? 1,
    magazineSize: (w as Items.Primary).magazineSize ?? 0,
    reloadTime: (w as Items.Primary).reloadTime ?? 0,
    multishot: (w as Items.Primary).multishot ?? 1,
  };

  const melee = w as Items.Melee;
  if (melee.range != null) stats.range = melee.range;
  if (melee.attackSpeed != null) stats.attackSpeed = melee.attackSpeed;

  return stats;
}

function resolveWeaponType(item: Items.Primary | Items.Secondary | Items.Melee): string {
  return item.category ?? 'Unknown';
}

export function normalizeWeapons(
  primary: Items.Primary[],
  secondary: Items.Secondary[],
  melee: Items.Melee[]
): WeaponEntry[] {
  const all: Array<Items.Primary | Items.Secondary | Items.Melee> = [...primary, ...secondary, ...melee];
  return all
    .filter(w => w.uniqueName && w.name)
    .map(w => ({
      uniqueName: w.uniqueName!,
      name: w.name!,
      type: resolveWeaponType(w),
      baseStats: normalizeWeaponStats(w),
      disposition: w.disposition ?? 3,
      masteryRank: w.masteryReq ?? 0,
    }));
}
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/normalizers/
git commit -m "feat: add warframe/mod/arcane/weapon normalizers"
```

---

## Task 7: Pipeline CLI entry point + cache layer

**Files:**
- Create: `pipeline/src/index.ts`
- Create: `data/manifest.json`
- Create: `data/warframes.json`, `data/mods.json`, `data/arcanes.json`, `data/weapons.json`
- Create: `pipeline/cache/.gitkeep`

- [ ] **Step 1: Create data/ placeholder files**

`data/manifest.json`:
```json
{
  "lastUpdated": "",
  "sourceVersions": {
    "wfcd": "",
    "publicExport": "",
    "wiki": {}
  }
}
```

`data/warframes.json`, `data/mods.json`, `data/arcanes.json`, `data/weapons.json`: each `[]`

- [ ] **Step 2: Write `pipeline/src/index.ts`**

```typescript
import { writeFileSync, readFileSync, mkdirSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { fetchWfcd } from './fetchers/wfcd.js';
import { fetchPublicExport } from './fetchers/public-export.js';
import { fetchWikiLua } from './fetchers/wiki-lua.js';
import { normalizeWarframes } from './normalizers/warframes.js';
import { normalizeMods } from './normalizers/mods.js';
import { normalizeArcanes } from './normalizers/arcanes.js';
import { normalizeWeapons } from './normalizers/weapons.js';
import type { Manifest } from './schema/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '../../');
const DATA_DIR = resolve(ROOT, 'data');
const CACHE_DIR = resolve(__dirname, '../cache');

function readManifest(): Manifest {
  try {
    return JSON.parse(readFileSync(resolve(DATA_DIR, 'manifest.json'), 'utf8'));
  } catch {
    return { lastUpdated: '', sourceVersions: { wfcd: '', publicExport: '', wiki: {} } };
  }
}

function writeData<T>(filename: string, data: T[]) {
  writeFileSync(resolve(DATA_DIR, filename), JSON.stringify(data, null, 2));
  console.log(`  wrote ${data.length} entries → data/${filename}`);
}

function writeCache(filename: string, data: unknown) {
  if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
  writeFileSync(resolve(CACHE_DIR, filename), JSON.stringify(data, null, 2));
}

function readCache<T>(filename: string): T | null {
  const path = resolve(CACHE_DIR, filename);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, 'utf8'));
}

async function run(fresh: boolean) {
  console.log(`\nWarframe Planner — data pipeline (${fresh ? 'fresh' : 'incremental'})\n`);

  const manifest = readManifest();

  // Step 1: fetch sources (use cache if not fresh)
  console.log('Fetching WFCD...');
  let wfcd = fresh ? null : readCache('wfcd-raw.json');
  if (!wfcd) {
    wfcd = await fetchWfcd();
    writeCache('wfcd-raw.json', wfcd);
  }

  console.log('Fetching Public Export...');
  let publicExport = fresh ? null : readCache('public-export-raw.json');
  if (!publicExport) {
    publicExport = await fetchPublicExport();
    writeCache('public-export-raw.json', publicExport);
  }

  // Check if upstream changed (skip full wiki fetch if not)
  const exportHash = (publicExport as { indexHash: string }).indexHash;
  if (!fresh && exportHash === manifest.sourceVersions.publicExport) {
    console.log('No upstream changes detected. Use --fresh to force update.\n');
    return;
  }

  console.log('Fetching Wiki Lua modules...');
  let wikiLua = fresh ? null : readCache('wiki-lua-raw.json');
  if (!wikiLua) {
    wikiLua = await fetchWikiLua();
    writeCache('wiki-lua-raw.json', wikiLua);
  }

  // Step 2: normalize
  console.log('\nNormalizing...');
  const { warframes: rawFrames, mods: rawMods, arcanes: rawArcanes, primary, secondary, melee } = wfcd as Awaited<ReturnType<typeof fetchWfcd>>;

  writeData('warframes.json', normalizeWarframes(rawFrames));
  writeData('mods.json', normalizeMods(rawMods));
  writeData('arcanes.json', normalizeArcanes(rawArcanes));
  writeData('weapons.json', normalizeWeapons(primary, secondary, melee));

  // Step 3: update manifest
  const { revIds } = wikiLua as Awaited<ReturnType<typeof fetchWikiLua>>;
  const newManifest: Manifest = {
    lastUpdated: new Date().toISOString(),
    sourceVersions: {
      wfcd: process.env.npm_package_version ?? 'unknown',
      publicExport: exportHash,
      wiki: revIds as Record<string, number>,
    },
  };
  writeFileSync(resolve(DATA_DIR, 'manifest.json'), JSON.stringify(newManifest, null, 2));
  console.log('\nDone. manifest.json updated.\n');
}

const args = process.argv.slice(2);
if (args[0] === 'run') {
  run(args.includes('--fresh')).catch(err => {
    console.error(err);
    process.exit(1);
  });
}
```

- [ ] **Step 3: Create cache placeholder**

```bash
mkdir -p pipeline/cache && touch pipeline/cache/.gitkeep
```

- [ ] **Step 4: Run the pipeline**

```bash
cd pipeline && npx tsx src/index.ts run --fresh
```

Expected: prints fetching/normalizing steps, writes to `data/`, no errors.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/index.ts pipeline/cache/.gitkeep data/
git commit -m "feat: add pipeline CLI with cache layer, write normalized data/"
```

---

## Task 8: Python engine scaffold

**Files:**
- Create: `engine/pyproject.toml`
- Create: `engine/warframe_engine/__init__.py`
- Create: `engine/warframe_engine/loader.py`
- Create: `engine/interactions/README.md`
- Create: `engine/tests/__init__.py`
- Create: `engine/tests/test_loader.py`

- [ ] **Step 1: Write `engine/pyproject.toml`**

```toml
[project]
name = "warframe-engine"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write `engine/warframe_engine/__init__.py`**

```python
```
(empty — marks the package)

- [ ] **Step 3: Write `engine/warframe_engine/loader.py`**

```python
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"


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
    abilities: list[AbilityRef]
    passive_description: str
    mastery_rank: int


@dataclass
class ModEffect:
    stat: str
    stack_type: str
    value_per_rank: float


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
    effects: list[ModEffect]
    raw_description: str


def _load_json(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    return json.loads(path.read_text())


def load_warframes() -> list[WarframeEntry]:
    return [
        WarframeEntry(
            unique_name=w["uniqueName"],
            name=w["name"],
            base_stats=BaseStats(**w["baseStats"]),
            polarities=w["polarities"],
            aura=w["aura"],
            abilities=[
                AbilityRef(
                    name=a["name"],
                    slot=a["slot"],
                    strength_scaling=a["strengthScaling"],
                    duration_scaling=a["durationScaling"],
                    range_scaling=a["rangeScaling"],
                    efficiency_scaling=a["efficiencyScaling"],
                )
                for a in w["abilities"]
            ],
            passive_description=w["passiveDescription"],
            mastery_rank=w["masteryRank"],
        )
        for w in _load_json("warframes.json")
    ]


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
            effects=[ModEffect(**e) for e in m["effects"]],
            raw_description=m["rawDescription"],
        )
        for m in _load_json("mods.json")
    ]
```

- [ ] **Step 4: Write `engine/tests/__init__.py`**

```python
```
(empty)

- [ ] **Step 5: Write `engine/tests/test_loader.py`**

```python
from warframe_engine.loader import load_warframes, load_mods


def test_warframes_load():
    frames = load_warframes()
    assert len(frames) > 0, "Expected at least one warframe"
    frost = next((f for f in frames if f.name == "Frost"), None)
    assert frost is not None, "Frost not found"
    assert frost.base_stats.armor > 0
    assert len(frost.abilities) == 4


def test_mods_load():
    mods = load_mods()
    assert len(mods) > 0, "Expected at least one mod"
    vitality = next((m for m in mods if m.name == "Vitality"), None)
    assert vitality is not None, "Vitality not found"
    assert vitality.max_rank == 10
```

- [ ] **Step 6: Write `engine/interactions/README.md`**

```markdown
# Interactions

Hand-curated YAML files for conditional mechanics that cannot be derived from item data.

## Format (planned)

Each file covers one mechanic or conditional buff:

```yaml
name: shieldgate
description: Brief Respite + Augur set converts energy spend to shields
rules:
  - trigger: ability_cast
    condition: brief_respite_equipped
    effect:
      stat: shield
      value_per_energy: 1.0
  - trigger: shield_depleted
    gate_duration_seconds: 1.3
    short_gate_duration_seconds: 0.13
```

Files in this directory are the source of truth for the calc engine's conditional logic.
Each YAML key maps to a Python function in `warframe_engine/mechanics/`.
```

- [ ] **Step 7: Install deps and run tests**

```bash
cd engine && uv sync --extra dev && uv run pytest -v
```

Expected: 2 tests pass (requires pipeline to have been run at least once to populate data/).

- [ ] **Step 8: Commit**

```bash
git add engine/
git commit -m "feat: add Python engine scaffold with dataclass loader and tests"
```

---

## Task 9: GitHub Actions data pipeline workflow

**Files:**
- Create: `.github/workflows/data-pipeline.yml`

- [ ] **Step 1: Write `.github/workflows/data-pipeline.yml`**

```yaml
name: Data Pipeline

on:
  schedule:
    - cron: '0 0 * * *'   # midnight UTC daily
  workflow_dispatch:        # allow manual trigger from GitHub UI

permissions:
  contents: write           # needed to commit data/ back to repo

jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: pipeline/package-lock.json

      - name: Install pipeline deps
        run: npm ci
        working-directory: pipeline

      - name: Run pipeline (fresh)
        run: npx tsx src/index.ts run --fresh
        working-directory: pipeline

      - name: Check for data changes
        id: diff
        run: |
          git diff --quiet data/ && echo "changed=false" >> $GITHUB_OUTPUT || echo "changed=true" >> $GITHUB_OUTPUT

      - name: Commit updated data
        if: steps.diff.outputs.changed == 'true'
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git commit -m "chore: update data [$(date -u +%Y-%m-%d)]"
          git push
```

- [ ] **Step 2: Commit**

```bash
git add .github/
git commit -m "ci: add nightly data pipeline GitHub Actions workflow"
```

---

## Self-Review

**Spec coverage:**
- ✅ Monorepo with TS pipeline + Python engine
- ✅ WFCD fetcher
- ✅ Public Export fetcher (LZMA)
- ✅ Wiki Lua fetcher
- ✅ Normalizers for warframes, mods, arcanes, weapons
- ✅ Incremental (manifest hash check) + --fresh flag
- ✅ Cache layer in pipeline/cache/
- ✅ data/ JSON output committed to repo
- ✅ Python engine loader with dataclasses
- ✅ interactions/ directory with format README
- ✅ GitHub Actions nightly workflow
- ✅ Tests for Python loader

**Placeholder scan:** None found.

**Type consistency:** `WarframeEntry`, `ModEntry`, `ArcaneEntry`, `WeaponEntry`, `Manifest` defined in Task 2 and used consistently through Tasks 3-7. Python dataclasses in Task 8 mirror the TS schema field names (camelCase → snake_case).
