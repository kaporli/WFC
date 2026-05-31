"""
data_indexer.py — converts data/*.json (build planner output) into
searchable text chunks and upserts them into the ChromaDB store.

Each entry becomes a human-readable chunk so the chatbot can answer
precise numeric questions: "what does Vitality do at rank 5?",
"what's Frost's base armor?", "what are Avalanche's stats?".
"""
from __future__ import annotations
import json
from pathlib import Path
from warframe_chatbot.chunker import Chunk
from warframe_chatbot.store import WikiStore

DATA_DIR = Path(__file__).parent.parent.parent / "data"
_WIKI_BASE = "https://wiki.warframe.com/w"


def _url(name: str) -> str:
    return f"{_WIKI_BASE}/{name.replace(' ', '_')}"


# ── Warframes ─────────────────────────────────────────────────────────────────

def _warframe_chunk(w: dict, idx: int) -> Chunk:
    b = w.get("baseStats", {})
    abilities = w.get("abilities", [])
    scaling = [
        a["name"] for a in abilities
        if a.get("strengthScaling") or a.get("durationScaling") or a.get("rangeScaling")
    ]
    lines = [
        f"{w['name']} (Warframe)",
        f"Base stats: {b.get('health',0):.0f} HP, {b.get('shield',0):.0f} Shield, "
        f"{b.get('armor',0):.0f} Armor, {b.get('energy',0):.0f} Energy, "
        f"{b.get('sprint',0):.2f} Sprint",
        f"Aura polarity: {w.get('aura') or 'none'} | Aura slots: {w.get('auraSlots', 1)}",
        f"Initial energy: {w.get('initialEnergy', 0):.0f}",
        f"Mastery rank: {w.get('masteryRank', 0)}",
        f"Abilities: {', '.join(a['name'] for a in abilities)}",
    ]
    if scaling:
        lines.append(f"Strength/scaling abilities: {', '.join(scaling)}")
    passive = w.get("passiveDescription", "")
    if passive and len(passive) < 200:
        lines.append(f"Passive: {passive}")
    return Chunk(
        page_title=w["name"],
        section="Warframe Stats",
        text="\n".join(lines),
        url=_url(w["name"]),
        revid=0,
        chunk_index=idx,
    )


# ── Mods ──────────────────────────────────────────────────────────────────────

def _mod_chunk(m: dict, idx: int) -> Chunk:
    effects = m.get("effects", [])
    effect_lines = []
    for e in effects:
        if e.get("target", "self") not in ("self", "warframe"):
            target = f" → {e['target']}"
        else:
            target = ""
        lvls = e.get("levelValues", [])
        if lvls:
            lo, hi = lvls[0], lvls[-1]
            pct = "%" if abs(hi) <= 10 else ""
            effect_lines.append(
                f"{e['stat']}{target}: {lo*100:.0f}{pct} to {hi*100:.0f}{pct} (rank 0-{len(lvls)-1})"
                if pct else
                f"{e['stat']}{target}: {lo:.0f} to {hi:.0f} (rank 0-{len(lvls)-1})"
            )
    lines = [
        f"{m['name']} (Mod — {m.get('type','?')})",
        f"Polarity: {m.get('polarity','?')} | Rarity: {m.get('rarity','?')} | "
        f"Max rank: {m.get('maxRank',0)}",
    ]
    if m.get("isAugment") and m.get("compatName"):
        lines.append(f"Augment for: {m['compatName']}")
    if m.get("modSet"):
        lines.append(f"Set: {m['modSet'].split('/')[-1].replace('SetMod', '')}")
    if effect_lines:
        lines.append("Effects: " + "; ".join(effect_lines))
    passives = m.get("passives", [])
    for p in passives[:2]:
        lines.append(f"Passive: {p}")
    return Chunk(
        page_title=m["name"],
        section="Mod",
        text="\n".join(lines),
        url=_url(m["name"]),
        revid=0,
        chunk_index=idx,
    )


# ── Weapons ───────────────────────────────────────────────────────────────────

def _weapon_chunk(w: dict, idx: int) -> Chunk:
    b = w.get("baseStats", {})
    slot_names = {0: "Primary", 1: "Secondary", 2: "Melee", 5: "Arch-Gun"}
    slot = slot_names.get(w.get("slot", 0), "Unknown")
    lines = [
        f"{w['name']} ({slot} Weapon)",
        f"Crit: {b.get('critChance',0)*100:.0f}% × {b.get('critMultiplier',1):.1f} | "
        f"Status: {b.get('statusChance',0)*100:.0f}% | "
        f"Damage: {b.get('totalDamage',0):.0f}",
        f"Fire rate: {b.get('fireRate',0):.1f} | "
        f"Magazine: {b.get('magazineSize',0)} | "
        f"Reload: {b.get('reloadTime',0):.1f}s",
        f"Disposition: {w.get('disposition',0)} | Mastery: {w.get('masteryRank',0)}",
    ]
    if b.get("comboDuration"):
        lines.append(f"Combo duration: {b['comboDuration']:.0f}s")
    dmg = b.get("damageTypes", {})
    if dmg:
        dmg_str = ", ".join(f"{k}: {v:.0f}" for k, v in list(dmg.items())[:4])
        lines.append(f"Damage types: {dmg_str}")
    return Chunk(
        page_title=w["name"],
        section=f"{slot} Weapon",
        text="\n".join(lines),
        url=_url(w["name"]),
        revid=0,
        chunk_index=idx,
    )


# ── Arcanes ───────────────────────────────────────────────────────────────────

def _arcane_chunk(a: dict, idx: int) -> Chunk:
    effects = a.get("effects", [])
    effect_lines = []
    for e in effects:
        lvls = e.get("levelValues", [])
        if lvls:
            effect_lines.append(f"{e['stat']}: {lvls[0]:.0f} to {lvls[-1]:.0f} (rank 0-{len(lvls)-1})")
    lines = [
        f"{a['name']} (Arcane)",
        f"Trigger: {a.get('trigger','?')} | Max rank: {a.get('maxRank',0)} | "
        f"Max stacks: {a.get('maxStacks',1)}",
    ]
    if effect_lines:
        lines.append("Effects: " + "; ".join(effect_lines))
    return Chunk(
        page_title=a["name"],
        section="Arcane",
        text="\n".join(lines),
        url=_url(a["name"]),
        revid=0,
        chunk_index=idx,
    )


# ── Ability stats ─────────────────────────────────────────────────────────────

def _ability_stats_chunk(e: dict, idx: int) -> Chunk:
    uid = e.get("uniqueName", "")
    name = uid.split("/")[-1].replace("Ability", "").replace("AbilityAbility", "")
    stats = e.get("stats", [])
    lines = [f"Ability: {name}", f"Internal: {uid}"]
    for s in stats:
        mod = s.get("modifier", "")
        label = s.get("label", "")
        val = s.get("baseValue", 0)
        pct = "%" if s.get("isPercent") else ""
        lines.append(f"  {label}: {val*100 if pct else val:.0f}{pct} (scales with {mod})")
    return Chunk(
        page_title=name,
        section="Ability Stats",
        text="\n".join(lines),
        url=_url(name),
        revid=0,
        chunk_index=idx,
    )


# ── Helmets ───────────────────────────────────────────────────────────────────

def _helmet_chunk(h: dict, idx: int) -> Chunk:
    effects = h.get("effects", [])
    eff_strs = [
        f"{e['stat']}: {e['value']*100:+.0f}%" if not e.get("isFlat")
        else f"{e['stat']}: {e['value']:+.0f} (flat)"
        for e in effects
    ]
    return Chunk(
        page_title=h["name"],
        section="Arcane Helmet",
        text=(
            f"{h['name']} (Arcane Helmet for {h.get('warframeName','?')})\n"
            + ("Effects: " + ", ".join(eff_strs) if eff_strs else "No parsed effects")
        ),
        url=_url(h["name"]),
        revid=0,
        chunk_index=idx,
    )


# ── Signature weapons ─────────────────────────────────────────────────────────

def _signature_chunk(s: dict, idx: int) -> Chunk:
    return Chunk(
        page_title=f"{s['warframeName']} + {s['weaponName']}",
        section="Signature Weapon",
        text=(
            f"Signature weapon synergy: {s['warframeName']} + {s['weaponName']}\n"
            f"Bonus: {s['bonus']}"
        ),
        url=_url(s["weaponName"]),
        revid=0,
        chunk_index=idx,
    )


# ── Set bonuses ───────────────────────────────────────────────────────────────

def _mod_set_chunk(s: dict, idx: int) -> Chunk:
    name = s["uniqueName"].split("/")[-1].replace("SetMod", " Set")
    bonuses = s.get("bonusByPieceCount", [])
    lines = [f"{name} ({s.get('numPiecesInSet',0)} pieces)"]
    for b in bonuses:
        lines.append(f"  {b['pieces']} piece(s): {b.get('rawText', b.get('stat','?'))}")
    return Chunk(
        page_title=name,
        section="Set Bonus",
        text="\n".join(lines),
        url=_url(name),
        revid=0,
        chunk_index=idx,
    )


# ── Weapon passives ───────────────────────────────────────────────────────────

def _weapon_passive_chunk(w: dict, idx: int) -> Chunk:
    passives = w.get("passives", [])
    return Chunk(
        page_title=w["weaponName"],
        section="Weapon Passive",
        text=(
            f"{w['weaponName']} (Weapon Passive)\n"
            + "\n".join(f"  - {p}" for p in passives)
        ),
        url=_url(w["weaponName"]),
        revid=0,
        chunk_index=idx,
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

_CONVERTERS = {
    "warframes.json":         (_warframe_chunk,       "warframe"),
    "mods.json":              (_mod_chunk,             "mod"),
    "arcanes.json":           (_arcane_chunk,          "arcane"),
    "weapons.json":           (_weapon_chunk,          "weapon"),
    "ability-stats.json":     (_ability_stats_chunk,   "ability_stat"),
    "helmets.json":           (_helmet_chunk,          "helmet"),
    "signature-weapons.json": (_signature_chunk,       "signature"),
    "mod-sets.json":          (_mod_set_chunk,         "mod_set"),
    "weapon-passives.json":   (_weapon_passive_chunk,  "weapon_passive"),
}


def index_data_files(store: WikiStore, *, data_dir: Path | None = None) -> int:
    """Convert all data/*.json files to chunks and upsert into the store."""
    src = data_dir or DATA_DIR
    total = 0
    for filename, (converter, prefix) in _CONVERTERS.items():
        path = src / filename
        if not path.exists():
            continue
        entries = json.loads(path.read_text())
        if not isinstance(entries, list):
            continue
        chunks = []
        for i, entry in enumerate(entries):
            try:
                chunk = converter(entry, i)
                # Prefix the ID so data chunks don't collide with wiki article chunks
                chunk.page_title = f"[data:{prefix}] {chunk.page_title}"
                chunks.append(chunk)
            except Exception:
                pass  # skip malformed entries
        if chunks:
            store.upsert(chunks)
            total += len(chunks)
            print(f"  indexed {len(chunks)} {prefix} entries from {filename}")
    return total
