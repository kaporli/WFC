import { writeFileSync, readFileSync, mkdirSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { fetchWfcd } from './fetchers/wfcd.js';
import { fetchPublicExport } from './fetchers/public-export.js';
import { fetchWikiLua, type WikiLuaRaw } from './fetchers/wiki-lua.js';
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
    return JSON.parse(readFileSync(resolve(DATA_DIR, 'manifest.json'), 'utf8')) as Manifest;
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
  return JSON.parse(readFileSync(path, 'utf8')) as T;
}

async function run(fresh: boolean, skipWiki: boolean) {
  console.log(`\nWarframe Planner — data pipeline (${fresh ? 'fresh' : 'incremental'}${skipWiki ? ', --skip-wiki' : ''})\n`);

  const manifest = readManifest();

  // WFCD is a local npm package — always fast, no network call
  console.log('Loading WFCD...');
  const wfcd = fetchWfcd();

  // Public Export — network fetch, cached between runs
  console.log('Fetching Public Export...');
  type PECache = Awaited<ReturnType<typeof fetchPublicExport>>;
  let publicExport = fresh ? null : readCache<PECache>('public-export-raw.json');
  if (!publicExport) {
    publicExport = await fetchPublicExport();
    writeCache('public-export-raw.json', publicExport);
  }

  // Skip remaining if upstream unchanged
  if (!fresh && publicExport.indexHash === manifest.sourceVersions.publicExport) {
    console.log('No upstream changes detected. Use --fresh to force update.\n');
    return;
  }

  // Wiki Lua — optional; stores raw Lua source to cache, not parsed inline
  let wikiRevIds: Record<string, number> = manifest.sourceVersions.wiki;
  if (!skipWiki) {
    console.log('Fetching Wiki Lua modules (raw source)...');
    const cachedWiki = fresh ? null : readCache<WikiLuaRaw>('wiki-lua-raw.json');
    if (cachedWiki) {
      wikiRevIds = cachedWiki.revIds as Record<string, number>;
      console.log('  (using cache)');
    } else {
      const wikiLua = await fetchWikiLua();
      writeCache('wiki-lua-raw.json', wikiLua);
      wikiRevIds = wikiLua.revIds as Record<string, number>;
    }
  } else {
    console.log('Skipping wiki (--skip-wiki).');
  }

  // Normalize and write data/
  console.log('\nNormalizing...');
  writeData('warframes.json', normalizeWarframes(wfcd.warframes));
  writeData('mods.json', normalizeMods(wfcd.mods));
  writeData('arcanes.json', normalizeArcanes(wfcd.arcanes));
  writeData('weapons.json', normalizeWeapons(wfcd.guns, wfcd.melee));

  const newManifest: Manifest = {
    lastUpdated: new Date().toISOString(),
    sourceVersions: {
      wfcd: '1.1269.x',
      publicExport: publicExport.indexHash,
      wiki: wikiRevIds,
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
