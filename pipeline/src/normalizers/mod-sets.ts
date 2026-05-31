import type { SetBonusEntry, SetBonusEffect } from '../schema/index.js';

interface WfcdSetMod {
  uniqueName: string;
  numUpgradesInSet?: number;
  stats?: string[];
  type?: string;
}

const STAT_MAP: Array<[RegExp, string, boolean]> = [
  // [pattern, normalised stat name, isFlat]

  // Augur — 40%/80%/.../240% Energy spent on abilities converted to Shields
  [/energy spent.*converted to shields/i, 'energyToShieldOnCast', false],

  // Gladiator — X% Melee Critical Chance per Combo Multiplier
  [/melee.*critical chance.*combo|critical chance.*per combo/i, 'meleeCritPerComboMult', false],

  // Vigilante — X% chance to enhance Critical Hits from Primary Weapons
  [/enhance.*critical.*primary|chance.*enhance.*critical/i, 'primaryCritEnhanceChance', false],

  // Hunter — +X% Companion Damage on enemies affected by Slash
  [/companion.*damage.*slash/i, 'companionSlashDamage', false],

  // Synth — Holstering weapons reload X% of Magazine/s
  [/holstering.*reload/i, 'holsterReloadRate', false],

  // Boreal — Reduces damage by +X% when Airborne
  [/reduces damage.*airborne/i, 'airborneReducedDamageTaken', false],

  // Nira — Increase damage from Slam Attacks by +X%
  [/damage from slam|slam attacks/i, 'slamDamage', false],

  // Raptor — +X% chance to become immune to Knockdown when airborne
  [/knockdown.*airborne/i, 'airborneKnockdownImmunity', false],

  // Spider — Wall Latch +X% Damage Reduction
  [/wall latch.*damage reduction/i, 'wallLatchDamageReduction', false],

  // Ashen — Heavy Attack kill reduces Enemy Accuracy by X%
  [/enemy accuracy/i, 'enemyAccuracyReduction', false],

  // Amar — Teleport range on heavy attack (value = metres, isFlat = true)
  [/teleport.*heavy attack/i, 'heavyAttackTeleportRange', true],
];

function parseSetBonusStat(text: string): { stat: string; isFlat: boolean } | null {
  for (const [re, stat, isFlat] of STAT_MAP) {
    if (re.test(text)) return { stat, isFlat };
  }
  return null;
}

function parseSetBonusValue(text: string): number {
  // Strip formatting tags before matching
  const clean = text.replace(/<[^>]+>/g, '');
  const pct = clean.match(/(\d+(?:\.\d+)?)\s*%/);
  if (pct) return parseFloat(pct[1]) / 100;
  const num = clean.match(/(\d+(?:\.\d+)?)/);
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
