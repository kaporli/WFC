import type { ShardBonus } from '../schema/index.js';

const SHARD_SECTIONS: Record<string, string> = {
  crimson: 'crimson_archon_shard_buffs',
  amber: 'amber_archon_shard_buffs',
  azure: 'azure_archon_shard_buffs',
  topaz: 'topaz_archon_shard_buffs',
  violet: 'violet_archon_shard_buffs',
  emerald: 'emerald_archon_shard_buffs',
};

const STAT_MAP: Array<[RegExp, string, boolean]> = [
  [/ability strength/i, 'abilityStrength', false],
  [/ability duration/i, 'abilityDuration', false],
  [/melee.*critical damage/i, 'meleeCritDamage', false],
  [/primary.*status chance/i, 'primaryStatusChance', false],
  [/secondary.*critical chance/i, 'secondaryCritChance', false],
  [/casting speed/i, 'castSpeed', false],
  [/parkour velocity/i, 'parkourVelocity', false],
  [/max.*health|\bhealth\b(?!.*regen)/i, 'health', true],
  [/shield capacity|\bshield\b/i, 'shield', true],
  [/energy max|\benergy\b(?!.*orb)/i, 'energy', true],
  [/\barmor\b/i, 'armor', true],
  [/health.*regen/i, 'healthRegen', true],
  [/health orb/i, 'healthOrbEffectiveness', false],
  [/energy orb/i, 'energyOrbEffectiveness', false],
];

function resolveShardStat(text: string): { stat: string; isFlat: boolean } | null {
  // Determine if this is a flat value (contains a bare number like "+150")
  // vs a percent value (contains "%")
  for (const [re, stat, isFlat] of STAT_MAP) {
    if (re.test(text)) {
      // Override isFlat detection: if it has % it's not flat
      const hasPercent = text.includes('%');
      const finalFlat = isFlat && !hasPercent;
      return { stat, isFlat: finalFlat };
    }
  }
  return null;
}

function isConditional(text: string): boolean {
  return /kill|killing|killed|status|affected by|gains\s+\d|stacking|reset|per enemy/i.test(text);
}

function extractNormalValue(text: string): number | null {
  // Format: "+X% (+Y%)" or "+X (+Y)" — normal value is X
  const pctMatch = text.match(/\+(\d+(?:\.\d+)?)\s*%?\s*\(/);
  if (pctMatch) {
    return text.includes('%') ? parseFloat(pctMatch[1]) / 100 : parseFloat(pctMatch[1]);
  }
  // "+X Stat" with no parens
  const directMatch = text.match(/\+(\d+(?:\.\d+)?)\s+/);
  if (directMatch) return parseFloat(directMatch[1]);
  return null;
}

export type ShardsOutput = Record<string, ShardBonus[]>;

export function normalizeShards(archonShardWikitext: string): ShardsOutput {
  const output: ShardsOutput = {};

  for (const [color, sectionId] of Object.entries(SHARD_SECTIONS)) {
    const sectionStart = archonShardWikitext.indexOf(`<section begin="${sectionId}" />`);
    const sectionEnd = archonShardWikitext.indexOf(`<section end="${sectionId}" />`);
    if (sectionStart === -1 || sectionEnd === -1) { output[color] = []; continue; }

    const section = archonShardWikitext.slice(sectionStart, sectionEnd);
    const bonuses: ShardBonus[] = [];

    const lines = section.split('\n').filter(l => {
      const t = l.trim();
      return t.startsWith('| +') || t.startsWith('| Gain') || t.startsWith('| Regenerate');
    });

    for (const line of lines) {
      const value = extractNormalValue(line);
      if (value === null || value === 0) continue;

      const resolved = resolveShardStat(line);
      if (!resolved) continue;

      bonuses.push({
        stat: resolved.stat,
        value,
        isFlat: resolved.isFlat,
        conditional: isConditional(line),
      });
    }

    output[color] = bonuses;
  }

  return output;
}
