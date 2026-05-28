import type { SetBonusEntry, SetBonusEffect } from '../schema/index.js';

interface WfcdSetMod {
  uniqueName: string;
  numUpgradesInSet?: number;
  stats?: string[];
  type?: string;
}

const STAT_MAP: Array<[RegExp, string, boolean]> = [
  // [pattern, statName, isFlat]
  [/energy spent.*converted to shields/i, 'energyToShieldOnCast', false],
  [/heavy attack.*teleport/i, 'heavyAttackTeleport', false],
  [/heavy attack.*reduces.*accuracy/i, 'heavyKillArmorStrip', false],
  [/combo count/i, 'comboCritChance', false],
  [/critical chance/i, 'critChance', false],
];

function parseSetBonusStat(text: string): { stat: string; isFlat: boolean } | null {
  for (const [re, stat, isFlat] of STAT_MAP) {
    if (re.test(text)) return { stat, isFlat };
  }
  return null;
}

function parseSetBonusValue(text: string): number {
  const pct = text.match(/(\d+(?:\.\d+)?)\s*%/);
  if (pct) return parseFloat(pct[1]) / 100;
  const num = text.match(/(\d+(?:\.\d+)?)/);
  if (num) return parseFloat(num[1]);
  return 0;
}

export function normalizeModSets(allItems: unknown[]): SetBonusEntry[] {
  const setMods = (allItems as WfcdSetMod[]).filter(
    i => i.type === 'Mod Set Mod' && i.stats?.length,
  );

  return setMods
    .map(s => {
      const bonusByPieceCount: SetBonusEffect[] = (s.stats ?? [])
        .map((statText, idx): SetBonusEffect | null => {
          const pieces = idx + 1;
          const parsed = parseSetBonusStat(statText);
          const value = parseSetBonusValue(statText);
          if (!parsed || value === 0) return null;
          return { pieces, stat: parsed.stat, value, isFlat: parsed.isFlat };
        })
        .filter((e): e is SetBonusEffect => e !== null);

      return {
        uniqueName: s.uniqueName,
        numPiecesInSet: s.numUpgradesInSet ?? bonusByPieceCount.length,
        bonusByPieceCount,
      };
    })
    .filter(s => s.bonusByPieceCount.length > 0);
}
