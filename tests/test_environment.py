import os

import pytest

from core import environment
from core.environment import detect, distro_family, install_command

UBUNTU = {"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Ubuntu 24.04 LTS"}
FEDORA = {"ID": "fedora", "PRETTY_NAME": "Fedora Linux 43"}
CACHY = {"ID": "cachyos", "ID_LIKE": "arch", "PRETTY_NAME": "CachyOS"}
MINT = {"ID": "linuxmint", "ID_LIKE": "ubuntu debian", "PRETTY_NAME": "Linux Mint 22"}

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Linux detection")


def _detect(env, release, *, grim=False, tesseract=False, portal=True, pywayland=False):
    return detect(
        env,
        os_release=release,
        which=lambda name: "/usr/bin/grim" if grim and name == "grim" else None,
        tesseract_ready=lambda: tesseract,
        portal_available=lambda: portal,
        module_available=lambda name: pywayland,
    )


def _keys(env):
    return {item.key: item for item in env.requirements}


def test_ubuntu_gnome_needs_tesseract_and_portal_but_not_overlay_extras():
    env = _detect(
        {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, UBUNTU
    )
    items = _keys(env)
    assert env.is_gnome and not env.uses_layer_shell
    assert set(items) == {"tesseract", "portal"}
    assert items["tesseract"].install == "sudo apt install tesseract-ocr"
    assert [item.key for item in env.missing] == ["tesseract"]


def test_fedora_kde_uses_overlay_and_portal_not_grim():
    env = _detect({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"}, FEDORA)
    assert env.uses_layer_shell
    assert set(_keys(env)) == {"tesseract", "portal", "pywayland"}


def test_niri_without_desktop_variable_is_detected_and_wants_grim():
    env = _detect(
        {"XDG_SESSION_TYPE": "wayland", "NIRI_SOCKET": "/run/user/1000/niri.sock"},
        CACHY,
        tesseract=True,
    )
    items = _keys(env)
    assert env.desktops == ("niri",)
    assert items["grim"].install == "sudo pacman -S --needed grim"
    assert items["grim"].required is False  # the portal still works
    assert [item.key for item in env.missing] == ["grim", "pywayland"]


def test_grim_is_required_when_there_is_no_portal():
    env = _detect(
        {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland"},
        CACHY,
        portal=False,
    )
    assert _keys(env)["grim"].required is True


def test_x11_session_only_needs_tesseract():
    env = _detect({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "X-Cinnamon"}, MINT)
    assert set(_keys(env)) == {"tesseract"}
    assert not env.uses_layer_shell


def test_install_commands_per_family_and_unknown_distro():
    assert distro_family({"ID": "endeavouros", "ID_LIKE": "arch"}) == "arch"
    assert distro_family({"ID": "pop", "ID_LIKE": "ubuntu debian"}) == "debian"
    assert distro_family({"ID": "somethingnew"}) == ""
    assert install_command("suse", "tesseract").startswith("sudo zypper install")
    assert "package manager" in install_command("", "grim")
    assert "configuration" in install_command("nixos", "tesseract")


def test_wants_pywayland_cli_matches_desktop(monkeypatch):
    monkeypatch.setattr(
        environment,
        "detect",
        lambda: _detect({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "sway"}, CACHY),
    )
    assert environment.main(["x", "wants-pywayland"]) == 0
    monkeypatch.setattr(
        environment,
        "detect",
        lambda: _detect({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"}, UBUNTU),
    )
    assert environment.main(["x", "wants-pywayland"]) == 1


from types import SimpleNamespace

from core.environment import install_system_packages, system_install_plan


def _wl(desktop):
    return {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": desktop}


def test_install_plan_uses_noninteractive_command_per_distro():
    assert system_install_plan(_detect(_wl("niri"), CACHY)) == [
        "pacman", "-S", "--needed", "--noconfirm", "tesseract", "tesseract-data-eng", "grim",
    ]
    assert system_install_plan(_detect(_wl("GNOME"), UBUNTU)) == [
        "apt-get", "install", "-y", "tesseract-ocr",
    ]
    assert system_install_plan(_detect(_wl("KDE"), FEDORA)) == ["dnf", "install", "-y", "tesseract"]


def test_install_plan_is_empty_when_everything_is_present():
    assert system_install_plan(_detect(_wl("niri"), CACHY, grim=True, tesseract=True)) is None


def test_immutable_and_unknown_systems_are_never_auto_installed():
    env = _detect(_wl("KDE"), {"ID": "fedora", "VARIANT_ID": "kinoite"})
    assert env.immutable and system_install_plan(env) is None
    assert system_install_plan(_detect(_wl("GNOME"), {"ID": "somethingnew"})) is None


def _run_install(env, *, interactive, have, environ):
    calls, messages = [], []
    code = install_system_packages(
        env,
        run=lambda argv: calls.append(argv) or SimpleNamespace(returncode=0),
        which=lambda name: f"/usr/bin/{name}" if name in have else None,
        interactive=interactive,
        environ=environ,
        out=messages.append,
    )
    return code, calls, messages


@pytest.mark.skipif(os.name != "nt" and os.geteuid() == 0, reason="runs as root")
def test_terminal_uses_sudo_and_desktop_launch_uses_pkexec():
    env = _detect(_wl("GNOME"), UBUNTU)
    _, calls, _ = _run_install(env, interactive=True, have={"sudo", "pkexec"}, environ={"WAYLAND_DISPLAY": "w"})
    assert calls == [["sudo", "apt-get", "install", "-y", "tesseract-ocr"]]
    _, calls, _ = _run_install(env, interactive=False, have={"sudo", "pkexec"}, environ={"WAYLAND_DISPLAY": "w"})
    assert calls == [["pkexec", "apt-get", "install", "-y", "tesseract-ocr"]]
    _, calls, messages = _run_install(env, interactive=False, have={"sudo"}, environ={})
    assert calls == [] and "sudo apt-get install -y tesseract-ocr" in messages[-1]


def test_opt_out_and_failed_install_never_block_launch():
    env = _detect(_wl("GNOME"), UBUNTU)
    _, calls, _ = _run_install(
        env, interactive=True, have={"sudo"}, environ={"ISLE_COMPANION_NO_SYSTEM_INSTALL": "1"}
    )
    assert calls == []
    messages = []
    code = install_system_packages(
        env,
        run=lambda argv: SimpleNamespace(returncode=1),
        which=lambda name: "/usr/bin/sudo",
        interactive=True,
        environ={},
        out=messages.append,
    )
    assert code == 1 and "install them later" in messages[-2]
