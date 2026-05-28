// Minimal structural types for the fields we read from warframe-items.
// warframe-items doesn't export its internal interfaces, so we define what we need.

export interface WfcdAbility {
  uniqueName: string;
  name: string;
  description: string;
  imageName: string;
}

export interface WfcdLevelStat {
  stats: string[];
}

export interface WfcdWarframe {
  uniqueName: string;
  name: string;
  category: string;
  health: number;
  shield: number;
  armor: number;
  power: number;        // energy pool
  sprintSpeed?: number;
  sprint?: number;
  polarities?: string[];
  aura?: string;
  abilities?: WfcdAbility[];
  passiveDescription?: string;
  masteryReq?: number;
  tradable: boolean;
}

export interface WfcdMod {
  uniqueName: string;
  name: string;
  category: string;
  polarity?: string;
  rarity?: string;
  fusionLimit?: number;
  type?: string;
  modSet?: string;
  levelStats?: WfcdLevelStat[];
  description?: string;
  tradable: boolean;
}

export interface WfcdArcane {
  uniqueName: string;
  name: string;
  category: string;
  levelStats?: WfcdLevelStat[];
  description?: string;
  tradable: boolean;
}

export interface WfcdWeapon {
  uniqueName: string;
  name: string;
  category: string;
  totalDamage?: number;
  damageTypes?: Record<string, number>;
  criticalChance?: number;
  criticalMultiplier?: number;
  statusChance?: number;
  procChance?: number;
  fireRate?: number;
  attackSpeed?: number;
  magazineSize?: number;
  reloadTime?: number;
  multishot?: number;
  range?: number;
  disposition?: number;
  masteryReq?: number;
  tradable: boolean;
}
