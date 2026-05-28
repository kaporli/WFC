const WIKI_API = 'https://wiki.warframe.com/api.php';

export const MODULES = [
  'Module:Mods/data',
  'Module:Warframes/data',
  'Module:Ability/data',
] as const;

export type ModuleName = (typeof MODULES)[number];

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
  const res = await fetch(`${WIKI_API}?${params}`, {
    headers: { 'User-Agent': 'warframe-planner/0.1 (data pipeline; github.com/warframe-planner)' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${title}`);
  const json = await res.json() as {
    query: {
      pages: Array<{
        missing?: boolean;
        revisions?: Array<{ revid: number; slots: { main: { content: string } } }>;
      }>;
    };
  };
  const page = json.query.pages[0];
  if (page.missing || !page.revisions?.length) throw new Error(`Wiki module not found: ${title}`);
  const rev = page.revisions[0];
  return { content: rev.slots.main.content, revId: rev.revid };
}

export interface WikiLuaRaw {
  // Raw Lua source per module — stored to cache for offline/future parsing.
  // Parsing happens later via a dedicated Lua interpreter; not done inline.
  sources: Partial<Record<ModuleName, string>>;
  revIds: Partial<Record<ModuleName, number>>;
}

export async function fetchWikiLua(): Promise<WikiLuaRaw> {
  const sources: Partial<Record<ModuleName, string>> = {};
  const revIds: Partial<Record<ModuleName, number>> = {};

  for (const mod of MODULES) {
    process.stdout.write(`  fetching ${mod}...`);
    const { content, revId } = await fetchModuleSource(mod);
    sources[mod] = content;
    revIds[mod] = revId;
    process.stdout.write(` ${(content.length / 1024).toFixed(0)}KB\n`);
  }

  return { sources, revIds };
}
