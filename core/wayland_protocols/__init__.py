"""Wayland protocol bindings not bundled with pywayland.

``wlr_layer_shell_unstable_v1.py`` is generated with pywayland's scanner from
the upstream wlr-protocols XML shipped alongside it:

    python -m pywayland.scanner -i wayland.xml xdg-shell.xml \
        wlr-layer-shell-unstable-v1.xml -o out

with its relative imports pointed at ``pywayland.protocol``.
"""
