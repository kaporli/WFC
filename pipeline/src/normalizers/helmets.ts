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
  const arcaneHelmets = (exportCustoms as RawCustom[]).filter(
    c => c.uniqueName?.includes('AltHelmet') && c.name?.startsWith('Arcane'),
  );

  return arcaneHelmets.map(h => {
    // Find the relevant wikitext block for this helmet by its sort key
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
}
