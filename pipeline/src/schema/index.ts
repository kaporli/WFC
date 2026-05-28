export interface BaseStats {
  health: number;
  shield: number;
  armor: number;
  energy: number;
  sprint: number;
}

export interface AbilityRef {
  name: string;
  slot: number;
  strengthScaling: boolean;
  durationScaling: boolean;
  rangeScaling: boolean;
  efficiencyScaling: boolean;
}

export interface WarframeEntry {
  uniqueName: string;
  name: string;
  baseStats: BaseStats;
  polarities: string[];
  aura: string | null;
  abilities: AbilityRef[];
  passiveDescription: string;
  masteryRank: number;
}

export type StackType = 'additive_base' | 'additive_stacking' | 'multiplicative';

export interface ModEffect {
  stat: string;
  stackType: StackType;
  valuePerRank: number;
}

export interface ModEntry {
  uniqueName: string;
  name: string;
  polarity: string;
  rarity: string;
  maxRank: number;
  type: string;
  modSet: string | null;
  tradable: boolean;
  effects: ModEffect[];
  rawDescription: string;
}

export interface ArcaneEffect {
  stat: string;
  value: number;
  atMaxRank: boolean;
}

export interface ArcaneEntry {
  uniqueName: string;
  name: string;
  maxRank: number;
  maxStacks: number;
  trigger: string;
  effects: ArcaneEffect[];
  rawDescription: string;
}

export interface WeaponStats {
  totalDamage: number;
  damageTypes: Record<string, number>;
  critChance: number;
  critMultiplier: number;
  statusChance: number;
  fireRate: number;
  magazineSize: number;
  reloadTime: number;
  multishot: number;
  range?: number;
  attackSpeed?: number;
}

export interface WeaponEntry {
  uniqueName: string;
  name: string;
  type: string;
  baseStats: WeaponStats;
  disposition: number;
  masteryRank: number;
}

export interface Manifest {
  lastUpdated: string;
  sourceVersions: {
    wfcd: string;
    publicExport: string;
    wiki: Record<string, number>;
  };
}
