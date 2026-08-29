import json

from core.data_loader import LayerRepository


def test_custom_markers_use_separate_per_user_path(tmp_path):
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    bundled_path = data_folder / "custom_markers.json"
    bundled_path.write_text(
        json.dumps({"items": [{"name": "Bundled", "position": [1, 2, 3]}]}),
        encoding="utf-8",
    )
    user_path = tmp_path / "config" / "custom_markers.json"

    repository = LayerRepository(data_folder, custom_markers_path=user_path)
    assert repository.layers["custom_markers"] == []

    marker = {"name": "Personal", "position": [4, 5, 6]}
    repository.save_custom_markers([marker])

    assert json.loads(user_path.read_text(encoding="utf-8"))["items"] == [marker]
    assert json.loads(bundled_path.read_text(encoding="utf-8"))["items"][0]["name"] == "Bundled"
