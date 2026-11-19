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
               purge_vocabularies: bool = False, purge_user_data: bool = False) -> Dict[str, Any]:
        """``part``: ``code`` · ``data`` · ``all``. The vocabularies stay on the
        machine unless ``purge_vocabularies`` (D-19), the plugin's own state
        unless ``purge_user_data`` (X3)."""
        from .. import extensions as E
        if part == "code":
            return E.remove_code(eid, purge_user_data=purge_user_data)
        if part == "data":
            return E.remove_data(eid, confirm=confirm, purge_vocabularies=purge_vocabularies,
                                 purge_user_data=purge_user_data)
        return E.remove(eid, confirm=confirm, purge_vocabularies=purge_vocabularies,
                        purge_user_data=purge_user_data)

    def build(self, folder: Any, *, output_dir: Any = None, dry_run: bool = False) -> Dict[str, Any]:
        """The curator's folder → ``<id>-<version>.zip`` (as the command line)."""
        from .. import extensions as E
        return E.build(folder, output_dir=output_dir, dry_run=dry_run)

    def dev_dir(self) -> Optional[str]:
        """W15a · the plugins' development folder as set (``None``: not set)."""
        from .. import extensions as E
        return E.dev_dir_setting()

    def set_dev_dir(self, path: Optional[str]) -> Optional[str]:
        """W15a · set (or clear, ``None``) the development folder of this
        machine. Its plugins load where they are, marked «development, not
        verified», only when the host says so (EMStudio: «Funzioni sperimentali»)."""
        from .. import extensions as E
        return E.set_dev_dir(path)

    def dev(self) -> Dict[str, Any]:
        """W15a · the development folder and the plugins in it, with their problems."""
        from .. import extensions as E
        return E.describe_dev()

    # X2 (MICRO-PL22) · the repositories of this machine
    def repositories(self) -> List[Dict[str, Any]]:
        """The repositories added on this machine (never their tokens)."""
        from .. import extensions as E
        return E.repositories()

    def add_repository(self, url: str, *, name: Optional[str] = None, token: Optional[str] = None,
                       check_on_startup: bool = False) -> Dict[str, Any]:
        """*Repository ▸ +*: an ``index.json`` by URL, ``file://`` or a folder (a NAS)."""
        from .. import extensions as E
        return E.add_repository(url, name=name, token=token, check_on_startup=check_on_startup)

    def remove_repository(self, name: str) -> bool:
        from .. import extensions as E
        return E.remove_repository(name)

    def sync(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Read the index again (http(s) only with ``online_access``)."""
        from .. import extensions as E
        return E.sync(name)

    def available(self, name: Optional[str] = None) -> Dict[str, Any]:
        """What the repositories offer, with what this machine has."""
        from .. import extensions as E
        return E.available(name)

    def install_from(self, repo: str, eid: str, version: Optional[str] = None, *, parts: str = "all",
                     trust: bool = False, with_requires: bool = True, trust_requires: bool = False) -> Dict[str, Any]:
        """Install from a repository: the archive checked against the index,
        the missing requirements first (their code only with ``trust_requires``)."""
        from .. import extensions as E
        return E.install_from(repo, eid, version, parts=parts, trust=trust, with_requires=with_requires,
                              trust_requires=trust_requires)

    def online_access(self) -> bool:
        """«Allow online access» (set it in the host's window, or ``s3dgraphy.extensions.set_online_access``)."""
        from .. import extensions as E
        return E.online_access()

    # X3 (MICRO-PL23) · updates, versions side by side, clean removal
    def check_updates(self, *, read: bool = True) -> Dict[str, Any]:
        """«Check for updates»: the indexes read again (https only with
        ``online_access``), what is newer, and which update would ask the trust again."""
        from .. import extensions as E
        return E.check_updates(read=read)

    def update_all(self, *, trust: Optional[List[str]] = None, read: bool = False) -> Dict[str, Any]:
        """«Update all»: an update that would ask the trust question again
        waits in ``needs_trust`` unless its id is in ``trust``."""
        from .. import extensions as E
        return E.update_all(trust=trust, read=read)

    def versions(self, eid: str) -> Dict[str, Any]:
        """The data and code versions of ``eid`` on this machine, side by side."""
        from .. import extensions as E
        return E.versions(eid)

    def use(self, eid: str, version: str, *, trust: bool = False) -> Dict[str, Any]:
        """An older (or newer) code version already on disk made the active
        one — no download; the host loads it at its next start."""
        from .. import extensions as E
        return E.use_code(eid, version, trust=trust)

    def remove_version(self, eid: str, part: str, version: str) -> Dict[str, Any]:
        """One version of the code (not the one in use) or of the data."""
        from .. import extensions as E
        return E.remove_version(eid, part, version)

    def clean(self, *, dry_run: bool = False) -> Dict[str, Any]:
        """What nothing in the register owns, removed (``dry_run``: said)."""
        from .. import extensions as E
        return E.clean(dry_run=dry_run)

    def _declared(self) -> Any:
        from . import host as _host
        c = getattr(_host.current(), "container", None)
        return ((getattr(c, "header", None) or {}).get("profiles")) if c is not None else None

    def document_updates(self, declared: Any = None) -> List[Dict[str, Any]]:
        """«This file uses stat 1.0.0, 1.1.0 is here»: for the packages the
        open document declares (or ``declared``), the newer version installed
        here, how much it changes, and for a major the CHANGELOG."""
        from .. import extensions as E
        return E.document_updates(self._declared() if declared is None else declared)

    def redeclare(self, ref: str, version: str) -> List[Dict[str, str]]:
        """The answer «yes»: the open document declares ``ref`` at ``version``
        (written at the next save; the packages read again now). Returns the
        new ``header.profiles``."""
        from .. import extensions as E
        from . import host as _host
        h = _host.current()
        c = getattr(h, "container", None)
        new = E.redeclare(self._declared(), ref, version)
        if c is not None and isinstance(getattr(c, "header", None), dict):
            c.header["profiles"] = new
            try:
                from ..profiles import activate
                c.profiles = activate(new)[0]
            except Exception:  # noqa: BLE001 — the declaration is written all the same
                pass
        return new

    def __repr__(self) -> str:
        return "<em.extensions: install, list, enable from disk and from repositories, update>"
