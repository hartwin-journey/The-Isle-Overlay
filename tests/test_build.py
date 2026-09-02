from tools.build_exe import build_arguments


def test_windows_build_includes_local_ocr_bridge_and_windows_data_separator():
    arguments = build_arguments("nt")
    assert "data;data" in arguments
    assert "assets/map;assets/map" in arguments
    assert "core/windows_ocr.ps1;core" in arguments


def test_linux_build_uses_posix_separator_and_omits_windows_ocr_bridge():
    arguments = build_arguments("posix")
    assert "data:data" in arguments
    assert "assets/map:assets/map" in arguments
    assert not any("windows_ocr.ps1" in argument for argument in arguments)
