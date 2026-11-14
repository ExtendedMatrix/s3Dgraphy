"""The ROLE of a file or a set in its group — a controlled vocabulary the user
can extend (E.D. 14 Nov 2026, MICRO-B-DOCUMENTI-MEDIA §1).

The base concepts are the SKOS module ``em-media-role`` of
stratigraph-templates (``vocabularies/skos/media-role.ttl``, origin
``originated``): this tuple is its mirror, and ``tests/test_media_sets.py``
checks the two are the same when the checkout is next door.

WHERE THE ROLE LIVES. On the set or on the file node, as ``data.media_role``
— beside ``kind`` / ``media_type``, which already say what a resource IS. Not
on the edge: a role says what the group IS FOR in the study (the photographs
of a photogrammetry, the frontispiece), and the same set seen from the unit,
from the catalogue and from the viewer is the same set with the same role.
An edge would let one set be «frontispiece» from one side and «detail» from
the other, which is two sets, not one.

THE USER'S TERMS. A term the base does not have is added to the PROJECT
(``data.media_roles_local`` of the graph node), with who added it and when:
``local:<slug>``, never in the base namespace. Traced, so a term that turns
out to be shared by many projects can be proposed to the base module.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional

NAMESPACE = "https://w3id.org/extendedmatrix/vocab/media-role/"

#: (id, it, en) — the base concepts, in the order the interface lists them
BASE_ROLES = (
    ("photogrammetry", "fotogrammetria", "photogrammetry"),
    ("frontispiece", "frontespizio", "frontispiece"),
    ("detail", "dettaglio", "detail"),
    ("vector_drawing", "disegno vettoriale", "vector drawing"),
    ("raster_drawing", "disegno raster", "raster drawing"),
    ("model_3d", "modello 3D", "3D model"),
    ("orthophoto", "ortofoto", "orthophoto"),
    ("archival_documentation", "documentazione d'archivio", "archival documentation"),
)
BASE_IDS = tuple(r[0] for r in BASE_ROLES)
#: the role whose image the Inspector and the viewer show first
FRONTISPIECE = "frontispiece"
LOCAL_PREFIX = "local:"


def _graph_node(graph):
    return next((n for n in getattr(graph, "nodes", []) or []
                 if getattr(n, "node_type", "") == "graph"), None)


def local_roles(graph) -> List[Dict[str, Any]]:
    g = _graph_node(graph)
    rows = (getattr(g, "data", None) or {}).get("media_roles_local") if g is not None else None
    return [r for r in rows or [] if isinstance(r, dict) and r.get("id")]


def roles(graph=None) -> List[Dict[str, Any]]:
    """Every role a project can use: ``[{id, uri, label: {it, en}, origin}]``,
    the base first (``origin: base``), then the project's (``origin: local``,
    with ``added_by`` / ``added_at``)."""
    out = [{"id": i, "uri": NAMESPACE + i, "label": {"it": it, "en": en}, "origin": "base"}
           for i, it, en in BASE_ROLES]
    for r in local_roles(graph) if graph is not None else []:
        out.append({"id": r["id"], "uri": None, "label": dict(r.get("label") or {}),
                    "origin": "local", "added_by": r.get("added_by"),
                    "added_at": r.get("added_at"), "definition": r.get("definition")})
    return out


def check_role(graph, role_id: str) -> str:
    """``role_id`` if the project knows it, else ValueError."""
    if role_id in BASE_IDS or any(r["id"] == role_id for r in local_roles(graph)):
        return role_id
    raise ValueError(f"unknown media role {role_id!r}: one of {list(BASE_IDS)} or a "
                     f"term of the project (add_local_role)")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")
    return s or "role"


def add_local_role(graph, label: str, *, lang: str = "it", by: Optional[str] = None,
                   at: Optional[str] = None, definition: Optional[str] = None) -> str:
    """A term of the PROJECT: ``local:<slug of the label>``, kept on the graph
    node with who and when. The same label twice is the same term. Returns its
    id."""
    if not str(label or "").strip():
        raise ValueError("a role needs a label")
    rid = LOCAL_PREFIX + _slug(label)
    base = next((i for i, it, en in BASE_ROLES
                 if _slug(it) == _slug(label) or _slug(en) == _slug(label)), None)
    if base:
        return base
    g = _graph_node(graph)
    if g is None:
        raise ValueError("the graph has no graph node to keep the project's terms on")
    d = g.data if isinstance(getattr(g, "data", None), dict) else {}
    g.data = d
    rows = d.setdefault("media_roles_local", [])
    if any(r.get("id") == rid for r in rows if isinstance(r, dict)):
        return rid
    row = {"id": rid, "label": {lang: str(label).strip()},
           "added_at": at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if by:
        row["added_by"] = by
    if definition:
        row["definition"] = definition
    rows.append(row)
    return rid


def label_of(graph, role_id: Optional[str], lang: str = "it") -> str:
    if not role_id:
        return ""
    for r in roles(graph):
        if r["id"] == role_id:
            return r["label"].get(lang) or r["label"].get("en") or next(iter(r["label"].values()), role_id)
    return role_id
