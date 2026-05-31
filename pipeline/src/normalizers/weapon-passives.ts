export interface WeaponPassiveEntry {
  weaponName: string;
  passives: string[];   // each entry is one passive bullet point, with [Trigger] prefix preserved
}

function cleanPassiveText(raw: string): string {
  return raw
    .replace(/'''/g, '')                                        // bold
    .replace(/''/g, '')                                         // italic
    .replace(/\[\[([^\]|]+\|)?([^\]]+)\]\]/g, '$2')            // [[Link|Text]] → Text
    .replace(/\{\{D\|([^}]+)\}\}/g, '$1')                      // {{D|Toxin}} → Toxin
    .replace(/\{\{M\|([^}]+)\}\}/g, '$1')                      // {{M|Mod}} → Mod
    .replace(/\{\{WF\|([^}]+)\}\}/g, '$1')                     // {{WF|Frame}} → Frame
    .replace(/\{\{Weapon\|([^}]+)\}\}/g, '$1')                 // {{Weapon|X}} → X
    .replace(/\{\{[^}]+\}\}/g, '')                             // other templates
    .replace(/<[^>]+>/g, '')                                    // HTML tags
    .replace(/\s+/g, ' ')
    .trim();
}

export function normalizeWeaponPassives(wikitext: string): WeaponPassiveEntry[] {
  const results: WeaponPassiveEntry[] = [];
  const rows = wikitext.split(/\n\|\-\n/);

  for (const row of rows) {
    const weaponMatch = row.match(/\{\{Weapon\|([^|}]+)/);
    if (!weaponMatch) continue;
    const weaponName = weaponMatch[1].trim();

    // Extract bullet-point lines
    const bullets = [...row.matchAll(/^\*\s*(.+)$/gm)].map(m => m[1]);
    if (!bullets.length) continue;

    const passives = bullets
      .map(b => cleanPassiveText(b))
      .filter(b => b.length > 5);

    if (passives.length > 0) {
      results.push({ weaponName, passives });
    }
  }

  // Deduplicate by weapon name (keep first occurrence — earlier in page = more specific)
  const seen = new Set<string>();
  return results.filter(e => {
    if (seen.has(e.weaponName)) return false;
    seen.add(e.weaponName);
    return true;
  });
}
