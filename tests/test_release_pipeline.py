from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_builds_platform_archives_and_publishes_tagged_releases():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "tags:" in workflow and '- "v*"' in workflow
    assert "windows-latest" in workflow
    assert "ubuntu-latest" in workflow
    assert "python tools/build_exe.py" in workflow
    assert "TheIsleCompanion-windows-x64.zip" in workflow
    assert "TheIsleCompanion-linux-x64.tar.gz" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "contents: write" in workflow
    assert "gh release create" in workflow
    assert "--target \"$TARGET\"" in workflow
