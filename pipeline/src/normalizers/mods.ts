import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { WfcdMod, WfcdLevelStat } from '../schema/wfcd.js';
import type { ModEntry, ModEffect, StackType, EffectTarget } from '../schema/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const STAT_TARGETS_PATH = resolve(__dirname, '../data/stat-targets.json');

function loadStatTargets(): Record<string, EffectTarget> {
  try {
    return JSON.parse(readFileSync(STAT_TARGETS_PATH, 'utf8')) as Record<string, EffectTarget>;
  } catch {
    return {};
  }
}

const STAT_TARGETS = loadStatTargets();

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

function resolveTarget(fragment: string): EffectTarget {
  const lower = fragment.toLowerCase().trim();
  for (const [key, target] of Object.entries(STAT_TARGETS)) {
    if (lower.includes(key)) return target as EffectTarget;
  }
  return 'self';
}

function parseEffects(levelStats: WfcdLevelStat[] | undefined): ModEffect[] {
  if (!levelStats?.length) return [];

  const effectCount = levelStats[0].stats?.length ?? 0;
  const results: ModEffect[] = [];

  for (let effIdx = 0; effIdx < effectCount; effIdx++) {
    const levelValues: number[] = [];
    let stat = '';
    let target: EffectTarget = 'self';
    let hasValue = false;

    for (let rankIdx = 0; rankIdx < levelStats.length; rankIdx++) {
      // Strip formatting tags (e.g. <DT_FREEZE_COLOR>, <LINE_SEPARATOR>)
      const raw = (levelStats[rankIdx].stats?.[effIdx] ?? '').replace(/<[^>]+>/g, '');
      const match = raw.match(/([+-]?\d+(?:\.\d+)?)\s*%/);
      if (match) {
        const val = parseFloat(match[1]) / 100;
        levelValues.push(val);
        if (rankIdx === 0 && !hasValue) {
          hasValue = true;
          const frag = raw.replace(/[+-]?\d+(?:\.\d+)?\s*%\s*/, '');
          stat = resolveStatName(frag);
          target = resolveTarget(frag);
        }
      } else {
        levelValues.push(0);
      }
    }

    if (stat && levelValues.some(v => v !== 0)) {
      results.push({ stat, stackType: 'additive_base' as StackType, levelValues, target });
    }
  }

  return results;
}

function parsePassives(levelStats: WfcdLevelStat[] | undefined): string[] {
  if (!levelStats?.length) return [];
  // Use max rank stats — split each stat block by newlines/LINE_SEPARATOR
  const maxStats = levelStats[levelStats.length - 1].stats ?? [];
  const passives: string[] = [];

  for (const block of maxStats) {
    const lines = block
      .replace(/<LINE_SEPARATOR>/gi, '\n')
      .replace(/<[^>]+>/g, '')
      .replace(/\\n/g, '\n')
      .split('\n')
      .map(l => l.trim())
      .filter(l => l.length > 4);

    for (const line of lines) {
      // Skip lines that are numeric stat changes (%, or leading +/- number)
      if (/[+-]?\d+(?:\.\d+)?\s*%/.test(line)) continue;
      if (/^[+-]\d/.test(line)) continue;
      // Skip multiplier lines like "x0.20 Max Shield Capacity"
      if (/^x\d/.test(line)) continue;
      passives.push(line);
    }
  }

  // Deduplicate and strip remaining noise
  return [...new Set(passives)];
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
      isAugment: m.isAugment ?? false,
      compatName: m.compatName ?? null,
      setMultipliers: m.modSetValues ?? [],
      effects: parseEffects(m.levelStats),
      passives: parsePassives(m.levelStats),
      rawDescription: m.description ?? '',
    }));
}
