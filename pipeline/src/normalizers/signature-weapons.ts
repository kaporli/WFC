export interface SignatureWeaponEntry {
  warframeName: string;   // e.g. "Sevagoth"
  weaponName: string;     // e.g. "Epitaph"
  bonus: string;          // e.g. "+20% headshot damage."
}

function cleanText(raw: string): string {
  return raw
    .replace(/\[\[([^\]|]+\|)?([^\]]+)\]\]/g, '$2')           // [[Link|Text]] → Text
    .replace(/\{\{(?:M|A|W|Weapon|WF|Mod)\|([^|}]+)[^}]*\}\}/gi, '$1') // {{M|Name|...}} → Name
    .replace(/'''/g, '')                                        // bold markers
    .replace(/<br\s*\/?>/gi, ' ')                               // <br> → space
    .replace(/rowspan="?\d+"?\s*\|/g, '')                       // rowspan="N" |
    .replace(/colspan="?\d+"?\s*\|/g, '')
    .replace(/style="[^"]*"\s*\|/g, '')
    .replace(/\{\{[^}]+\}\}/g, '')                             // remaining templates
    .replace(/\s+/g, ' ')
    .trim();
}

export function normalizeSignatureWeapons(wikitext: string): SignatureWeaponEntry[] {
  const rows = wikitext.split(/\n\|\-\n/);
  const results: SignatureWeaponEntry[] = [];
  let currentWarframe: string | null = null;

  for (const row of rows) {
    // Update current warframe if this row has a WF/Companion template
    const wfMatch = row.match(/\{\{(?:WF|Companion)\|([^|}]+)/);
    if (wfMatch) currentWarframe = wfMatch[1].trim();

    const weaponMatches = [...row.matchAll(/\{\{Weapon\|([^|}]+)/g)];
    if (!weaponMatches.length || !currentWarframe) continue;

    // Bonus text: pipe-separated cells that aren't template calls or "not implemented"
    const bonusLines: string[] = [];
    for (const line of row.split('\n')) {
      const t = line.trim();
      if (!t.startsWith('|')) continue;
      const cleaned = cleanText(t.slice(1));
      if (!cleaned || cleaned.length < 5) continue;
      if (/not implemented/i.test(cleaned)) continue;
      // Skip lines that are just warframe/weapon references
      if (/^\{\{(WF|Weapon|Companion)/i.test(t)) continue;
      bonusLines.push(cleaned);
    }

    const bonus = bonusLines.join(' ').trim();
    if (!bonus || /not implemented/i.test(bonus)) continue;

    for (const wm of weaponMatches) {
      results.push({
        warframeName: currentWarframe,
        weaponName: wm[1].trim(),
        bonus,
      });
    }
  }

  return results;
}
