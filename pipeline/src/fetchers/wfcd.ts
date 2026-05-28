import Items from 'warframe-items';
import type { WfcdWarframe, WfcdMod, WfcdArcane, WfcdWeapon } from '../schema/wfcd.js';

export interface WfcdRaw {
  warframes: WfcdWarframe[];
  mods: WfcdMod[];
  arcanes: WfcdArcane[];
  guns: WfcdWeapon[];
  melee: WfcdWeapon[];
}

export function fetchWfcd(): WfcdRaw {
  const all = new Items({ category: ['Warframes', 'Mods', 'Arcanes', 'Primary', 'Secondary', 'Melee'] });

  return {
    warframes: all.filter(i => i.category === 'Warframes') as unknown as WfcdWarframe[],
    mods: all.filter(i => i.category === 'Mods') as unknown as WfcdMod[],
    arcanes: all.filter(i => i.category === 'Arcanes') as unknown as WfcdArcane[],
    guns: all.filter(i => i.category === 'Primary' || i.category === 'Secondary') as unknown as WfcdWeapon[],
    melee: all.filter(i => i.category === 'Melee') as unknown as WfcdWeapon[],
  };
}
