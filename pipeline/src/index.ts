import { writeFileSync, readFileSync, mkdirSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import Items from 'warframe-items';
import { createRequire } from 'node:module';
const _require = createRequire(import.meta.url);
// Resolve warframe-items location then read its package.json directly (avoids exports map restriction)
const _wfcdPkgPath = resolve(dirname(_require.resolve('warframe-items')), 'package.json');
const WFCD_VERSION: string = (JSON.parse(readFileSync(_wfcdPkgPath, 'utf8')) as { version: string }).version;

import { fetchWfcd } from './fetchers/wfcd.js';
import { fetchPublicExport } from './fetchers/public-export.js';
import { fetchWikiImages } from './fetchers/wiki-images.js';
import { fetchWikiLua, type WikiLuaRaw } from './fetchers/wiki-lua.js';
import { fetchWikiPages, type WikiPagesRaw } from './fetchers/wiki-pages.js';
import { normalizeWarframes } from './normalizers/warframes.js';
import { normalizeMods } from './normalizers/mods.js';
import { normalizeArcanes } from './normalizers/arcanes.js';
import { normalizeWeapons } from './normalizers/weapons.js';
import { normalizeHelmets } from './normalizers/helmets.js';
import { normalizeModSets } from './normalizers/mod-sets.js';
import { normalizeAbilityStats } from './normalizers/ability-stats.js';
import { normalizeShards } from './normalizers/shards.js';
import { buildAbilitiesData } from './normalizers/abilities.js';
import { normalizeSignatureWeapons } from './normalizers/signature-weapons.js';
import { normalizeWeaponPassives } from './normalizers/weapon-passives.js';
import type { Manifest } from './schema/index.js';
import type { LuaObj } from './lua/eval.js';

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

function writeData<T>(filename: string, data: T[] | object) {
  const content = JSON.stringify(data, null, 2);
  writeFileSync(resolve(DATA_DIR, filename), content);
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

  // ── WFCD (local npm, always fast) ─────────────────────────────────────────
  console.log('Loading WFCD...');
  const wfcd = fetchWfcd();
  // Load ALL items for mod-sets (needs Mod Set Mod items)
  const allItems = new Items({ category: ['All'] }) as unknown[];

  // ── Images ────────────────────────────────────────────────────────────────
  console.log('Resolving images...');
  type ImagesCache = { _wfcdVersion?: string } & Record<string, Record<string, string>>;
  let imagesCache = fresh ? null : readCache<ImagesCache>('images-raw.json');
  if (!imagesCache || Object.keys(imagesCache).length === 0 || imagesCache._wfcdVersion !== WFCD_VERSION) {
    const allItemRefs = [
      ...wfcd.warframes.map(i => ({ uniqueName: i.uniqueName, name: i.name, wikiaThumbnail: i.wikiaThumbnail })),
      ...wfcd.mods.map(i => ({ uniqueName: i.uniqueName, name: i.name, wikiaThumbnail: i.wikiaThumbnail })),
      ...wfcd.arcanes.map(i => ({ uniqueName: i.uniqueName, name: i.name, wikiaThumbnail: i.wikiaThumbnail })),
      ...wfcd.guns.map(i => ({ uniqueName: i.uniqueName, name: i.name, wikiaThumbnail: i.wikiaThumbnail })),
      ...wfcd.melee.map(i => ({ uniqueName: i.uniqueName, name: i.name, wikiaThumbnail: i.wikiaThumbnail })),
    ];
    const imageMap = await fetchWikiImages(allItemRefs);
    imagesCache = { _wfcdVersion: WFCD_VERSION, ...imageMap };
    writeCache('images-raw.json', imagesCache);
  }
  const { _wfcdVersion: _v, ...images } = imagesCache;
  writeData('images.json', images);
  const totalFiles = Object.values(images).reduce((n, m) => n + Object.keys(m).length, 0);
  console.log(`  resolved ${Object.keys(images).length} items, ${totalFiles} total image files`);

  // ── Public Export ─────────────────────────────────────────────────────────
  console.log('Fetching Public Export...');
  type PECache = Awaited<ReturnType<typeof fetchPublicExport>>;
  let publicExport = fresh ? null : readCache<PECache>('public-export-raw.json');
  if (!publicExport) {
    publicExport = await fetchPublicExport();
    writeCache('public-export-raw.json', publicExport);
  }

  if (!fresh && publicExport.indexHash === manifest.sourceVersions.publicExport) {
    console.log('No upstream changes detected. Use --fresh to force update.\n');
    return;
  }

  // ── Wiki Lua modules ──────────────────────────────────────────────────────
  let wikiLua: WikiLuaRaw = { modules: {}, revIds: {} };
  if (!skipWiki) {
    console.log('Fetching Wiki Lua modules...');
    const cachedWiki = fresh ? null : readCache<WikiLuaRaw>('wiki-lua-raw.json');
    if (cachedWiki?.modules && Object.keys(cachedWiki.modules).length > 0) {
      wikiLua = cachedWiki;
      console.log('  (using cache)');
    } else {
      wikiLua = await fetchWikiLua();
      writeCache('wiki-lua-raw.json', wikiLua);
    }
  } else {
    console.log('Skipping wiki (--skip-wiki).');
  }

  // ── Wiki article pages (Arcane Helmet + Archon Shard) ─────────────────────
  let wikiPages: WikiPagesRaw = { arcaneHelmet: '', archonShard: '', signatureWeapon: '', weaponPassives: '' };
  if (!skipWiki) {
    console.log('Fetching Wiki pages...');
    const cachedPages = fresh ? null : readCache<WikiPagesRaw>('wiki-pages-raw.json');
    if (cachedPages?.archonShard) {
      wikiPages = cachedPages;
      console.log('  (using cache)');
    } else {
      wikiPages = await fetchWikiPages();
      writeCache('wiki-pages-raw.json', wikiPages);
    }
  }

  // ── Normalize ─────────────────────────────────────────────────────────────
  console.log('\nNormalizing...');

  const exports = publicExport.exports as Record<string, { [key: string]: unknown[] }>;
  const exportCustoms = (exports['ExportCustoms_en.json']?.['ExportCustoms'] ?? []) as unknown[];

  const wikiModData = {
    warframes: wikiLua.modules['Module:Warframes/data'] as LuaObj | undefined,
    abilityStats: wikiLua.modules['Module:Ability/data/stats'] as LuaObj | undefined,
  };

  writeData('warframes.json', normalizeWarframes(wfcd.warframes, wikiModData));
  writeData('mods.json', normalizeMods(wfcd.mods));
  writeData('arcanes.json', normalizeArcanes(wfcd.arcanes));
  writeData('weapons.json', normalizeWeapons(wfcd.guns, wfcd.melee));
  writeData('helmets.json', normalizeHelmets(exportCustoms, wikiPages.arcaneHelmet));
  writeData('mod-sets.json', normalizeModSets(allItems));
  writeData('ability-stats.json',
    normalizeAbilityStats((wikiLua.modules['Module:Ability/data/stats'] ?? {}) as LuaObj),
  );
  writeData('shard-bonuses.json', normalizeShards(wikiPages.archonShard));
  writeData('signature-weapons.json', normalizeSignatureWeapons(wikiPages.signatureWeapon));
  writeData('weapon-passives.json', normalizeWeaponPassives(wikiPages.weaponPassives));

  const abilitiesData = buildAbilitiesData(
    (wikiLua.modules['Module:Ability/data'] ?? {}) as LuaObj,
  );
  writeFileSync(
    resolve(DATA_DIR, 'abilities.json'),
    JSON.stringify(abilitiesData, null, 2),
  );
  console.log(`  wrote abilities.json (${abilitiesData.subsumable.length} subsumable, ${Object.keys(abilitiesData.augmentToAbility).length} augments)`);

  // ── Manifest ──────────────────────────────────────────────────────────────
  const newManifest: Manifest = {
    lastUpdated: new Date().toISOString(),
    sourceVersions: {
      wfcd: WFCD_VERSION,
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
