import type { WfcdWarframe, WfcdAbility } from '../schema/wfcd.js';
import type { WarframeEntry, AbilityRef } from '../schema/index.js';

function normalizeAbility(ab: WfcdAbility, slot: number): AbilityRef {
  const desc = ab.description?.toLowerCase() ?? '';
  return {
    name: ab.name,
    slot,
    strengthScaling: /ability strength|power strength/.test(desc),
    durationScaling: /ability duration|power duration/.test(desc),
    rangeScaling: /ability range|power range/.test(desc),
    efficiencyScaling: /ability efficiency|power efficiency/.test(desc),
  };
}

export function normalizeWarframes(wfcdWarframes: WfcdWarframe[]): WarframeEntry[] {
  return wfcdWarframes
    .filter(w => w.uniqueName && w.name && w.category === 'Warframes')
    .map(w => ({
      uniqueName: w.uniqueName,
      name: w.name,
      baseStats: {
        health: w.health ?? 100,
        shield: w.shield ?? 100,
        armor: w.armor ?? 0,
        energy: w.power ?? 100,   // warframe-items uses `power` for energy pool
        sprint: w.sprintSpeed ?? w.sprint ?? 1.0,
      },
      polarities: w.polarities ?? [],
      aura: w.aura ?? null,
      abilities: (w.abilities ?? []).map((ab, i) => normalizeAbility(ab, i + 1)),
      passiveDescription: w.passiveDescription ?? '',
      masteryRank: w.masteryReq ?? 0,
    }));
}
