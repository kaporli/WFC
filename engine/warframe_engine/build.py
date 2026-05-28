from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warframe_engine.calculator import DataCache


@dataclass
class EquippedMod:
    unique_name: str
    rank: int  # 0 = unranked


@dataclass
class EquippedArcane:
    unique_name: str
    rank: int


@dataclass
class ArchonShard:
    color: str    # 'crimson' | 'azure' | 'amber' | 'topaz' | 'violet' | 'emerald'
    stat: str     # e.g. 'abilityStrength', 'health'
    tauforged: bool


@dataclass
class Build:
    warframe_name: str
    mods: list[EquippedMod] = field(default_factory=list)
    arcanes: list[EquippedArcane] = field(default_factory=list)
    shards: list[ArchonShard] = field(default_factory=list)
    exilus: EquippedMod | None = None
    auras: list[EquippedMod] = field(default_factory=list)
    helmet: str | None = None
    helminth_ability: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Build:
        return cls(
            warframe_name=d['warframe_name'],
            mods=[EquippedMod(**m) for m in d.get('mods', [])],
            arcanes=[EquippedArcane(**a) for a in d.get('arcanes', [])],
            shards=[ArchonShard(**s) for s in d.get('shards', [])],
            exilus=EquippedMod(**d['exilus']) if d.get('exilus') else None,
            auras=[EquippedMod(**a) for a in d.get('auras', [])],
            helmet=d.get('helmet'),
            helminth_ability=d.get('helminth_ability'),
        )

    def validate(self, cache: DataCache) -> list[str]:
        errors: list[str] = []

        if self.warframe_name not in cache.warframe_by_name:
            errors.append(f"Unknown warframe: {self.warframe_name}")
            return errors

        warframe = cache.warframe_by_name[self.warframe_name]

        if len(self.auras) > warframe.aura_slots:
            errors.append(
                f"Too many auras: {self.warframe_name} has {warframe.aura_slots} "
                f"slot(s), {len(self.auras)} equipped"
            )

        max_arcanes = 1 if (
            self.helmet and self.helmet in cache.arcane_helmet_unique_names
        ) else 2
        if len(self.arcanes) > max_arcanes:
            errors.append(
                f"Too many arcanes: max {max_arcanes} with this helmet, "
                f"got {len(self.arcanes)}"
            )

        if len(self.shards) > 5:
            errors.append(f"Too many shards: max 5, got {len(self.shards)}")

        all_mods = [*self.mods, self.exilus, *self.auras]
        for em in filter(None, all_mods):
            mod = cache.mod_by_unique_name.get(em.unique_name)
            if not mod:
                continue
            if em.rank < 0 or em.rank > mod.max_rank:
                errors.append(
                    f"Mod '{mod.name}' rank {em.rank} out of bounds "
                    f"[0, {mod.max_rank}]"
                )
            if mod.is_augment and mod.compat_name:
                valid = (
                    mod.compat_name == self.warframe_name
                    or self._helminth_allows_augment(mod.name, cache)
                )
                if not valid:
                    errors.append(
                        f"Augment '{mod.name}' requires warframe "
                        f"'{mod.compat_name}' or Helminth subsume"
                    )

        for ea in self.arcanes:
            arcane = cache.arcane_by_unique_name.get(ea.unique_name)
            if arcane and (ea.rank < 0 or ea.rank > arcane.max_rank):
                errors.append(
                    f"Arcane '{arcane.name}' rank {ea.rank} out of "
                    f"bounds [0, {arcane.max_rank}]"
                )

        return errors

    def _helminth_allows_augment(self, augment_name: str, cache: DataCache) -> bool:
        if not self.helminth_ability:
            return False
        return (
            cache.abilities_data.augment_to_ability.get(augment_name)
            == self.helminth_ability
        )
