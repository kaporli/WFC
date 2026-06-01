from __future__ import annotations
import re
from warframe_chatbot.config import RETRIEVAL_K
from warframe_chatbot.store import WikiStore, SearchResult


_default_store: WikiStore | None = None


def _get_store() -> WikiStore:
    global _default_store
    if _default_store is None:
        _default_store = WikiStore()
    return _default_store


# ── Query expansion ────────────────────────────────────────────────────────────
# For broad "what sources of X" questions, a single embedding query misses many
# relevant items because the stat names don't lexically overlap with the query.
# We generate 2-4 related sub-queries and merge the result sets.

_EXPANSIONS: list[tuple[re.Pattern, list[str]]] = [
    # companion / summon
    (re.compile(r'companion|summon|pet|sentinel|kavat|kubrow|moa', re.I), [
        "arcane enhancement companion summoned allies damage",
        "companion damage mod",
        "increases damage of companions summoned allies",
        "summon damage arcane",
        "Hunter set companion",
        "companion healing recovery",
        "arcane companion damage",
        "companion buff warframe ability",
    ]),
    # shieldgate / shield
    (re.compile(r'shield.?gate|shield.?gat|energy.*shield|augur', re.I), [
        "energy to shield conversion",
        "Brief Respite Augur",
        "shield gate invulnerability duration",
    ]),
    # armor strip
    (re.compile(r'armor.?strip|strip.*armor|full.*armor|terrify|avalanche|corrosive projection', re.I), [
        "armor reduction ability",
        "armor strip percentage",
        "corrosive projection aura",
    ]),
    # crit / damage
    (re.compile(r'crit|damage.*source|buff.*damage|damage.*buff', re.I), [
        "critical chance multiplier mod",
        "damage boost warframe ability",
        "Roar Rhino damage buff",
    ]),
    # energy / efficiency
    (re.compile(r'energy\b|efficiency|flow|primed flow', re.I), [
        "energy max mod",
        "ability efficiency streamline",
        "energy restore arcane",
    ]),
    # farming / drop location
    (re.compile(r'farm|where.*get|drop.*location|how.*get|obtain', re.I), [
        "drop location resource",
        "mission reward relic",
        "farming guide",
    ]),
]


def _expand_queries(query: str) -> list[str]:
    """Generate additional search queries based on the topic of the question."""
    extras: list[str] = []
    for pattern, expansions in _EXPANSIONS:
        if pattern.search(query):
            extras.extend(expansions)
    return extras[:8]  # cap to avoid too many API calls


def search(query: str, *, store: WikiStore | None = None, k: int = RETRIEVAL_K) -> list[SearchResult]:
    """Return top-k semantically relevant chunks, using query expansion for broad questions."""
    s = store or _get_store()

    # Primary query
    seen: dict[str, SearchResult] = {r.page_title: r for r in s.query(query, k=k)}

    # Expanded sub-queries — merge, keeping best score per page
    for sub in _expand_queries(query):
        for r in s.query(sub, k=k // 2):
            if r.page_title not in seen or r.score > seen[r.page_title].score:
                seen[r.page_title] = r

    # Filter low-relevance noise
    # 0.45 works well for all-mpnet-base-v2 (768-dim scores lower than MiniLM)
    MIN_SCORE = 0.45
    relevant = [r for r in seen.values() if r.score >= MIN_SCORE]
    if not relevant:
        relevant = sorted(seen.values(), key=lambda r: r.score, reverse=True)[:k]

    # Deduplicate: wiki article and data chunk for the same item both end up in
    # `seen` under different keys ("[data:mod] X" vs "X"). Keep higher-scoring one.
    _DATA_PREFIXES = (
        "[data:mod] ", "[data:arcane] ", "[data:warframe] ", "[data:weapon] ",
        "[data:mod_set] ", "[data:helmet] ", "[data:signature] ",
        "[data:weapon_passive] ", "[data:ability_stat] ",
    )
    canonical: dict[str, SearchResult] = {}
    for r in relevant:
        base = r.page_title
        for prefix in _DATA_PREFIXES:
            if base.startswith(prefix):
                base = base[len(prefix):]
                break
        if base not in canonical or r.score > canonical[base].score:
            canonical[base] = r

    return sorted(canonical.values(), key=lambda r: r.score, reverse=True)
