"""The core a package extends, read live from this library's datamodel.

``vocabularies/profiles/core-types.json`` was GENERATED from s3Dgraphy so that
the tests of that repository could check a ``specializes``; inside the library
the same lists are read from the source (``node_registry.generated.json``,
the connections datamodel), so they cannot lag behind it. The flat tables of
qualia, extractor and document types are the core half of the merged views
(:mod:`s3dgraphy.profiles.overlay`): every entry carries ``origin: "core"``.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, FrozenSet

ORIGIN_CORE = "core"


def _json(name: str) -> Dict[str, Any]:
    from ..datamodel import JSON_CONFIG
    return json.loads((JSON_CONFIG / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def core_node_types() -> FrozenSet[str]:
    reg = _json("node_registry.generated.json")
    return frozenset(v["node_type"] for v in (reg.get("node_types") or {}).values()
                     if isinstance(v, dict) and v.get("node_type") not in (None, "None", "unknown"))


@lru_cache(maxsize=1)
def core_edge_types() -> FrozenSet[str]:
    return frozenset((_json("s3Dgraphy_connections_datamodel.json").get("edge_types") or {}).keys())


@lru_cache(maxsize=1)
def core_versions() -> Dict[str, str]:
    """``{nodes, connections, qualia}`` — what ``datamodel_checked`` is compared with."""
    from ..datamodel import datamodel_fingerprint
    v = datamodel_fingerprint().get("versions") or {}
    return {k: str(v[k]) for k in ("nodes", "connections", "qualia") if v.get(k)}


def _flat_subtypes(doc: Dict[str, Any], key: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for cat_id, cat in (doc.get(key) or {}).items():
        if not isinstance(cat, dict):
            continue
        for sub_id, sub in (cat.get("subtypes") or {}).items():
            if isinstance(sub, dict):
                out[str(sub.get("id") or sub_id)] = dict(sub, category=cat_id, origin=ORIGIN_CORE)
    return out


@lru_cache(maxsize=1)
def _core_qualia() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    doc = _json("em_qualia_types.json")
    for cat in doc.get("qualia_categories") or []:
        for sub_id, sub in ((cat or {}).get("subcategories") or {}).items():
            for q in (sub or {}).get("qualia") or []:
                if isinstance(q, dict) and q.get("id"):
                    out[str(q["id"])] = dict(q, category=cat.get("id"), subcategory=sub_id, origin=ORIGIN_CORE)
    return out


def core_qualia() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in _core_qualia().items()}


@lru_cache(maxsize=1)
def core_property_names() -> FrozenSet[str]:
    """Property names in use that are not a quale (``property_names``), lower-cased."""
    names = _json("em_qualia_types.json").get("property_names") or {}
    return frozenset(k.lower() for k in names if not k.startswith("_"))


def is_core_quale(name: str) -> bool:
    n = str(name or "")
    return n in _core_qualia() or n.lower() in {k.lower() for k in _core_qualia()} or n.lower() in core_property_names()


@lru_cache(maxsize=1)
def _core_extractors() -> Dict[str, Dict[str, Any]]:
    return _flat_subtypes(_json("em_extractor_types.json"), "extractor_types")


def core_extractor_types() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in _core_extractors().items()}


@lru_cache(maxsize=1)
def _core_documents() -> Dict[str, Dict[str, Any]]:
    return _flat_subtypes(_json("em_document_types.json"), "document_types")


def core_document_types() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in _core_documents().items()}


@lru_cache(maxsize=1)
def core_document_ids() -> FrozenSet[str]:
    doc = _json("em_document_types.json").get("document_types") or {}
    return frozenset(set(_core_documents()) | set(doc))


__all__ = ["ORIGIN_CORE", "core_node_types", "core_edge_types", "core_versions", "core_qualia",
           "core_property_names", "is_core_quale", "core_extractor_types", "core_document_types",
           "core_document_ids"]
