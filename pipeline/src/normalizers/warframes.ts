import type { WfcdWarframe, WfcdAbility } from '../schema/wfcd.js';
import type { WarframeEntry, AbilityRef } from '../schema/index.js';
import type { LuaObj } from '../lua/eval.js';
import { buildAbilityScalingMap, type AbilityScalingMap } from './abilities.js';

function getWikiEntry(wikiWarframes: LuaObj | undefined, wfName: string): LuaObj | null {
  if (!wikiWarframes) return null;
  if (wfName in wikiWarframes) return wikiWarframes[wfName] as LuaObj;
  const lower = wfName.toLowerCase();
  for (const [k, v] of Object.entries(wikiWarframes)) {
    if (k.toLowerCase() === lower) return v as LuaObj;
  }
  return null;
}

function parseAuraSlots(wikiEntry: LuaObj | null): number {
  if (!wikiEntry) return 1;
  const aura = wikiEntry['AuraPolarity'];
  if (Array.isArray(aura)) return aura.length;
  return 1;
}

function normalizeAbility(
  ab: WfcdAbility,
  slot: number,
  scalingMap: AbilityScalingMap,
): AbilityRef {
  // Try to match by uniqueName (internal path)
  const flags = scalingMap.get(ab.uniqueName) ?? {
    strengthScaling: false, durationScaling: false,
    rangeScaling: false, efficiencyScaling: false,
  };
  return { name: ab.name, slot, ...flags };
}

export function normalizeWarframes(
  wfcdWarframes: WfcdWarframe[],
  wikiModulesData: { warframes?: LuaObj; abilityStats?: LuaObj } = {},
): WarframeEntry[] {
  const scalingMap: AbilityScalingMap = wikiModulesData.abilityStats
    ? buildAbilityScalingMap(wikiModulesData.abilityStats)
    : new Map();

  // Module:Warframes/data has shape { Archwings: {...}, Warframes: {...}, ... }
  const wikiWarframes = wikiModulesData.warframes
    ? ((wikiModulesData.warframes['Warframes'] as LuaObj) ?? wikiModulesData.warframes)
    : null;

  return wfcdWarframes
    .filter(w => w.uniqueName && w.name && w.category === 'Warframes')
    .map(w => {
      const wikiEntry = wikiWarframes ? getWikiEntry(wikiWarframes, w.name) : null;
      const initialEnergy = wikiEntry && typeof wikiEntry['InitialEnergy'] === 'number'
        ? (wikiEntry['InitialEnergy'] as number)
        : Math.floor((w.power ?? 100) / 4);
      const exilusPolarity = wikiEntry && typeof wikiEntry['ExilusPolarity'] === 'string'
        ? (wikiEntry['ExilusPolarity'] as string)
        : null;

      return {
        uniqueName: w.uniqueName,
        name: w.name,
        baseStats: {
          health: w.health ?? 100,
          shield: w.shield ?? 100,
          armor: w.armor ?? 0,
          energy: w.power ?? 100,
          sprint: w.sprintSpeed ?? w.sprint ?? 1.0,
        },
        polarities: w.polarities ?? [],
        aura: w.aura ?? null,
        auraSlots: parseAuraSlots(wikiEntry),
        abilities: (w.abilities ?? []).map((ab, i) => normalizeAbility(ab, i + 1, scalingMap)),
        passiveDescription: w.passiveDescription ?? '',
        masteryRank: w.masteryReq ?? 0,
        initialEnergy,
        exilusPolarity,
      };
    });
}
