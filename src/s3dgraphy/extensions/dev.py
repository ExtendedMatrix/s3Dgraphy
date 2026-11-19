"""The development folder of the plugins — ``plugins_dev_dir`` (W15a of the
extensions plan, MICRO-PL18, E.D. 18 Nov 2026; SPEC-plugin §7).

A folder named in the settings whose plugins are loaded **as they are on
disk**: not installed, no archive hash, no trust question — the person who
writes a plugin is the person who runs it. It is the HOST that decides when
the folder counts: EMStudio only with «Funzioni sperimentali» on, the command
line only when asked (``em.plugins.sync(host, dev=True)``). This module
never loads anything; it says what is there.

* where — ``S3DGRAPHY_PLUGINS_DEV_DIR`` (the checks, a terminal) else the
  ``dir`` of ``~/.s3dgraphy/plugins/dev.json`` (this machine's setting, the
  same for EMStudio and EM Tools);
* what — every sub-folder with an ``em-extension.toml`` that has ``[code]``
  (or the folder itself, when it is one), read and validated each time, its
  code folder put on ``sys.path`` in place. A mixed package in development
  brings its data too, read from the same folder (``ctx.package``);
* how it is marked — source ``dev``, ``verified: false``, wherever an
  installed plugin says «from disk» (window, menus, the DTC of its acts).

Binary wheels are unpacked into ``~/.s3dgraphy/plugins/.dev-wheels/<id>/``,
never into the developer's folder.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..profiles.package import ENVELOPE, open_package
from ..profiles.problems import ProfileError, Problem, ERROR, WARNING
from .store import ExtensionError, _code, _module, _now, _write_json, plugins_dir
from .validate import validate_archive

DEV_ENV = "S3DGRAPHY_PLUGINS_DEV_DIR"
DEV_FILE = "dev.json"
DEV_FORMAT = "em-plugins-dev/1"
SOURCE_DEV = "dev"


def _setting_path() -> Path:
    return plugins_dir() / DEV_FILE


def dev_dir_setting() -> Optional[str]:
    """What the settings say (the environment wins), as written: it may not
    exist any more."""
    env = os.environ.get(DEV_ENV)
    if env:
        return env
    try:
        doc = json.loads(_setting_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    d = doc.get("dir") if isinstance(doc, dict) and doc.get("format") == DEV_FORMAT else None
    return str(d) if d else None


def dev_dir() -> Optional[Path]:
    """The development folder, when it is set and is a folder of this machine."""
    d = dev_dir_setting()
    if not d:
        return None
    p = Path(d).expanduser()
    return p if p.is_dir() else None


def set_dev_dir(path: Optional[str]) -> Optional[str]:
    """Write the setting (``None`` or ``""`` clears it). A path that is not a
    folder is refused: :class:`ExtensionError` ``dev_dir_missing``."""
    target = _setting_path()
    if not path:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return None
    p = Path(str(path)).expanduser()
    if not p.is_dir():
        raise ExtensionError.of("dev_dir_missing", path=str(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, {"format": DEV_FORMAT, "dir": str(p.resolve()), "set_at": _now()})
    return str(p.resolve())


def _candidates(root: Path) -> List[Path]:
    if (root / ENVELOPE).is_file():
        return [root]
    return [c for c in sorted(root.iterdir())
            if c.is_dir() and not c.name.startswith((".", "_")) and (c / ENVELOPE).is_file()]


def _read(folder: Path) -> Dict[str, Any]:
    """One development folder → the row :func:`s3dgraphy.em.plugins.sync`
    loads: like :func:`~s3dgraphy.extensions.active_code`'s, with the
    ``meta`` an installation would have written in ``.install.json`` and the
    problems that refuse it (EN + IT)."""
    row: Dict[str, Any] = {"id": folder.name, "source": SOURCE_DEV, "dev": True, "dev_folder": str(folder),
                           "version": "", "module": "", "entry": "", "hosts": [], "problems": [], "warnings": []}
    try:
        pkg = open_package(folder)
    except ProfileError as exc:
        row["problems"].append(Problem("dev_not_a_package", ERROR, "", {"folder": folder.name, "why": str(exc)}).as_dict())
        return row
    if not pkg.has_code:
        row["problems"].append(Problem("dev_no_code", ERROR, "", {"folder": folder.name}).as_dict())
        return row
    report = validate_archive(pkg)
    env = pkg.envelope or {}
    c = _code(pkg)
    eid = str(pkg.id or folder.name)
    root = (pkg.code_root or "").rstrip("/")
    code_folder = (folder / root) if root else folder
    row.update(id=eid, version=str(pkg.code_version or ""), module=_module(c.get("entry")),
               entry=str(c.get("entry") or ""), hosts=list(c.get("hosts") or []), folder=str(code_folder))
    row["problems"] = [p.as_dict() for p in report.errors]
    row["warnings"] = [p.as_dict() for p in report.warnings]
    row["meta"] = {
        "id": eid, "version": row["version"], "archive": {"id": eid, "version": env.get("version")},
        "source": SOURCE_DEV, "dev": True, "dev_folder": str(folder), "origin": str(folder),
        "entry": c.get("entry"), "module": row["module"], "hosts": row["hosts"],
        "trusted": None, "verified": False, "package": eid if pkg.has_data else None,
        "data_version": pkg.data_version if pkg.has_data else None, "code": c,
        "em_api_min": env.get("em_api_min"), "em_api_max": env.get("em_api_max"), "name": env.get("name"),
        "wheels_dir": str(plugins_dir() / ".dev-wheels" / eid),
    }
    return row


def dev_code(host: Optional[str] = None) -> List[Dict[str, Any]]:
    """The plugins of the development folder (for ``host``, when given:
    those that declare it, or no host at all), read now. Two folders with
    the same id: the first in name order is kept, the other said."""
    root = dev_dir()
    if root is None:
        return []
    out: Dict[str, Dict[str, Any]] = {}
    for folder in _candidates(root):
        row = _read(folder)
        if any(p.get("code") == "dev_no_code" for p in row["problems"]):
            continue                                 # a package of data only: not a plugin, nothing to load
        if host and row["hosts"] and host not in row["hosts"]:
            continue
        have = out.get(row["id"])
        if have is not None:
            have["warnings"].append(Problem("dev_same_id", WARNING, "", {
                "id": row["id"], "folder": Path(have["dev_folder"]).name, "other": folder.name}).as_dict())
            continue
        out[row["id"]] = row
    return [out[k] for k in sorted(out)]


def describe_dev(host: Optional[str] = None) -> Dict[str, Any]:
    """What a settings window shows: the folder as set, whether it is there,
    the plugins in it (id, version, folder, problems)."""
    setting = dev_dir_setting()
    rows = dev_code(host) if dev_dir() is not None else []
    return {"setting": setting, "env": bool(os.environ.get(DEV_ENV)), "exists": dev_dir() is not None,
            "plugins": [{k: r.get(k) for k in ("id", "version", "module", "hosts", "dev_folder", "problems", "warnings")}
                        for r in rows]}


__all__ = ["DEV_ENV", "DEV_FILE", "SOURCE_DEV", "dev_dir", "dev_dir_setting", "set_dev_dir", "dev_code", "describe_dev"]
