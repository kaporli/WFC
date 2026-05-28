import type { WfcdMod, WfcdLevelStat } from '../schema/wfcd.js';
import type { ModEntry, ModEffect, StackType } from '../schema/index.js';

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

function parseEffects(levelStats: WfcdLevelStat[] | undefined): ModEffect[] {
  if (!levelStats?.length) return [];

  const maxStats = levelStats[levelStats.length - 1].stats ?? [];
  const rankCount = levelStats.length;

  return maxStats
    .map((desc: string): ModEffect | null => {
      const match = desc.match(/([+-]?\d+(?:\.\d+)?)\s*%/);
      if (!match) return null;

      const maxVal = parseFloat(match[1]) / 100;
      const perRank = rankCount > 1 ? maxVal / rankCount : maxVal;
      const statFrag = desc.replace(/[+-]?\d+(?:\.\d+)?\s*%\s*/, '');

      return {
        stat: resolveStatName(statFrag),
        stackType: 'additive_base' as StackType,
        valuePerRank: perRank,
      };
    })
    .filter((e): e is ModEffect => e !== null);
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
      effects: parseEffects(m.levelStats),
      rawDescription: m.description ?? '',
    }));
}
