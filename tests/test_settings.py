import json

from core.settings import DEFAULT_SETTINGS, SettingsStore


def test_missing_settings_create_defaults(tmp_path):
    store = SettingsStore(tmp_path / "config" / "settings.json")
    values = store.load()
    assert values["hotkeys"]["toggle_full_map"] == "Ctrl+Shift+M"
    assert store.path.exists()
    assert values["layers"]["updrafts"] is True
    assert values["layer_opacity"]["updrafts"] == 1.0


def test_malformed_settings_fall_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{bad json", encoding="utf-8")
    store = SettingsStore(path)
    values = store.load()
    assert values["layers"] == DEFAULT_SETTINGS["layers"]
    assert json.loads(path.read_text(encoding="utf-8"))["overlay_size"] == 360


def test_dynamic_per_zone_visibility_is_preserved(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "individual_migrations": {"Northern Route": False},
                "individual_sanctuaries": {"Central Haven": True},
            }
        ),
        encoding="utf-8",
    )
    values = SettingsStore(path).load()
    assert values["individual_migrations"] == {"Northern Route": False}
    assert values["individual_sanctuaries"] == {"Central Haven": True}


def test_legacy_overlay_settings_are_migrated_and_saved(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "overlay_circular_mask": True,
                "overlay_square_mode": False,
                "migration_opacity": 0.4,
                "overlay_size": 420,
                "hotkeys": {"toggle_full_map": "Alt+F8"},
            }
        ),
        encoding="utf-8",
    )
    values = SettingsStore(path).load()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert values["overlay_shape"] == "circle"
    assert values["layer_opacity"]["migrations"] == 0.4
    assert values["overlay_size"] == 420
    assert values["hotkeys"]["toggle_full_map"] == "Alt+F8"
    assert "overlay_circular_mask" not in saved
    assert "overlay_square_mode" not in saved
    assert "migration_opacity" not in saved


def test_new_appearance_settings_are_clamped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "overlay_shape": "triangle",
                "overlay_interaction_hold_key": "NotAKey",
                "poi_label_font_size_full": 100,
                "poi_label_font_size_mini": 1,
                "map_label_font_preset": "comic_sans_ultra",
                "automatic_tracking_enabled": 1,
                "automatic_tracking_region": {
                    "x": -999_999,
                    "y": 999_999,
                    "width": 2,
                    "height": 999_999,
                },
                "automatic_tracking_interval_ms": 10,
                "automatic_tracking_confirmation_reads": 99,
                "layer_opacity": {"water": 5, "sanctuaries": 0},
            }
        ),
        encoding="utf-8",
    )
    values = SettingsStore(path).load()
    assert values["overlay_shape"] == "square"
    assert values["overlay_interaction_hold_key"] == "M4"
    assert values["poi_label_font_size_full"] == 24
    assert values["poi_label_font_size_mini"] == 6
    assert values["map_label_font_preset"] == "segoe_semibold"
    assert values["automatic_tracking_enabled"] is True
    assert values["automatic_tracking_region"] == {
        "x": -100_000,
        "y": 100_000,
        "width": 32,
        "height": 2160,
    }
    assert values["automatic_tracking_interval_ms"] == 500
    assert values["automatic_tracking_confirmation_reads"] == 5
    assert values["layer_opacity"]["water"] == 1.0
    assert values["layer_opacity"]["sanctuaries"] == 0.1
