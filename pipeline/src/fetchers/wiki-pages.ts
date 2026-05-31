import { existsSync, readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
// chatbot/raw/ is populated by `wf-crawl` in Job 1 of the unified pipeline
const CHATBOT_RAW_DIR = resolve(__dirname, '../../../../chatbot/raw');
const WIKI_API = 'https://wiki.warframe.com/api.php';

/**
 * Try to read a wiki article page from the chatbot's raw/ cache first.
 * Falls back to a live API fetch if the file doesn't exist.
 * This avoids double-fetching pages that `wf-crawl` already downloaded.
 */
async function fetchPageWikitext(pageName: string): Promise<string> {
  // Check raw/ cache (populated by Python wf-crawl in Job 1)
  const slug = pageName.replace(/\//g, '_').replace(/\s+/g, '_').slice(0, 80);
  const cachePath = resolve(CHATBOT_RAW_DIR, `${slug}.json`);
  if (existsSync(cachePath)) {
    try {
      const cached = JSON.parse(readFileSync(cachePath, 'utf8')) as { wikitext: string };
      if (cached.wikitext) {
        process.stdout.write(' (from raw cache)');
        return cached.wikitext;
      }
    } catch {
      // fall through to API fetch
    }
  }

  // Fall back to live API fetch
  const params = new URLSearchParams({
    action: 'parse', page: pageName, prop: 'wikitext', format: 'json',
  });
  const res = await fetch(`${WIKI_API}?${params}`, {
    headers: { 'User-Agent': 'warframe-planner/0.1 (github.com/warframe-planner)' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching page ${pageName}`);
  const json = await res.json() as { parse?: { wikitext?: { '*'?: string } }; error?: { info: string } };
  if (json.error) throw new Error(`Wiki API error: ${json.error.info}`);
  return json.parse?.wikitext?.['*'] ?? '';
}

export interface WikiPagesRaw {
  arcaneHelmet: string;
  archonShard: string;
  signatureWeapon: string;
  weaponPassives: string;
}

export async function fetchWikiPages(): Promise<WikiPagesRaw> {
  process.stdout.write('  fetching Arcane Helmet page...');
  const arcaneHelmet = await fetchPageWikitext('Arcane Helmet');
  process.stdout.write(` ${(arcaneHelmet.length / 1024).toFixed(0)}KB\n`);

  process.stdout.write('  fetching Archon Shard page...');
  const archonShard = await fetchPageWikitext('Archon Shard');
  process.stdout.write(` ${(archonShard.length / 1024).toFixed(0)}KB\n`);

  process.stdout.write('  fetching Signature Weapon page...');
  const signatureWeapon = await fetchPageWikitext('Signature Weapon');
  process.stdout.write(` ${(signatureWeapon.length / 1024).toFixed(0)}KB\n`);

  process.stdout.write('  fetching Weapons/Passives page...');
  const weaponPassives = await fetchPageWikitext('Weapons/Passives');
  process.stdout.write(` ${(weaponPassives.length / 1024).toFixed(0)}KB\n`);

  return { arcaneHelmet, archonShard, signatureWeapon, weaponPassives };
}
