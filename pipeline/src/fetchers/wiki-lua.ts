import { evalLuaWithFallback, type LuaObj } from '../lua/eval.js';

const WIKI_API = 'https://wiki.warframe.com/api.php';

export const MODULES = [
  // ── Core warframe data ─────────────────────────────────────────────────────
  'Module:Mods/data',
  'Module:Warframes/data',
  'Module:Ability/data',
  'Module:Ability/data/stats',
  // ── Weapons ────────────────────────────────────────────────────────────────
  'Module:Weapons/data/primary',
  'Module:Weapons/data/secondary',
  'Module:Weapons/data/melee',
  'Module:Weapons/data/archwing',
  'Module:Weapons/data/companion',
  'Module:Weapons/data/railjack',
  'Module:Weapons/data/modular',
  'Module:Weapons/data/misc',
  // ── Companions & stances ───────────────────────────────────────────────────
  'Module:Companions/data',
  'Module:Stances/data',
  'Module:ScientiaStances/data',
  // ── Arcanes & upgrades ─────────────────────────────────────────────────────
  'Module:Arcane/data',
  'Module:Upgrades/data',
  // ── Game mechanics ─────────────────────────────────────────────────────────
  'Module:DamageTypes/data',
  // ── Farming & acquisition ──────────────────────────────────────────────────
  'Module:Resources/data',
  'Module:Void/data',
  'Module:Acquisition/data',
  'Module:Blueprints/data',
  // ── Content & activities ───────────────────────────────────────────────────
  'Module:Enemies/data',
  'Module:Syndicates/data',
  'Module:Research/data',
  'Module:Vendors/data',
  'Module:Decrees/data',
  'Module:Conservation/data',
  'Module:Avionics/data',
  'Module:Codex/data',
  'Module:Decorations/data',
] as const;

export type ModuleName = (typeof MODULES)[number];

async function fetchModuleSource(title: string): Promise<{ content: string; revId: number } | null> {
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
  if (page.missing || !page.revisions?.length) {
    process.stdout.write(` (missing)\n`);
    return null;
  }
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
    try {
      const result = await fetchModuleSource(mod);
      if (!result) continue;
      const { content, revId } = result;
      if (!content.trim()) {
        process.stdout.write(` (empty)\n`);
        continue;
      }
      const evaluated = evalLuaWithFallback(content);
      modules[mod] = (evaluated as LuaObj) ?? {};
      revIds[mod] = revId;
      process.stdout.write(` done (${(content.length / 1024).toFixed(0)}KB)\n`);
    } catch (err) {
      process.stdout.write(` ERROR: ${(err as Error).message}\n`);
      // Continue with remaining modules — don't crash the whole pipeline
    }
  }

  return { modules, revIds };
}
