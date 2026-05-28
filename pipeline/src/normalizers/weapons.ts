import type { WfcdWeapon } from '../schema/wfcd.js';
import type { WeaponEntry, WeaponStats } from '../schema/index.js';

function normalizeWeaponStats(w: WfcdWeapon): WeaponStats {
  const raw = w.damageTypes ?? {};
  const damageTypes: Record<string, number> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (typeof v === 'number' && v > 0) damageTypes[k] = v;
  }
  const totalDamage = w.totalDamage ?? Object.values(damageTypes).reduce((a, b) => a + b, 0);

  const stats: WeaponStats = {
    totalDamage,
    damageTypes,
    critChance: w.criticalChance ?? 0,
    critMultiplier: w.criticalMultiplier ?? 1,
    statusChance: w.statusChance ?? w.procChance ?? 0,
    fireRate: w.fireRate ?? w.attackSpeed ?? 1,
    magazineSize: w.magazineSize ?? 0,
    reloadTime: w.reloadTime ?? 0,
    multishot: w.multishot ?? 1,
  };

  if (w.range != null) stats.range = w.range;
  if (w.attackSpeed != null) stats.attackSpeed = w.attackSpeed;
  if (w.comboDuration != null) stats.comboDuration = w.comboDuration;
  if (w.heavyAttackDamage != null) stats.heavyAttackDamage = w.heavyAttackDamage;

  return stats;
}

function resolveSlot(category: string): number {
  const c = category.toLowerCase();
  if (c.includes('arch-gun')) return 5;
  if (c.includes('primary') || c.includes('railjack')) return 0;
  if (c.includes('secondary')) return 1;
  if (c.includes('melee') || c.includes('arch-melee')) return 2;
  return 0;
}

export function normalizeWeapons(guns: WfcdWeapon[], melee: WfcdWeapon[]): WeaponEntry[] {
  return [...guns, ...melee]
    .filter(w => w.uniqueName && w.name)
    .map(w => ({
      uniqueName: w.uniqueName,
      name: w.name,
      type: w.category ?? 'Unknown',
      slot: resolveSlot(w.category ?? ''),
      baseStats: normalizeWeaponStats(w),
      disposition: w.disposition ?? 3,
      masteryRank: w.masteryReq ?? 0,
    }));
}
