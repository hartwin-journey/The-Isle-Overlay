"""Detect the Linux desktop the app runs on and what it still needs.

Used at startup (logging and in-app hints) and by ``run.sh`` during setup:

* ``python -m core.environment wants-pywayland`` decides whether to install
  the optional Mini Map overlay support for this desktop;
* ``python -m core.environment install-system`` installs missing system
  packages (Tesseract, grim) with the distribution's package manager, asking
  for the password through sudo or pkexec. Image-based systems and unknown
  distributions are never modified; the app shows what to install instead.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Desktops whose compositor supports wlr-layer-shell (the Mini Map overlay).
LAYER_SHELL_DESKTOPS = {
    "kde",
    "sway",
    "hyprland",
    "niri",
    "river",
    "wayfire",
    "labwc",
    "cosmic",
    "dwl",
    "hikari",
    "qtile",
    "mango",
}
# wlroots-style compositors where grim (wlr-screencopy) captures the screen.
GRIM_DESKTOPS = LAYER_SHELL_DESKTOPS - {"kde", "cosmic"}
GNOME_DESKTOPS = {"gnome", "gnome-classic", "gnome-flashback", "unity", "budgie"}

# Distribution families by /etc/os-release ID / ID_LIKE.
_FAMILIES = {
    "arch": {"arch", "cachyos", "manjaro", "endeavouros", "garuda", "artix"},
    "debian": {"debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin", "kali"},
    "fedora": {"fedora", "rhel", "centos", "nobara", "bazzite", "ultramarine"},
    "suse": {"opensuse", "suse", "opensuse-tumbleweed", "opensuse-leap"},
    "void": {"void"},
    "alpine": {"alpine"},
    "gentoo": {"gentoo"},
    "nixos": {"nixos"},
}

# family -> (install command prefix, {component: package names})
_PACKAGES: dict[str, tuple[str, dict[str, str]]] = {
    "arch": ("sudo pacman -S --needed", {"tesseract": "tesseract tesseract-data-eng", "grim": "grim"}),
    "debian": ("sudo apt install", {"tesseract": "tesseract-ocr", "grim": "grim"}),
    "fedora": ("sudo dnf install", {"tesseract": "tesseract", "grim": "grim"}),
    "suse": (
        "sudo zypper install",
        {"tesseract": "tesseract-ocr tesseract-ocr-traineddata-english", "grim": "grim"},
    ),
    "void": ("sudo xbps-install", {"tesseract": "tesseract-ocr", "grim": "grim"}),
    "alpine": ("sudo apk add", {"tesseract": "tesseract-ocr tesseract-ocr-data-eng", "grim": "grim"}),
    "gentoo": ("sudo emerge", {"tesseract": "app-text/tesseract", "grim": "gui-apps/grim"}),
}


# family -> non-interactive install command (run as root).
_NONINTERACTIVE: dict[str, list[str]] = {
    "arch": ["pacman", "-S", "--needed", "--noconfirm"],
    "debian": ["apt-get", "install", "-y"],
    "fedora": ["dnf", "install", "-y"],
    "suse": ["zypper", "--non-interactive", "install"],
    "void": ["xbps-install", "-y"],
    "alpine": ["apk", "add"],
}
# Components a plain package install can provide.
_SYSTEM_COMPONENTS = ("tesseract", "grim")


@dataclass(frozen=True)
class Requirement:
    key: str
    title: str
    purpose: str
    installed: bool
    required: bool
    install: str  # Command or instruction shown to the user.


@dataclass
class Environment:
    platform: str
    distro_name: str = ""
    distro_family: str = ""
    immutable: bool = False
    session_type: str = ""
    desktops: tuple[str, ...] = ()
    requirements: list[Requirement] = field(default_factory=list)

    @property
    def desktop_label(self) -> str:
        return ":".join(self.desktops) or "unknown"

    @property
    def is_wayland(self) -> bool:
        return self.session_type == "wayland"

    @property
    def is_gnome(self) -> bool:
        return bool(set(self.desktops) & GNOME_DESKTOPS)

    @property
    def uses_layer_shell(self) -> bool:
        return self.is_wayland and bool(set(self.desktops) & LAYER_SHELL_DESKTOPS)

    @property
    def missing(self) -> list[Requirement]:
        return [item for item in self.requirements if not item.installed]

    def summary(self) -> str:
        parts = [self.distro_name or self.platform, self.session_type or "unknown session"]
        parts.append(f"desktop {self.desktop_label}")
        return ", ".join(parts)


def _os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep:
                values[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return values


def distro_family(os_release: dict[str, str]) -> str:
    ids = {
        part.lower()
        for key in ("ID", "ID_LIKE")
        for part in os_release.get(key, "").split()
    }
    for family, members in _FAMILIES.items():
        if ids & members:
            return family
    return ""


def install_command(family: str, component: str) -> str:
    if family == "nixos":
        return f"add pkgs.{'tesseract' if component == 'tesseract' else component} to your configuration"
    if family in _PACKAGES:
        prefix, packages = _PACKAGES[family]
        return f"{prefix} {packages[component]}"
    return f"install the '{component}' package with your package manager"


def _detect_desktops(environ: dict[str, str]) -> tuple[str, ...]:
    raw = environ.get("XDG_CURRENT_DESKTOP") or environ.get("XDG_SESSION_DESKTOP") or ""
    desktops = [part.strip().lower() for part in raw.replace(";", ":").split(":") if part.strip()]
    # Some compositors leave XDG_CURRENT_DESKTOP unset; their sockets give them away.
    if not desktops:
        if environ.get("NIRI_SOCKET"):
            desktops = ["niri"]
        elif environ.get("SWAYSOCK"):
            desktops = ["sway"]
        elif environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            desktops = ["hyprland"]
    return tuple(dict.fromkeys(desktops))


def _session_type(environ: dict[str, str]) -> str:
    session = environ.get("XDG_SESSION_TYPE", "").lower()
    if session in {"wayland", "x11"}:
        return session
    if environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if environ.get("DISPLAY"):
        return "x11"
    return session


def _tesseract_ready() -> bool:
    from core.local_ocr import TesseractOcrEngine

    return TesseractOcrEngine().support_status()[0]


def _portal_available() -> bool:
    for root in ("/usr/share/dbus-1/services", "/usr/local/share/dbus-1/services"):
        if (Path(root) / "org.freedesktop.portal.Desktop.service").is_file():
            return True
    return False


def _is_immutable(release: dict[str, str]) -> bool:
    """Image-based systems where a normal package install does not apply."""

    variant = release.get("VARIANT_ID", "").lower()
    return (
        Path("/run/ostree-booted").exists()
        or release.get("ID", "").lower() in {"steamos", "nixos"}
        or variant in {"silverblue", "kinoite", "sericea", "onyx", "aurora", "bluefin", "bazzite"}
        or "bazzite" in release.get("ID", "").lower()
    )


def system_install_plan(env: Environment) -> list[str] | None:
    """Return the root install command for missing system packages.

    None means nothing to do, or that this system cannot be handled with a
    plain package install (unknown/immutable distro, NixOS, Gentoo).
    """

    if env.platform != "linux" or env.immutable or env.distro_family not in _NONINTERACTIVE:
        return None
    _prefix, names = _PACKAGES[env.distro_family]
    packages: list[str] = []
    for item in env.missing:
        if item.key in _SYSTEM_COMPONENTS:
            packages.extend(names[item.key].split())
    if not packages:
        return None
    return [*_NONINTERACTIVE[env.distro_family], *packages]


def install_system_packages(
    env: Environment,
    *,
    run=subprocess.run,
    which=shutil.which,
    interactive: bool | None = None,
    environ: dict[str, str] | None = None,
    out=print,
) -> int:
    """Install missing system packages, asking for the password.

    In a terminal this uses sudo; without one (desktop launcher) it uses
    pkexec, which shows the desktop's graphical password prompt.
    """

    environ = dict(os.environ if environ is None else environ)
    if environ.get("ISLE_COMPANION_NO_SYSTEM_INSTALL"):
        return 0
    plan = system_install_plan(env)
    if plan is None:
        for item in env.missing:
            if item.key in _SYSTEM_COMPONENTS:
                out(f"{item.title} is missing ({item.purpose}). Install it with: {item.install}")
        return 0
    if interactive is None:
        interactive = sys.stdin.isatty()
    if os.geteuid() == 0:
        elevate: list[str] = []
    elif interactive and which("sudo"):
        elevate = ["sudo"]
    elif which("pkexec") and (environ.get("WAYLAND_DISPLAY") or environ.get("DISPLAY")):
        elevate = ["pkexec"]
    else:
        out("Missing system packages. Install them with: sudo " + " ".join(plan))
        return 0
    titles = ", ".join(item.title for item in env.missing if item.key in _SYSTEM_COMPONENTS)
    out(f"Installing {titles} (your password is needed for system packages) ...")
    result = run([*elevate, *plan])
    code = int(getattr(result, "returncode", 1))
    if code != 0:
        out("System packages were not installed. You can install them later with:")
        out("    sudo " + " ".join(plan))
    return code


def detect(
    environ: dict[str, str] | None = None,
    *,
    os_release: dict[str, str] | None = None,
    which=shutil.which,
    tesseract_ready=_tesseract_ready,
    portal_available=_portal_available,
    module_available=lambda name: importlib.util.find_spec(name) is not None,
) -> Environment:
    environ = dict(os.environ if environ is None else environ)
    if os.name == "nt" or sys.platform == "darwin":
        return Environment(platform="windows" if os.name == "nt" else "macos")
    release = _os_release() if os_release is None else os_release
    family = distro_family(release)
    env = Environment(
        platform="linux",
        distro_name=release.get("PRETTY_NAME") or release.get("NAME", ""),
        distro_family=family,
        immutable=_is_immutable(release),
        session_type=_session_type(environ),
        desktops=_detect_desktops(environ),
    )
    desktops = set(env.desktops)

    env.requirements.append(
        Requirement(
            key="tesseract",
            title="Tesseract OCR (English)",
            purpose="reads your coordinates for Automatic Tracking",
            installed=tesseract_ready(),
            required=True,
            install=install_command(family, "tesseract"),
        )
    )
    if env.is_wayland:
        grim_useful = bool(desktops & GRIM_DESKTOPS)
        has_portal = portal_available()
        if grim_useful:
            env.requirements.append(
                Requirement(
                    key="grim",
                    title="grim",
                    purpose="fast screen capture for Automatic Tracking on this desktop",
                    installed=bool(which("grim")),
                    # The screenshot portal also works, just more slowly.
                    required=not has_portal,
                    install=install_command(family, "grim"),
                )
            )
        else:
            env.requirements.append(
                Requirement(
                    key="portal",
                    title="xdg-desktop-portal",
                    purpose="screen capture for Automatic Tracking on this desktop",
                    installed=has_portal,
                    required=True,
                    install="install xdg-desktop-portal and your desktop's portal backend",
                )
            )
        if env.uses_layer_shell:
            env.requirements.append(
                Requirement(
                    key="pywayland",
                    title="pywayland (Python)",
                    purpose="keeps the Mini Map above the game on every workspace",
                    installed=module_available("pywayland"),
                    required=False,
                    install="sh run.sh   (installs it automatically)",
                )
            )
    return env


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "report"
    env = detect()
    if command == "wants-pywayland":
        # Used by run.sh: exit 0 when this desktop benefits from pywayland.
        return 0 if env.uses_layer_shell else 1
    if command == "install-system":
        # Used by run.sh during setup. Never fatal for launching the app.
        install_system_packages(env)
        return 0
    print(f"Detected: {env.summary()}")
    for item in env.requirements:
        state = "ok" if item.installed else ("MISSING" if item.required else "recommended")
        line = f"  [{state}] {item.title}: {item.purpose}"
        if not item.installed:
            line += f"\n           -> {item.install}"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
