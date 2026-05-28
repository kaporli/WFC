# Interactions

Hand-curated YAML files for conditional mechanics that cannot be derived from item data alone.

## Format

Each file covers one mechanic or conditional buff:

```yaml
name: shieldgate
description: >
  Shield gate prevents one-shot kills. When shields reach 0, a brief
  invulnerability window opens. Duration depends on whether it's a full
  gate (shields fully depleted) or short gate (partial depletion).
rules:
  - trigger: shield_fully_depleted
    gate_duration_seconds: 1.3
    requires_mod: null
  - trigger: shield_partially_depleted
    gate_duration_seconds: 0.13
    requires_mod: null
  - trigger: ability_cast
    condition: brief_respite_equipped
    effect:
      stat: shield
      value_per_energy_spent: 1.0
  - trigger: ability_cast
    condition: catalyzing_shields_equipped
    effect:
      sets_shield_to: 1
      gate_duration_seconds: 1.3
```

## File naming

One file per mechanic: `shieldgate.yaml`, `adaptation.yaml`, `molt_augmented.yaml`, etc.

Each YAML key maps to a Python function in `warframe_engine/mechanics/`.
