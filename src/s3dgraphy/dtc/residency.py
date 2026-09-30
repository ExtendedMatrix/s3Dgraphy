"""DTC residency: detach ↔ inject ↔ bake (pure ops, R3).

A DTC = a ``DTCProcessNode`` plus its chain of **Resource** LinkNodes, wired by
``dtc_had_input`` (process → input), ``dtc_had_output`` (process → output) and
``dtc_derived_from`` (output → input). Resources are referenced by their **stable
ID** (= the ResourceNode UUID, :func:`s3dgraphy.resources.stable_resource_id`).

  * :func:`detach_dtc` extracts a DTC into a standalone JSON record (the
    "resident-with-data" form) keyed by resource stable IDs + kinds. Read-only —
    the graph is untouched, so a DTC already living in em.json keeps working.
  * :func:`inject_dtc` re-creates a DTC into a graph from a record. Everything it
    creates is tagged ``injected_by`` (temporary), reusing the aux-lifecycle
    convention; resources already present (by stable ID) are reused, not
    duplicated.
  * :func:`bake_dtc` promotes an injected DTC to persistent (drops the
    ``injected_by`` tag), i.e. ``bake → em.json`` — the explicit export.

No web framework; heavy deps are never imported here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

DTC_RECORD_VERSION = 1

PROCESS_TYPE = "dtc_process"
RESOURCE_TYPE = "resource"

# role → the DTC chain edge (structural constants of the profile — verified in the
# connections datamodel by the tests). input and output are BOTH Process→ResourceNode
# edges, so the role IS the edge type (a node-pair lookup would be ambiguous).
EDGE_HAD_INPUT = "dtc_had_input"        # Process → input Resource
EDGE_HAD_OUTPUT = "dtc_had_output"      # Process → output Resource
EDGE_DERIVED_FROM = "dtc_derived_from"  # output Resource → input Resource


def dtc_injector_id(process_id: str) -> str:
    """The conventional injector id for a DTC keyed on its process's stable id —
    ``"DTC:<process_id>"`` (matches the ``"<kind>:<id>"`` aux-lifecycle form)."""
    return f"DTC:{process_id}"


def _data(node: Any) -> Dict[str, Any]:
    d = getattr(node, "data", None)
    return d if isinstance(d, dict) else {}


def _resource_ids(graph: Any, process_id: str, edge_type: str) -> List[str]:
    return [e.edge_target for e in graph.edges
            if e.edge_type == edge_type and e.edge_source == process_id]


def _resource_record(graph: Any, res_id: str, role: str) -> Dict[str, Any]:
    """One resource, keyed by its **stable ID**, with its kind + locator."""
    from ..resources import stable_resource_id
    n = graph.find_node_by_id(res_id)
    d = _data(n) if n is not None else {}
    return {
        "id": stable_resource_id(n) if n is not None else res_id,
        "role": role,
        "dtc_kind": d.get("dtc_kind"),
        "resource_type": d.get("resource_type"),
        "url": d.get("url", ""),
        "name": str(getattr(n, "name", "") or "") if n is not None else "",
    }


# ── detach ──────────────────────────────────────────────────────────────────────
def detach_dtc(graph: Any, process_id: str) -> Dict[str, Any]:
    """Extract the DTC anchored on ``process_id`` into a standalone JSON record.

    Read-only: the graph is not mutated (the DTC keeps living in em.json until the
    caller chooses to strip it). Resources are recorded by **stable ID** + kind, so
    the record is graph-agnostic and reusable. Raises ``ValueError`` if
    ``process_id`` is not a DTC process node."""
    proc = graph.find_node_by_id(process_id)
    if proc is None or getattr(proc, "node_type", None) != PROCESS_TYPE:
        raise ValueError(f"{process_id!r} is not a DTC process node")

    input_ids = _resource_ids(graph, process_id, EDGE_HAD_INPUT)
    output_ids = _resource_ids(graph, process_id, EDGE_HAD_OUTPUT)

    resources: List[Dict[str, Any]] = []
    seen: set = set()
    for rid in input_ids:
        if rid not in seen:
            resources.append(_resource_record(graph, rid, "input"))
            seen.add(rid)
    for rid in output_ids:
        if rid not in seen:
            resources.append(_resource_record(graph, rid, "output"))
            seen.add(rid)

    # the chain edges, expressed purely by stable IDs (role-typed)
    edges: List[Dict[str, str]] = []
    for rid in input_ids:
        edges.append({"source": process_id, "target": rid, "type": EDGE_HAD_INPUT})
    for rid in output_ids:
        edges.append({"source": process_id, "target": rid, "type": EDGE_HAD_OUTPUT})
    for e in graph.edges:
        if e.edge_type == EDGE_DERIVED_FROM and e.edge_source in output_ids:
            edges.append({"source": e.edge_source, "target": e.edge_target,
                          "type": EDGE_DERIVED_FROM})

    return {
        "dtc_record_version": DTC_RECORD_VERSION,
        "process": {
            "id": process_id,
            "name": str(getattr(proc, "name", "") or ""),
            "description": str(getattr(proc, "description", "") or ""),
            "dtc_kind": _data(proc).get("dtc_kind"),
        },
        "resources": resources,
        "edges": edges,
    }


# ── inject ──────────────────────────────────────────────────────────────────────
def _ensure_edge(graph: Any, src: str, tgt: str, edge_type: str, injector_id: str):
    from ..transforms import mark_as_injected
    for e in graph.edges:
        if (e.edge_source == src and e.edge_target == tgt
                and e.edge_type == edge_type):
            return e  # already present — leave as-is (may be graph-native)
    e = graph.add_edge(f"{src}__{edge_type}__{tgt}", src, tgt, edge_type)
    mark_as_injected(e, injector_id)
    return e


def inject_dtc(graph: Any, record: Dict[str, Any], *,
               injector_id: Optional[str] = None) -> Dict[str, Any]:
    """Re-create a DTC from a :func:`detach_dtc` record into ``graph``.

    Nodes/edges this call CREATES are tagged ``injected_by`` (temporary); a
    resource or process already present (by stable ID) is REUSED, not duplicated
    (so a DTC injected onto a graph that already owns the resources just adds the
    provenance overlay). Returns
    ``{"injector_id", "process_id", "resource_ids", "created"}``."""
    from ..nodes import DTCProcessNode
    from ..resources.files import add_resource
    from ..transforms import mark_as_injected

    proc_rec = record["process"]
    pid = proc_rec["id"]
    injector_id = injector_id or dtc_injector_id(pid)
    created: List[str] = []

    # process node (adopt the recorded stable id)
    proc = graph.find_node_by_id(pid)
    if proc is None:
        proc = DTCProcessNode(pid, name=proc_rec.get("name") or "DTC process",
                              description=proc_rec.get("description") or "",
                              dtc_kind=proc_rec.get("dtc_kind"))
        graph.add_node(proc)
        mark_as_injected(proc, injector_id)
        created.append(pid)

    # resource LinkNodes (adopt stable ids; reuse if already present)
    resource_ids: List[str] = []
    for r in record.get("resources", []):
        rid = r["id"]
        resource_ids.append(rid)
        node = graph.find_node_by_id(rid)
        if node is None:
            node = add_resource(
                graph, resource_id=rid, name=r.get("name") or rid,
                files=[{"path": r["url"]}] if r.get("url") else [],
                data={k: r[k] for k in ("dtc_kind", "resource_type")
                      if r.get(k) is not None})
            mark_as_injected(node, injector_id)
            created.append(rid)

    # chain edges
    for e in record.get("edges", []):
        _ensure_edge(graph, e["source"], e["target"], e["type"], injector_id)

    return {
        "injector_id": injector_id,
        "process_id": pid,
        "resource_ids": resource_ids,
        "created": created,
    }


# ── bake ──────────────────────────────────────────────────────────────────────
def bake_dtc(graph: Any, injector_id: str) -> Dict[str, int]:
    """Promote an injected DTC to persistent (drop its ``injected_by`` tag) — the
    ``bake → em.json`` export. Thin wrapper over the scoped
    :func:`s3dgraphy.transforms.bake_injector`; returns its
    ``{"nodes", "edges", "overrides_cleared"}`` report."""
    from ..transforms import bake_injector
    return bake_injector(graph, injector_id)
