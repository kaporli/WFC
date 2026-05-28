import type { LuaObj, LuaVal } from '../lua/eval.js';
import type { AbilitiesData } from '../schema/index.js';

export interface AbilityScalingFlags {
  strengthScaling: boolean;
  durationScaling: boolean;
  rangeScaling: boolean;
  efficiencyScaling: boolean;
}

export type AbilityScalingMap = Map<string, AbilityScalingFlags>;

// Build map: ability uniqueName → scaling flags
// Module:Ability/data/stats has entries like:
//   ["/Lotus/Powersuits/.../AbilityFoo"] = {
//     { Label = "Energy Cost: ...", Modifier = "AVATAR_ABILITY_EFFICIENCY", Values = { Val1 = 75 } },
//     { Label = "Bonus: ...", Modifier = "AVATAR_ABILITY_STRENGTH", Values = { Val1 = 50 } },
//   }
export function buildAbilityScalingMap(abilityStatsModule: LuaObj): AbilityScalingMap {
  const map = new Map<string, AbilityScalingFlags>();

  for (const [uniqueName, entry] of Object.entries(abilityStatsModule)) {
    if (!Array.isArray(entry)) continue;

    const flags: AbilityScalingFlags = {
      strengthScaling: false,
      durationScaling: false,
      rangeScaling: false,
      efficiencyScaling: false,
    };

    for (const block of entry as LuaVal[]) {
      if (typeof block !== 'object' || Array.isArray(block) || !block) continue;
      const modifier = (block as LuaObj)['Modifier'];
      if (typeof modifier !== 'string') continue;
      if (modifier === 'AVATAR_ABILITY_STRENGTH')   flags.strengthScaling = true;
      if (modifier === 'AVATAR_ABILITY_DURATION')   flags.durationScaling = true;
      if (modifier === 'AVATAR_ABILITY_RANGE')      flags.rangeScaling = true;
      if (modifier === 'AVATAR_ABILITY_EFFICIENCY') flags.efficiencyScaling = true;
    }

    map.set(uniqueName, flags);
  }

  return map;
}

// Build AbilitiesData from Module:Ability/data
// The module returns { Archived: {...}, Ability: { ["Roar"] = { ... }, ... } }
// Each entry in the Ability sub-table looks like:
//   ["Roar"] = {
//     InternalName = "/Lotus/Powersuits/Rhino/Abilities/RhinoRoarAbility",
//     Augments = { "Piercing Roar" },
//     Subsumable = true,
//     ...
//   }
export function buildAbilitiesData(abilityDataModule: LuaObj): AbilitiesData {
  const subsumable: string[] = [];
  const augmentToAbility: Record<string, string> = {};

  // The module is structured as { Ability: { ... }, Archived: { ... } }
  // We want the Ability sub-table; fall back to iterating top-level if absent.
  const abilityTable = (abilityDataModule['Ability'] as LuaObj | undefined) ?? abilityDataModule;

  for (const [, entry] of Object.entries(abilityTable)) {
    if (typeof entry !== 'object' || Array.isArray(entry) || !entry) continue;
    const e = entry as LuaObj;

    const uniqueName = e['InternalName'];
    if (typeof uniqueName !== 'string') continue;

    if (e['Subsumable'] === true) subsumable.push(uniqueName);

    const augments = e['Augments'];
    if (Array.isArray(augments)) {
      for (const aug of augments) {
        if (typeof aug === 'string') augmentToAbility[aug] = uniqueName;
      }
    }
  }

  return { subsumable, augmentToAbility };
}
