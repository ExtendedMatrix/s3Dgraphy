"""Community packages — EM Profiles 0.2 — read by every EM tool through this library.

MICRO-PL03-PROFILI-LIBRERIA, row W1 of the extensions plan (E.D., 18 Nov 2026).
A community does not change the units of EM: it changes what it records of
them and how it reads them — its qualia and vocabularies, its extractors with
their 3D component, its combiners, documents and file types, its form, its
colours, its words. The package says all of that in data, without code
(SPEC-pacchetto §1; «Pacchetto di comunità» in the interface, «EM Profile» in
the specification, D-4). This module does three things and nothing else
(SPEC-pacchetto §4):

1. **load and validate** a package — :func:`validate`, :func:`open_package`:
   the schema of its ``profile_format`` (0.1 and 0.2, shipped here in
   ``schema/``) and the coherence checks of ``vocabularies/tests/
   test_profiles.py`` brought into the library, so every tool checks the same
   way; the envelope ``em-extension.toml`` (``[data]``/``[code]``, partition,
   ``[requires]``, carried vocabularies);
2. build an **overlay** — :class:`ProfileOverlay`: the package's types,
   prefixed, BESIDE the core's;
3. expose **merged views** — :func:`qualia_types`, :func:`extractor_types`,
   :func:`combiner_types`, :func:`document_types`, :func:`file_types`…

And the machine folder (``~/.s3dgraphy/profiles``, ``S3DGRAPHY_PROFILES_DIR``)
with its ``index.local.json`` (:func:`install`, :func:`installed`,
:func:`find`, :func:`remove`); the em.json importer activates the packages of
``header.profiles`` (:func:`activate`, ``Container.profiles``) and the
exporter writes ``header.profiles`` (:func:`declare`, REPORT G6).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Union

from .core import (ORIGIN_CORE, core_document_types, core_edge_types, core_extractor_types,
                   core_node_types, core_qualia, core_versions)
from .overlay import EMPTY, Profile, ProfileOverlay, pick_label
from .package import (BUILTIN_READERS, ENVELOPE, EXECUTABLE_SUFFIXES, FORMATS, OPERATIONS,
                      PRIMITIVE_PRODUCES, PROFILE_FILE, Package, content_digest, open_package,
                      own_types, schema_for, validate, validate_envelope, validate_profile)
from .problems import ERROR, MESSAGES, WARNING, Problem, ProfileError, Report
from .semver import satisfies, valid_range
from .store import (ENV_VAR, INDEX_FILE, activate, compile_index, declare, find, install, installed,
                    prefixes_used, profiles_dir, read_index, remove)

Active = Union[None, ProfileOverlay, list, tuple]


def overlay(active: Active = None) -> ProfileOverlay:
    """An overlay from what a caller has: None (the core alone), an overlay,
    or the ``header.profiles`` of a document (activated now)."""
    if active is None:
        return EMPTY
    if isinstance(active, ProfileOverlay):
        return active
    return activate(active)[0]


def load(source: Any) -> Profile:
    """Read and validate a package from a folder, zip or bytes; raises
    :class:`ProfileError` (with the report) when it has errors. The profile
    is read from the source (``root`` is set only for a folder)."""
    import json
    import tempfile
    from pathlib import Path
    pkg = open_package(source)
    report = validate(pkg)
    if not report.ok:
        raise ProfileError("; ".join(str(p) for p in report.errors), report)
    if pkg.source.dir is not None:
        root = pkg.source.dir / pkg.data_root if pkg.data_root else pkg.source.dir
        return Profile.from_folder(root, digest=content_digest(pkg))
    # a zip: read its landmark sets now, the rest stays in the manifest
    prof = Profile(manifest=dict(pkg.profile or {}), digest=content_digest(pkg))
    for ls in prof.items("landmark_sets"):
        try:
            prof.landmarks[str(ls["id"])] = json.loads(pkg.source.read(pkg.data_file(ls["path"])).decode("utf-8"))
        except Exception:  # noqa: BLE001 — validated above; a race is not worth a crash
            pass
    return prof


def qualia_types(active: Active = None) -> Dict[str, Dict[str, Any]]:
    return overlay(active).qualia_types()


def extractor_types(active: Active = None) -> Dict[str, Dict[str, Any]]:
    return overlay(active).extractor_types()


def document_types(active: Active = None) -> Dict[str, Dict[str, Any]]:
    return overlay(active).document_types()


def combiner_types(active: Active = None) -> Dict[str, Dict[str, Any]]:
    return overlay(active).combiner_types()


def file_types(active: Active = None) -> Dict[str, Dict[str, Any]]:
    return overlay(active).file_types()


def landmark_sets(active: Active = None) -> Dict[str, Dict[str, Any]]:
    return overlay(active).landmark_sets()


def label(type_id: str, lang: str = "en", active: Active = None) -> Optional[str]:
    return overlay(active).label(type_id, lang)


__all__ = [
    "ORIGIN_CORE", "ENV_VAR", "INDEX_FILE", "PROFILE_FILE", "ENVELOPE", "FORMATS", "OPERATIONS",
    "PRIMITIVE_PRODUCES", "BUILTIN_READERS", "EXECUTABLE_SUFFIXES", "ERROR", "WARNING", "MESSAGES",
    "Problem", "Report", "ProfileError", "Package", "Profile", "ProfileOverlay", "EMPTY",
    "open_package", "validate", "validate_profile", "validate_envelope", "schema_for", "own_types",
    "content_digest", "load", "overlay", "pick_label",
    "profiles_dir", "install", "installed", "find", "remove", "compile_index", "read_index",
    "activate", "declare", "prefixes_used", "satisfies", "valid_range",
    "qualia_types", "extractor_types", "document_types", "combiner_types", "file_types", "landmark_sets", "label",
    "core_node_types", "core_edge_types", "core_qualia", "core_extractor_types", "core_document_types",
    "core_versions",
]
