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
  auraSlots: number;
  abilities: AbilityRef[];
  passiveDescription: string;
  masteryRank: number;
  initialEnergy: number;
  exilusPolarity: string | null;
}

export type StackType = 'additive_base' | 'additive_stacking' | 'multiplicative';
export type EffectTarget = 'self' | 'warframe' | 'primary' | 'secondary' | 'melee' | 'archgun' | 'companion';

export interface ModEffect {
  stat: string;
  stackType: StackType;
  levelValues: number[];
  target: EffectTarget;
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
  isAugment: boolean;
  compatName: string | null;
  setMultipliers: number[];
  effects: ModEffect[];
  passives: string[];        // non-numeric passive descriptions from levelStats for UI display
  rawDescription: string;
}

export interface ArcaneEffect {
  stat: string;
  levelValues: number[];
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
  comboDuration?: number;
  heavyAttackDamage?: number;
}

export interface WeaponEntry {
  uniqueName: string;
  name: string;
  type: string;
  slot: number;
  baseStats: WeaponStats;
  disposition: number;
  masteryRank: number;
}

export interface ArcaneHelmetEffect {
  stat: string;
  value: number;
  isFlat: boolean;
}

export interface ArcaneHelmetEntry {
  uniqueName: string;
  name: string;
  warframeName: string;
  effects: ArcaneHelmetEffect[];
}

export interface SetBonusEffect {
  pieces: number;
  stat: string;         // 'mechanic' for effects with no parseable numeric stat
  value: number;        // 0 for mechanic-only effects
  isFlat: boolean;
  rawText: string;      // original description from WFCD — always present for UI display
}

export interface SetBonusEntry {
  uniqueName: string;
  numPiecesInSet: number;
  bonusByPieceCount: SetBonusEffect[];
}

export interface AbilityStatBlock {
  label: string;
  modifier: string;
  baseValue: number;
  isPercent: boolean;
}

export interface AbilityStatsEntry {
  uniqueName: string;
  stats: AbilityStatBlock[];
}

export interface ShardBonus {
  stat: string;
  value: number;
  isFlat: boolean;
  conditional: boolean;
}

export interface AbilitiesData {
  subsumable: string[];
  augmentToAbility: Record<string, string>;
}

export interface SignatureWeaponEntry {
  warframeName: string;
  weaponName: string;
  bonus: string;
}

export interface Manifest {
  lastUpdated: string;
  sourceVersions: {
    wfcd: string;
    publicExport: string;
    wiki: Record<string, number>;
    wikiPages: Record<string, string>;
  };
}
