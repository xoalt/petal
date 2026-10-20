[Documentation](../README.md) / Wayland setup

# Wayland setup

For MangoWM, see [the optional shortcut example](../../integration/mango.conf.example). For other compositors, bind `petal --wheel` using their shortcut settings. Petal never modifies live compositor configuration. Four separate layer-shell namespaces are available:

| Surface | Namespace |
| --- | --- |
| Wheel | `petal-wheel` |
| Floating target | `petal-drop-target` |
| Shelf | `petal-shelf` |
| Settings | `petal-settings` |

Editors, progress, setup, and software checks are normal windows. Blur and positioning follow your compositor. The wheel supports alpha transparency and independent expanding hover animation, without an outer backing. It does not globally intercept modifier keys while hidden or read input devices. A global drag-anywhere trigger requires compositor support; use your shortcut and/or floating target.
