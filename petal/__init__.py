"""Petal: local file tools for Wayland desktops."""
from pathlib import Path
import tomllib

# The source distribution includes pyproject.toml as the version authority.
__version__ = tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text())['project']['version']
