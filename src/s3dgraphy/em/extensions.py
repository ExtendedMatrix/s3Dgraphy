"""``em.extensions`` — install, list, enable from disk (phase 1, the plan's §5.1).

The library that does it is :mod:`s3dgraphy.extensions` (W21, W19); this is
its face in ``em``, the same in a console, a script and Blender. It never asks
a question: the trust of a ``[code]`` section is an argument
(``trust=True``), and :func:`preview` says beforehand what an archive is made
of and whether the question is needed — a window asks, a script decides with
its eyes open.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Extensions:
    """``em.extensions``."""

    def preview(self, source: Any) -> Dict[str, Any]:
        """The two panels of the confirmation (data, code), nothing written."""
        from .. import extensions as E
        return E.preview(source)

    def validate(self, source: Any) -> Dict[str, Any]:
        """Everything wrong with an archive: ``{ok, errors, warnings}``, each
        problem in English and Italian."""
        from .. import extensions as E
        report = E.validate_archive(source)
        return report.as_dict() if hasattr(report, "as_dict") else {"ok": report.ok}

    def install(self, source: Any, *, parts: str = "all", trust: bool = False) -> Dict[str, Any]:
        """Install from disk (a folder or a zip): data first, code after. A
        ``[code]`` section needs ``trust=True`` — said by :func:`preview`;
        ``parts="data"`` is «Data only»."""
        from .. import extensions as E
        return E.install(source, parts=parts, trust=trust)

    def update(self, source: Any, *, trust: bool = False) -> Dict[str, Any]:
        from .. import extensions as E
        return E.update(source, trust=trust)

    def list(self) -> List[Dict[str, Any]]:
        """What is installed on this machine, by parts."""
        from .. import extensions as E
        return E.installed()

    installed = list

    def get(self, eid: str) -> Optional[Dict[str, Any]]:
        from .. import extensions as E
        return E.get(eid)

    def enable(self, eid: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Make a code version the active one of its id. It is LOADED by the
        host at its next start (W14): Python does not unload a module well."""
        from .. import extensions as E
        return E.enable(eid, version)

    def disable(self, eid: str) -> bool:
        from .. import extensions as E
        return E.disable(eid)

    def active(self, host: Optional[str] = None) -> List[Dict[str, Any]]:
        """The active code versions for ``host`` (default: the current host;
        the command line, ``none``, sees them all)."""
        from .. import extensions as E
        from . import host as _host
        name = host if host is not None else _host.current().name
        return E.active_code(None if name == "none" else name)

    def removal_plan(self, eid: str) -> Dict[str, Any]:
        from .. import extensions as E
        return E.removal_plan(eid)

    def remove(self, eid: str, *, part: str = "all", confirm: bool = False,
               purge_vocabularies: bool = False) -> Dict[str, Any]:
        """``part``: ``code`` · ``data`` · ``all``. The vocabularies stay on the
        machine unless ``purge_vocabularies`` (D-19)."""
        from .. import extensions as E
        if part == "code":
            return E.remove_code(eid)
        if part == "data":
            return E.remove_data(eid, confirm=confirm, purge_vocabularies=purge_vocabularies)
        return E.remove(eid, confirm=confirm, purge_vocabularies=purge_vocabularies)

    def build(self, folder: Any, *, output_dir: Any = None, dry_run: bool = False) -> Dict[str, Any]:
        """The curator's folder → ``<id>-<version>.zip`` (as the command line)."""
        from .. import extensions as E
        return E.build(folder, output_dir=output_dir, dry_run=dry_run)

    def __repr__(self) -> str:
        return "<em.extensions: install, list, enable from disk>"
