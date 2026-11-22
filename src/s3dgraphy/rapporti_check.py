"""Read back a pyArchInit export and say which «Copre» were an ``is_after``.

MICRO-LG7 (E.D., 22 Nov 2026). Until 1.6.0.dev138 s3Dgraphy wrote every
``is_after`` between two US/USM into ``us_table.rapporti`` as «Copre» (and
the yEd pipeline wrote EVERY line between two US so): a fact of time became a
fact of the ground, and pyArchInit's export read it back as ``overlies``.
:mod:`s3dgraphy.rapporti` no longer does it; what was already written stays.

From the row alone a «Copre» born of an ``is_after`` cannot be told from a
true one. The proof is the ORIGIN GRAPH (the em.json, or a GraphML with the
``_s3d_physical_relations`` channel), matched to the rows by
``us_table.node_uuid``. This module only READS and REPORTS: nothing is
corrected, nothing is written — a correction is a decision of whoever owns
the data.

Findings (``kind``):

* ``copre_from_is_after`` — a «Copre» / «Coperto da» (any language) whose pair
  has, in the origin graph, an ``is_after`` in that direction and no physical
  cover of its own: the spurious ones.
* ``copre_verified`` — the pair has a physical cover in the origin graph: true.
* ``copre_not_in_origin`` — neither: written by hand in pyArchInit, or the
  origin graph changed since. Said, not judged.
* ``unverifiable`` — a row (or its target) without a ``node_uuid`` the origin
  graph knows: the provenance does not allow the check.
* ``raw_edge_name`` — a voice that is the raw name of an edge (``is_before``,
  ``changed_from``…), written by an older s3Dgraphy and dropped by every
  reader.
* ``arrow_to_missing_row`` — a ``>>`` / ``<<`` towards a name that is no row of
  the site (an activity, an author: the old black list let them out).
* ``contaminated_overlies`` — in the origin graph itself, an ``overlies``
  edge re-projected from the DB (id ``rap_…``) beside an ``is_after`` of the
  same pair and no physical cover of origin: the spurious «Copre» came back
  into the graph.

Each finding says ``hint`` too when the row's text says who wrote it: a
JSON list with double quotes is the yEd pipeline's (``json.dumps``; there
EVERY «Copre» is suspect, the line style was never read), a Python literal
with single quotes the GraphIngestor's.

CLI::

    python -m s3dgraphy.rapporti_check --db site.sqlite --graph site.em.json [--sito NAME] [--json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any, Dict, Iterable, List, Optional

from .rapporti import RAPPORTI_TO_EDGE_TYPE, _coerce_to_list

_COVER = {"overlies": False, "is_overlain_by": True}     # name → swap


def _writer_hint(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    t = raw.strip()
    if t.startswith('[["') or t.startswith('[ ["'):
        return "yed_pipeline"
    if t.startswith("[['") or t.startswith("[ ['"):
        return "graph_ingestor"
    return None


def rows_from_sqlite(path: str, sito: Optional[str] = None) -> List[Dict[str, Any]]:
    """The ``us_table`` rows of a pyArchInit SQLite DB, read-only
    (``mode=ro``)."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(us_table)")}
        want = [c for c in ("sito", "area", "us", "unita_tipo", "rapporti", "node_uuid") if c in cols]
        sql = f"SELECT {', '.join(want)} FROM us_table"
        args: tuple = ()
        if sito is not None and "sito" in cols:
            sql += " WHERE sito = ?"
            args = (sito,)
        return [dict(zip(want, r)) for r in con.execute(sql, args)]
    finally:
        con.close()


def _edge_pairs(graph):
    """``{(src, dst): {edge_type: [edge_id…]}}`` with the reverses turned to
    their canonical reading (``is_overlain_by`` → ``overlies`` swapped,
    ``is_before`` → ``is_after`` swapped)."""
    flip = {"is_overlain_by": "overlies", "is_before": "is_after"}
    out: Dict[tuple, Dict[str, List[str]]] = {}
    for e in getattr(graph, "edges", None) or []:
        et = e.edge_type
        s, t = e.edge_source, e.edge_target
        if et in flip:
            et, s, t = flip[et], t, s
        if et not in ("overlies", "is_after"):
            continue
        out.setdefault((s, t), {}).setdefault(et, []).append(str(e.edge_id))
    return out


def check_rapporti(rows: Iterable[Dict[str, Any]], graph) -> List[Dict[str, Any]]:
    """The findings of the module docstring, one dict each: ``kind``,
    ``row`` (sito/area/us of the row that carries the voice), ``voice``,
    ``target``, ``pair`` (origin node ids, the cover's upper unit first) when
    known, ``hint``, ``note``. Read-only."""
    rows = list(rows)
    known = {n.node_id for n in graph.nodes}
    pairs = _edge_pairs(graph)
    edge_names = set()
    try:
        from .edges.connections_loader import get_connections_datamodel
        edge_names = set(get_connections_datamodel()._expanded_edges)
    except Exception:                                  # noqa: BLE001
        pass
    by_us_area: Dict[tuple, Dict[str, Any]] = {}
    by_us: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        us = str(r.get("us") or "").strip()
        by_us_area[(us, str(r.get("area") or "").strip())] = r
        by_us.setdefault(us, []).append(r)

    def target_row(us, area):
        r = by_us_area.get((us, area))
        if r is not None:
            return r
        same = by_us.get(us) or []
        return same[0] if len(same) == 1 else None

    out: List[Dict[str, Any]] = []
    for r in rows:
        hint = _writer_hint(r.get("rapporti"))
        where = {k: r.get(k) for k in ("sito", "area", "us", "unita_tipo")}
        for entry in _coerce_to_list(r.get("rapporti")):
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            voice = str(entry[0] or "").strip()
            tus = str(entry[1] or "").strip()
            tarea = str(entry[2]).strip() if len(entry) > 2 and entry[2] is not None else ""
            base = {"row": where, "voice": voice, "target": tus, "hint": hint}
            if voice in edge_names and voice.lower() not in RAPPORTI_TO_EDGE_TYPE:
                out.append({**base, "kind": "raw_edge_name",
                            "note": "the raw name of an edge: no reader takes it"})
                continue
            tr = target_row(tus, tarea)
            if voice in (">>", "<<") and tr is None:
                out.append({**base, "kind": "arrow_to_missing_row",
                            "note": "a paradata arrow towards a name that is no row of the site"})
                continue
            et = RAPPORTI_TO_EDGE_TYPE.get(voice.lower())
            if et not in _COVER:
                continue
            src = str(r.get("node_uuid") or "")
            dst = str((tr or {}).get("node_uuid") or "")
            if not src or not dst or src not in known or dst not in known:
                out.append({**base, "kind": "unverifiable",
                            "note": "row or target without a node_uuid the origin graph knows"})
                continue
            upper, lower = (dst, src) if _COVER[et] else (src, dst)
            found = pairs.get((upper, lower), {})
            true_cover = [i for i in found.get("overlies", []) if not i.startswith("rap_")]
            if true_cover:
                kind, note = "copre_verified", "a physical cover of origin"
            elif found.get("is_after"):
                kind, note = ("copre_from_is_after",
                              "the origin graph says only «later than» (is_after) for this pair")
            else:
                kind, note = ("copre_not_in_origin",
                              "neither a cover nor an is_after in the origin graph")
            out.append({**base, "kind": kind, "pair": [upper, lower], "note": note})
    # (b) the contamination already back in the graph
    for (s, t), kinds in pairs.items():
        rap = [i for i in kinds.get("overlies", []) if i.startswith("rap_")]
        own = [i for i in kinds.get("overlies", []) if not i.startswith("rap_")]
        if rap and kinds.get("is_after") and not own:
            out.append({"kind": "contaminated_overlies", "pair": [s, t], "edges": rap,
                        "note": "an overlies re-projected from the DB beside an is_after of origin"})
    return out


def summary(findings: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for f in findings:
        out[f["kind"]] = out.get(f["kind"], 0) + 1
    return out


def _load_graph(path: str):
    if path.lower().endswith((".graphml", ".xml")):
        from .graph import Graph
        from .importer.import_graphml import GraphMLImporter
        g = Graph("origin")
        GraphMLImporter(path, g).parse()
        return g
    from .container import parse_container
    with open(path, encoding="utf-8") as fh:
        c, _w = parse_container(json.load(fh))
    return c.graphs[c.active_graph_id]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m s3dgraphy.rapporti_check",
        description="Read a pyArchInit us_table and its origin graph; list the «Copre» "
                    "that were an is_after. Read-only: nothing is corrected.")
    ap.add_argument("--db", required=True, help="pyArchInit SQLite DB (opened read-only)")
    ap.add_argument("--graph", required=True, help="the origin graph (em.json or GraphML)")
    ap.add_argument("--sito", help="only the rows of this site")
    ap.add_argument("--json", action="store_true", help="the findings as JSON")
    a = ap.parse_args(argv)
    findings = check_rapporti(rows_from_sqlite(a.db, a.sito), _load_graph(a.graph))
    if a.json:
        json.dump({"summary": summary(findings), "findings": findings}, sys.stdout,
                  ensure_ascii=False, indent=1)
        print()
    else:
        for f in findings:
            row = f.get("row") or {}
            print(f"{f['kind']:24} {row.get('unita_tipo') or ''}{row.get('us') or ''} "
                  f"{f.get('voice') or ''} {f.get('target') or ''}  — {f['note']}"
                  + (f"  [{f['hint']}]" if f.get("hint") else ""))
        print("summary:", summary(findings))
    return 0


if __name__ == "__main__":                              # pragma: no cover
    raise SystemExit(main())
