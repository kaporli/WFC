import type { LuaObj, LuaVal } from '../lua/eval.js';
import type { AbilityStatsEntry, AbilityStatBlock } from '../schema/index.js';

export function normalizeAbilityStats(abilityStatsModule: LuaObj): AbilityStatsEntry[] {
  const entries: AbilityStatsEntry[] = [];

  for (const [uniqueName, statBlocks] of Object.entries(abilityStatsModule)) {
    if (!Array.isArray(statBlocks)) continue;

    const stats: AbilityStatBlock[] = [];

    for (const block of statBlocks as LuaVal[]) {
      if (typeof block !== 'object' || Array.isArray(block) || !block) continue;
      const b = block as LuaObj;
      const label = b['Label'];
      const modifier = b['Modifier'];
      const values = b['Values'];

      if (typeof label !== 'string' || typeof modifier !== 'string') continue;

      let baseValue = 0;
      if (typeof values === 'object' && !Array.isArray(values) && values) {
        const v = (values as LuaObj)['Val1'];
        if (typeof v === 'number') baseValue = v;
      }

      const isPercent = label.includes('%');
      const cleanLabel = label
        .replace(/\|val\d+\|%?/g, '')
        .replace(/[:\s]+$/g, '')
        .trim();

      if (isPercent) baseValue = baseValue / 100;

      stats.push({ label: cleanLabel, modifier: String(modifier), baseValue, isPercent });
    }

    if (stats.length > 0) entries.push({ uniqueName, stats });
  }

  return entries;
}
