import type { WfcdArcane, WfcdLevelStat } from '../schema/wfcd.js';
import type { ArcaneEntry, ArcaneEffect } from '../schema/index.js';

const TRIGGER_PATTERNS: Array<[RegExp, string]> = [
  [/on\s+kill/i, 'on_kill'],
  [/on\s+headshot/i, 'on_headshot'],
  [/energy\s+pickup/i, 'on_energy_pickup'],
  [/shield\s+break/i, 'on_shield_break'],
  [/on\s+hit/i, 'on_hit'],
  [/on\s+cast/i, 'on_cast'],
  [/on\s+dodge/i, 'on_dodge'],
  [/on\s+melee/i, 'on_melee'],
];

function extractTrigger(desc: string): string {
  for (const [re, name] of TRIGGER_PATTERNS) {
    if (re.test(desc)) return name;
  }
  return 'passive';
}

function extractMaxStacks(desc: string): number {
  const m = desc.match(/(?:up to|max(?:imum)?)\s+(\d+)\s+stack/i);
  return m ? parseInt(m[1], 10) : 1;
}

function parseArcaneEffects(levelStats: WfcdLevelStat[] | undefined): ArcaneEffect[] {
  if (!levelStats?.length) return [];
  const maxStats = levelStats[levelStats.length - 1].stats ?? [];

  return maxStats.map((desc: string): ArcaneEffect => {
    const match = desc.match(/([+-]?\d+(?:\.\d+)?)\s*%?/);
    const value = match ? parseFloat(match[1]) : 0;
    const statFrag = desc.replace(/[+-]?\d+(?:\.\d+)?\s*%?\s*/, '').trim();
    return {
      stat: statFrag.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, ''),
      value,
      atMaxRank: true,
    };
  });
}

export function normalizeArcanes(wfcdArcanes: WfcdArcane[]): ArcaneEntry[] {
  return wfcdArcanes
    .filter(a => a.uniqueName && a.name)
    .map(a => {
      const desc = a.description ?? '';
      return {
        uniqueName: a.uniqueName,
        name: a.name,
        // Arcane rank count = levelStats.length; ranks are 0-indexed so maxRank = length - 1
        maxRank: (a.levelStats?.length ?? 1) - 1,
        maxStacks: extractMaxStacks(desc),
        trigger: extractTrigger(desc),
        effects: parseArcaneEffects(a.levelStats),
        rawDescription: desc,
      };
    });
}
