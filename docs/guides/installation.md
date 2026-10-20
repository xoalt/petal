[Documentation](../README.md) / Install Petal

# Install Petal

Download and extract the Linux archive from [Releases](https://github.com/xoalt/petal/releases), keep the folder in a permanent location, then run:

```sh
./petal-run
```

## Requirements

Core requirements: Python 3.11+, GTK4, PyGObject with Cairo integration, pycairo, and Pillow. gtk4-layer-shell enables the separate Wayland layers; without it Petal falls back to ordinary windows. On Arch/CachyOS the package names are `python`, `gtk4`, `python-gobject`, `python-cairo`, `python-pillow`, and `gtk4-layer-shell`. Obtain core runtime dependencies through your distribution software manager. Petal does not install them silently.

These are runtime dependencies; the release archive does not bundle them. Conversion programs are optional and covered in [Software setup](software.md).

## First launch

First launch walks through Software, Applications, Appearance, and Preferences. Program lists start with **Choose a program…** and include **Other program…** for a compatible external executable. No replacement program or download is preselected. Checks use temporary samples and show which exports passed before accepting an external program.

## Desktop launcher

Optional desktop entry and `~/.local/bin/petal` launcher:

```sh
python3 install.py
```

This only creates user-local launchers pointing at the extracted folder. It leaves system defaults, autostart, compositor rules, and preferences alone. Existing unrelated launchers are never overwritten. Remove the managed launchers with `python3 install.py --remove`; app files and preferences remain.
