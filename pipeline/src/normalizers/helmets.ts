import type { ArcaneHelmetEntry, ArcaneHelmetEffect } from '../schema/index.js';

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

  // Match percent values: [[Stat Name]] (<span ...>±X%</span>)
  const pctPattern = /\[\[([^\]]+)\]\][^\(]*\(<span[^>]+>([+-]?\d+(?:\.\d+)?)%<\/span>\)/g;
  let m: RegExpExecArray | null;
  while ((m = pctPattern.exec(wikitext)) !== null) {
    const value = parseFloat(m[2]) / 100;
    effects.push({ stat: resolveStatName(m[1]), value, isFlat: false });
  }

  // Match flat values: [[Stat Name]] (<span ...>±X</span>)  (no % sign)
  const flatPattern = /\[\[([^\]]+)\]\][^\(]*\(<span[^>]+>([+-]?\d+(?:\.\d+)?)<\/span>\)/g;
  while ((m = flatPattern.exec(wikitext)) !== null) {
    const raw = m[0];
    if (raw.includes('%')) continue; // already captured above
    const value = parseFloat(m[2]);
    effects.push({ stat: resolveStatName(m[1]), value, isFlat: true });
  }

  return effects;
}

// Build a map from sort-value → wikitext block from the page
function extractBlocks(wikitext: string): Map<string, string> {
  const blocks = new Map<string, string>();
  const splitPattern = /data-sort-value="([^"]+)"/g;
  let m: RegExpExecArray | null;
  const positions: Array<{ key: string; start: number }> = [];

  while ((m = splitPattern.exec(wikitext)) !== null) {
    positions.push({ key: m[1], start: m.index });
  }

  for (let i = 0; i < positions.length; i++) {
    const { key, start } = positions[i];
    const end = i + 1 < positions.length ? positions[i + 1].start : wikitext.length;
    blocks.set(key, wikitext.slice(start, end));
  }

  return blocks;
}

// Find the best matching sort-value block for a helmet name.
// The wiki sometimes omits words (e.g. "Arcane Gauss Helmet" for "Arcane Mag Gauss Helmet").
// Match by checking that every word in the sort-value is present in the helmet name.
function findBlock(blocks: Map<string, string>, helmetName: string): string | null {
  // Exact match first
  if (blocks.has(helmetName)) return blocks.get(helmetName)!;

  const nameLower = helmetName.toLowerCase();
  for (const [key, block] of blocks) {
    const keyWords = key.toLowerCase().split(/\s+/);
    if (keyWords.every(w => nameLower.includes(w))) {
      return block;
    }
  }
  return null;
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
  const arcaneHelmets = (exportCustoms as RawCustom[]).filter(
    c => (c.uniqueName?.includes('AltHelmet') || c.uniqueName?.includes('HelmetAlt'))
      && c.name?.startsWith('Arcane'),
  );

  const blocks = extractBlocks(arcaneHelmetWikitext);

  return arcaneHelmets.map(h => {
    const block = findBlock(blocks, h.name);
    const effects = block ? parseWikiTextEffects(block) : [];

    return {
      uniqueName: h.uniqueName,
      name: h.name,
      warframeName: extractWarframeName(h.description ?? ''),
      effects,
    };
  });
}
