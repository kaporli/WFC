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
  signatureWeapon: string;
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

  return { arcaneHelmet, archonShard, signatureWeapon };
}
