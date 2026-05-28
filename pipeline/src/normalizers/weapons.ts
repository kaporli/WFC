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

  return stats;
}

export function normalizeWeapons(guns: WfcdWeapon[], melee: WfcdWeapon[]): WeaponEntry[] {
  return [...guns, ...melee]
    .filter(w => w.uniqueName && w.name)
    .map(w => ({
      uniqueName: w.uniqueName,
      name: w.name,
      type: w.category ?? 'Unknown',
      baseStats: normalizeWeaponStats(w),
      disposition: w.disposition ?? 3,
      masteryRank: w.masteryReq ?? 0,
    }));
}
