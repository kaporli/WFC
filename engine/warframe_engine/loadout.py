from __future__ import annotations
from dataclasses import dataclass, field, asdict
from warframe_engine.build import Build, EquippedMod


@dataclass
class WeaponSlot:
    weapon_unique_name: str
    mods: list[EquippedMod] = field(default_factory=list)
    exilus: EquippedMod | None = None
    riven: EquippedMod | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> WeaponSlot:
        return cls(
            weapon_unique_name=d['weapon_unique_name'],
            mods=[EquippedMod(**m) for m in d.get('mods', [])],
            exilus=EquippedMod(**d['exilus']) if d.get('exilus') else None,
            riven=EquippedMod(**d['riven']) if d.get('riven') else None,
        )


@dataclass
class Loadout:
    warframe: Build
    primary: WeaponSlot | None = None
    secondary: WeaponSlot | None = None
    melee: WeaponSlot | None = None
    archgun: WeaponSlot | None = None
    archgun_gravimag: bool = False
    companion_mods: list[EquippedMod] = field(default_factory=list)
    companion_weapon: WeaponSlot | None = None

    def to_dict(self) -> dict:
        def slot_d(s: WeaponSlot | None) -> dict | None:
            return s.to_dict() if s else None
        return {
            'warframe': self.warframe.to_dict(),
            'primary': slot_d(self.primary),
            'secondary': slot_d(self.secondary),
            'melee': slot_d(self.melee),
            'archgun': slot_d(self.archgun),
            'archgun_gravimag': self.archgun_gravimag,
            'companion_mods': [asdict(m) for m in self.companion_mods],
            'companion_weapon': slot_d(self.companion_weapon),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Loadout:
        def slot_from(v: dict | None) -> WeaponSlot | None:
            return WeaponSlot.from_dict(v) if v else None
        return cls(
            warframe=Build.from_dict(d['warframe']),
            primary=slot_from(d.get('primary')),
            secondary=slot_from(d.get('secondary')),
            melee=slot_from(d.get('melee')),
            archgun=slot_from(d.get('archgun')),
            archgun_gravimag=d.get('archgun_gravimag', False),
            companion_mods=[EquippedMod(**m) for m in d.get('companion_mods', [])],
            companion_weapon=slot_from(d.get('companion_weapon')),
        )
