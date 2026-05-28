from warframe_engine.loader import load_warframes, load_mods, load_arcanes


def test_warframes_load():
    frames = load_warframes()
    assert len(frames) > 0, "Expected at least one warframe"
    frost = next((f for f in frames if f.name == "Frost"), None)
    assert frost is not None, "Frost not found in warframes.json"
    assert frost.base_stats.armor > 0, "Frost should have armor > 0"
    assert len(frost.abilities) == 4, "Frost should have 4 abilities"


def test_mods_load():
    mods = load_mods()
    assert len(mods) > 0, "Expected at least one mod"
    vitality = next((m for m in mods if m.name == "Vitality"), None)
    assert vitality is not None, "Vitality not found in mods.json"
    assert vitality.max_rank == 10, "Vitality should be rank 10"


def test_arcanes_load():
    arcanes = load_arcanes()
    assert len(arcanes) > 0, "Expected at least one arcane"
    energize = next((a for a in arcanes if "Energize" in a.name), None)
    assert energize is not None, "Arcane Energize not found"
    assert energize.max_rank >= 3, "Arcane Energize should have at least 3 ranks"
