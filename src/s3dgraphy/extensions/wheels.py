"""Platforms and wheels: what a ``[code]`` section promises and what it carries.

The names are those of ``platforms`` (as Blender's manifest): ``macos-arm64``,
``macos-x64``, ``windows-x64``, ``windows-arm64``, ``linux-x64``,
``linux-arm64``. A wheel says where it runs in its file name (PEP 427).
Shared by the validator (W19: every declared platform has a wheel of every
distribution) and by the installer (W21: this machine has one).
"""
from __future__ import annotations

import platform
import re
import sys
from pathlib import Path
from typing import Optional, Set

#: the platforms a ``[code]`` section may declare
PLATFORMS = ("macos-arm64", "macos-x64", "windows-x64", "windows-arm64", "linux-x64", "linux-arm64")

_WHEEL_RE = re.compile(r"^[A-Za-z0-9_.]+-[A-Za-z0-9_.!+]+(-\d[^-]*)?-[^-]+-[^-]+-[^-]+\.whl$")


def this_platform() -> str:
    """``macos-arm64``, ``windows-x64``, ``linux-x64``… (the names of ``platforms``)."""
    osname = "macos" if sys.platform == "darwin" else "windows" if sys.platform.startswith("win") else "linux"
    m = platform.machine().lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "x64" if m in ("x86_64", "amd64", "x64") else m
    return f"{osname}-{arch}"


def is_wheel_name(filename: str) -> bool:
    return bool(_WHEEL_RE.match(Path(filename).name))


def wheel_platforms(filename: str) -> Optional[Set[str]]:
    """The platforms a wheel runs on, from its file name (PEP 427); ``None``
    for a pure wheel (``…-none-any.whl``)."""
    parts = Path(filename).name[:-len(".whl")].split("-") if filename.endswith(".whl") else []
    if len(parts) < 5:
        return set()
    out: Set[str] = set()
    for tag in parts[-1].split("."):
        if tag == "any":
            return None
        osname = "macos" if tag.startswith("macosx") else "windows" if tag.startswith("win") else \
            "linux" if "linux" in tag else ""
        if tag.endswith("universal2"):
            out |= {"macos-arm64", "macos-x64"}
        elif tag.endswith(("arm64", "aarch64")):
            out.add(f"{osname}-arm64")
        elif tag.endswith(("x86_64", "amd64")):
            out.add(f"{osname}-x64")
    return out


def wheel_dist(filename: str) -> str:
    return Path(filename).name.split("-", 1)[0].lower().replace("_", "-")


__all__ = ["PLATFORMS", "this_platform", "is_wheel_name", "wheel_platforms", "wheel_dist"]
