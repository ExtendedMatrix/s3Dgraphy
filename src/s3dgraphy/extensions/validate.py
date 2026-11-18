"""The validator of an archive — the same for the Extensions window, the
command line and the CI (W19).

``python -m s3dgraphy.extensions validate`` is what ``blender --command
extension validate`` is for Blender: the curator checks a folder or a zip
without opening EMStudio, and gets the same words the window would show
before installing (:func:`s3dgraphy.extensions.preview` calls
:func:`validate_archive` too).

It is the library of the community packages' validator
(:func:`s3dgraphy.profiles.validate`: the envelope, the partition, the
profile, the vocabularies carried with their tier against their licence,
``[requires]``, ``[code]``) plus what concerns the archive as a thing to
distribute:

* the ``[code]`` wheels are in the archive and are named as wheels; every
  declared platform has a wheel of every distribution; platform wheels with
  no ``platforms`` said out loud; the code root exists;
* what ``build`` would fix, said as a warning: no ``type``, a vocabulary
  file still named in ``qualia_vocabularies[].path``, a bare profile without
  ``em-extension.toml``.

Nothing here depends on the machine: the platform of THIS machine, what is
installed, the trust — those are the installer's (W21).
"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Set

from ..profiles.package import ENVELOPE, Package, open_package, validate
from ..profiles.problems import ProfileError, Report
from .wheels import PLATFORMS, is_wheel_name, wheel_dist, wheel_platforms

#: the archive checks about the code section alone (the data go in all the same, SPEC-pacchetto §16.3)
ARCHIVE_CODE_PROBLEMS = ("code_wheel_missing", "code_wheel_name", "code_platform_unknown", "code_platform_wheel",
                         "code_outside_root")


def _code_archive(pkg: Package, r: Report) -> None:
    c = (pkg.envelope or {}).get("code")
    if not isinstance(c, Mapping):
        return
    root = (pkg.code_root or "").rstrip("/")
    files = set(pkg.source.files())
    if root and not any(f.startswith(root + "/") for f in files):
        r.error("code_outside_root", ENVELOPE, root=pkg.code_root)
    wheels = [str(w) for w in (c.get("wheels") or [])]
    for w in wheels:
        try:
            rel = pkg.source.norm(str(PurePosixPath(root) / w) if root else w)
        except ProfileError:
            rel = None
        if rel not in files:
            r.error("code_wheel_missing", ENVELOPE, path=w)
        elif not is_wheel_name(w):
            r.error("code_wheel_name", ENVELOPE, path=w)
    plats = c.get("platforms")
    declared: List[str] = [str(p) for p in plats] if isinstance(plats, list) else []
    for p in declared:
        if p not in PLATFORMS:
            r.error("code_platform_unknown", ENVELOPE, value=p, known=", ".join(PLATFORMS))
    by_dist: Dict[str, List[Optional[Set[str]]]] = {}
    for w in wheels:
        if is_wheel_name(w):
            by_dist.setdefault(wheel_dist(w), []).append(wheel_platforms(w))
    for dist, plist in sorted(by_dist.items()):
        if any(p is None for p in plist):
            continue  # a pure wheel runs everywhere
        for p in declared:
            if p in PLATFORMS and not any(p in x for x in plist):
                r.error("code_platform_wheel", ENVELOPE, platform=p, dist=dist)
    if not declared:
        bound = sorted(d for d, plist in by_dist.items() if all(p is not None for p in plist))
        if bound:
            r.warn("code_platforms_undeclared", ENVELOPE, dists=", ".join(bound))


def _build_would_fix(pkg: Package, r: Report) -> None:
    env = pkg.envelope
    if env is None:
        if ENVELOPE not in pkg.source.files():  # an unreadable envelope is said already
            r.warn("bare_profile")
        return
    if env.get("type") is None and (pkg.has_data or pkg.has_code):
        r.warn("type_missing", ENVELOPE, want=pkg.kind)
    if pkg.has_data:
        for q in (pkg.profile or {}).get("qualia_vocabularies") or []:
            if isinstance(q, Mapping) and q.get("path"):
                r.warn("vocab_path_in_profile", pkg.profile_path or "", scheme=q.get("scheme"))


def validate_archive(source: Any) -> Report:
    """Everything wrong with an archive (folder, zip, bytes or an opened
    :class:`~s3dgraphy.profiles.package.Package`), at once, errors and
    warnings, every sentence in English and Italian."""
    if isinstance(source, Package):
        pkg = source
    else:
        try:
            pkg = open_package(source)
        except ProfileError as exc:
            r = Report()
            r.error("not_a_package" if "not a package" in str(exc) else "unreadable", why=str(exc))
            return r
    r = validate(pkg)
    _build_would_fix(pkg, r)
    _code_archive(pkg, r)
    return r


__all__ = ["ARCHIVE_CODE_PROBLEMS", "validate_archive"]
