"""The pyArchInit row of a unit, read from the GRAPH — its nodes and edges —
and not from ``node.data`` (MICRO pyArchInit campi in nodi, 27 Nov 2026).

E.D.'s rule of the day: what a us_table row says about a unit is mapped as
nodes and edges, not as fields on the unit's node. In the unit's own data only
the technical keys stay (``node_uuid``). So the way back to pyArchInit
(:class:`GraphIngestor`, the GraphML writer) reads each column from where the
graph keeps it:

========================  =====================================================
column                    read from
========================  =====================================================
``us``                    the unit's NAME (``1.US12`` → ``12``)
``unita_tipo``            the CLASS (+ ``stratigraphic_kind``); the code it came
                          in with when that is not the class's own
                          (``source_code``: SU, WSU, USS…)
``area`` ``settore``      the places, ``is_in_location`` → ``LocationNodeGroup``
``saggio`` ``ambient``    (the place's ``level``, a key of em-place-level, says
``quad_par``              the column — ``quadrato`` → quad_par, ``ambiente`` →
                          ambient: :func:`place_columns`; else its id)
``d_stratigrafica``       the unit's ``description``
``d_interpretativa``      its properties, ``has_property`` → ``PropertyNode``
``attivita`` ``struttura``  (the property name of the mapping)
``documentazione``        the per-unit documents of the checklist,
                          ``has_documentation`` → ``<unit>_doc_<label>``
``doc_usv``               the file document (``doc::path::<path>``) — or, for a
                          DOC row, the document's own ``url``
``periodo_iniziale`` /    ``has_first_epoch`` → the epoch's periodo / fase
``fase_iniziale``
``periodo_finale`` /      ``survive_in_epoch`` → the latest such epoch
``fase_finale``
``schedatore``            the PERSONS (27 Nov 2026, MICRO ruoli persone): the
``direttore_us``          author of the unit's act, ``is_in_activity`` →
``responsabile_us``       ``ActivityNodeGroup`` (``act_kind`` recording /
                          excavation / revision) ``has_author`` → the person;
                          a role the act does not say is ``attributes.role``
                          on that edge (:func:`person_columns`)
========================  =====================================================

The EPOCH's own row of ``periodizzazione_table`` (27 Nov 2026, same rule) is
read from the EpochNode's fields — :func:`epoch_columns`: ``periodo`` /
``fase`` are its technical key (they stay in its data), ``cron_iniziale`` /
``cron_finale`` its ``start_time`` / ``end_time``, ``descrizione`` its
``name``, ``datazione_estesa`` its ``description``.

A value the graph does not have falls back to what an older graph carried in
``attributes`` / ``node.data`` (a GraphML hydrated by the ingestor, a file
written before this rule): the reading never loses what was there.

No SQL, no Qt: a pure reading of a graph.
"""
from __future__ import annotations

import ast
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: The place columns of us_table that the importer maps to LocationNodeGroup.
PLACE_COLUMNS: Tuple[str, ...] = ("area", "settore", "saggio", "ambient",
                                   "quad_par")

#: The place column of us_table → the ``level`` its place says in the graph,
#: the key of the vocabulary em-place-level (E.D., 27 Nov 2026: the graph
#: speaks EM, the column's name lives in the translation), as
#: pyarchinit_us_mapping 1.6.8 ships them. :func:`place_levels` reads the
#: mapping itself; this is the fallback when the mapping cannot be read.
PLACE_LEVELS: Dict[str, str] = {
    "area": "area",
    "settore": "settore",
    "saggio": "saggio",
    "quad_par": "quadrato",
    "ambient": "ambiente",
}

#: The us_table columns this module rebuilds from the graph.
ROW_COLUMNS: Tuple[str, ...] = (
    "us", "unita_tipo", "area", "settore", "saggio", "ambient", "quad_par",
    "d_stratigrafica", "d_interpretativa", "attivita", "struttura",
    "documentazione", "doc_usv",
    "periodo_iniziale", "fase_iniziale", "periodo_finale", "fase_finale",
    "schedatore", "direttore_us", "responsabile_us",
)

#: The person columns of us_table → (the act's kind, the role on the edge),
#: as pyarchinit_us_mapping 1.6.7 ships them. :func:`person_columns` reads the
#: mapping itself, so that changing a column's act or role there changes the
#: way back too; this is the fallback when the mapping cannot be read.
PERSON_COLUMNS: Dict[str, Tuple[str, Optional[str]]] = {
    "schedatore": ("recording", None),
    "direttore_us": ("excavation", None),
    "responsabile_us": ("revision", None),
}

def person_columns() -> Dict[str, Tuple[str, Optional[str]]]:
    """``{column: (act_kind, person_role)}`` of the person columns of the
    pyArchInit mapping the importer uses (``pyarchinit_us_mapping`` through
    the mapping registry, so a project's own copy counts): a column with
    ``node_type: AuthorNode`` and an ``act_kind``. The importer writes the
    person as the author of that act, with that role on the ``has_author``
    edge; the way back reads it from there. :data:`PERSON_COLUMNS` when the
    mapping cannot be read."""
    found: Dict[str, Tuple[str, Optional[str]]] = {}
    try:
        from .mappings import mapping_registry
        mapping = mapping_registry.load_mapping("pyarchinit_us_mapping",
                                                "pyarchinit") or {}
        for col, cfg in (mapping.get("column_mappings") or {}).items():
            if cfg.get("node_type") == "AuthorNode" and cfg.get("act_kind"):
                found[col] = (cfg["act_kind"], cfg.get("person_role") or None)
    except Exception:
        found = {}
    return found or dict(PERSON_COLUMNS)

def place_levels() -> Dict[str, str]:
    """``{column: level}`` of the place columns of the pyArchInit mapping
    the importer uses (``pyarchinit_us_mapping`` through the mapping
    registry, so a project's own copy counts): a column with ``node_type:
    LocationNodeGroup`` and a ``place_level``. :data:`PLACE_LEVELS` for a
    column the mapping does not say, or when it cannot be read."""
    found: Dict[str, str] = dict(PLACE_LEVELS)
    try:
        from .mappings import mapping_registry
        mapping = mapping_registry.load_mapping("pyarchinit_us_mapping",
                                                "pyarchinit") or {}
        for col, cfg in (mapping.get("column_mappings") or {}).items():
            if col in PLACE_COLUMNS and cfg.get("node_type") == "LocationNodeGroup" \
                    and cfg.get("place_level"):
                found[col] = str(cfg["place_level"])
    except Exception:
        pass
    return found


def place_columns(levels: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """``{level: column}``: the column a place of that ``level`` goes back
    to. A level that is a column's own name (``quad_par``, ``ambient``: a
    graph written before 27 Nov 2026 not yet migrated) reads as that
    column too."""
    out = {c: c for c in PLACE_COLUMNS}
    out.update({lv: c for c, lv in (levels or place_levels()).items()})
    return out


#: The keys an older graph wrote on the unit's node (projector up to 1.6.0
#: dev142, the em.json it saved): the columns above plus the copies that were
#: only display (``datazione_estesa``) or are rebuilt from edges
#: (``rapporti``). ``node_uuid`` is NOT here: it is the technical key that stays.
#: Nor are the person columns: no projector wrote them on the node.
LEGACY_ROW_KEYS: Tuple[str, ...] = tuple(
    c for c in ROW_COLUMNS if c not in PERSON_COLUMNS) + (
    "sito", "rapporti", "datazione_estesa", "documentazione")

#: Placeholder descriptions the importer writes when the row has none.
_EMPTY_DESCRIPTIONS = frozenset({"", "none", "pyarchinit element"})

#: Property columns of the mapping whose value the ingestor writes back. The
#: property name is the mapping's ``property_name`` (pyarchinit_us_mapping).
PROPERTY_COLUMNS: Dict[str, str] = {
    "d_interpretativa": "Interpretation",
    "attivita": "Activity",
    "struttura": "Structure",
}

#: The classes of the paradata rows of us_table (unita_tipo → class name).
PARADATA_CODE_TO_CLASS: Dict[str, str] = {
    "DOC": "DocumentNode",
    "Combinar": "CombinerNode",
    "Extractor": "ExtractorNode",
    "property": "PropertyNode",
}
PARADATA_CLASS_TO_CODE: Dict[str, str] = {v: k for k, v in PARADATA_CODE_TO_CLASS.items()}

#: pyArchInit codes that are NOT the EM code of the class they make
#: (27 Nov 2026, E.D.): a ``CON`` row is the EM continuity node, whose EM
#: code stays ``BR``. The row's code is kept in ``source_code`` and goes
#: back as it came.
NOT_EM_CODES: Dict[str, str] = {"CON": "BR"}


def keeps_source_code(node, code: Optional[str]) -> bool:
    """Whether a row's *code* is kept on its node as ``source_code``: when
    the class (and kind) do not say it back (a localized SU / SE / UE / ΣΜ,
    a code with no class — VA…), or when it is pyArchInit's own code and not
    the EM one (``CON`` for the EM ``BR``). Node datamodel 1.6.57."""
    if not code:
        return False
    return code in NOT_EM_CODES or row_code(node) != code

_EPOCH_ID = re.compile(r"^epoch_([^_]+)_(.+?)(_synthetic)?$")
_IMPORTER_EPOCH_ID = re.compile(r"^epoch::.*::([^:]*)::([^:]*)$")
_LOC_ID = re.compile(r"^loc::([^:]+)::")


def _bags(node) -> Iterable[dict]:
    for bag in (getattr(node, "attributes", None), getattr(node, "data", None)):
        if isinstance(bag, dict):
            yield bag


def legacy_value(node, key: str):
    """The value an older graph left on the node for *key* (attributes first,
    then ``node.data``), or ``None``."""
    for bag in _bags(node):
        v = bag.get(key)
        if v not in (None, ""):
            return v
    return None


def node_uuid_of(node) -> Optional[str]:
    """The row identity: ``node_uuid`` (the technical key), else the id."""
    v = legacy_value(node, "node_uuid")
    return str(v) if v else getattr(node, "node_id", None)


def is_row_born(node) -> bool:
    """A node born from a us_table row: it carries ``node_uuid``."""
    return bool(legacy_value(node, "node_uuid"))


def is_generated_document(node, graph_edges_by_target=None) -> bool:
    """The documents the importer GENERATES from a row's columns, which are
    not rows themselves: the checklist ones (``<unit>_doc_<label>``) and the
    file ones (``doc::path::<path>``)."""
    if type(node).__name__ != "DocumentNode" or is_row_born(node):
        return False
    nid = str(getattr(node, "node_id", "") or "")
    return nid.startswith("doc::path::") or "_doc_" in nid


def place_column(loc, columns: Optional[Dict[str, str]] = None) -> Optional[str]:
    """The us_table column a place stands for: its ``level`` (nodes 1.6.43;
    a key of em-place-level, :func:`place_columns`), else its group kind
    (pyArchInit's grouping dimension, the column's name), else the column
    in its id (``loc::<column>::…``). *columns*: :func:`place_columns`,
    when the caller reads many places."""
    columns = columns if columns is not None else place_columns()
    v = legacy_value(loc, "level")
    if v and str(v) in columns:
        return columns[str(v)]
    v = legacy_value(loc, "group_kind")
    if v and str(v) in PLACE_COLUMNS:
        return str(v)
    m = _LOC_ID.match(str(getattr(loc, "node_id", "") or ""))
    if m and m.group(1) in PLACE_COLUMNS:
        return m.group(1)
    return None


def epoch_key(epoch) -> Tuple[Optional[str], Optional[str]]:
    """``(periodo, fase)`` of an epoch written by the projector or the
    importer, or ``(None, None)`` (an epoch made in EMStudio has neither)."""
    periodo = legacy_value(epoch, "periodo")
    fase = legacy_value(epoch, "fase")
    if periodo is not None:
        return str(periodo), (str(fase) if fase is not None else "")
    nid = str(getattr(epoch, "node_id", "") or "")
    for rx in (_EPOCH_ID, _IMPORTER_EPOCH_ID):
        m = rx.match(nid)
        if m:
            return m.group(1), m.group(2)
    return None, None


def row_code(node) -> Optional[str]:
    """The ``unita_tipo`` a node goes back to pyArchInit with.

    The code it came in with (``source_code``) when the class still says
    that code — a US that came in as ``SU`` goes back ``SU``, a masonry US
    that came in as ``WSU`` goes back ``WSU``; then the kind's code (USM,
    USR); then the class's code (USVs, SF, CON, DOC, Combinar…)."""
    from .nodes.stratigraphic_node import unit_code
    from .rapporti import S3DGRAPHY_TYPE_TO_UNITA_TIPO, canonical_unita_tipo
    cls = type(node).__name__
    source = getattr(node, "source_code", None) or legacy_value(node, "source_code")
    kind_code = unit_code(node)
    class_code = (PARADATA_CLASS_TO_CODE.get(cls)
                  or S3DGRAPHY_TYPE_TO_UNITA_TIPO.get(cls))
    if source:
        source = str(source)
        if kind_code:
            # unit_code already honours a source_code of the same kind
            return kind_code
        if class_code and canonical_unita_tipo(source) == class_code:
            return source
        if class_code is None or cls == "StratigraphicNode":
            # a code the library has no class for (VA…): kept as it came
            return source
    if kind_code:
        return kind_code
    return class_code


def _year(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def epoch_columns(epoch) -> Dict[str, Any]:
    """The ``periodizzazione_table`` row of an epoch, read from the
    EpochNode's own fields (27 Nov 2026, E.D.: the rule of the units holds
    for the epochs too):

    - ``periodo`` / ``fase``: the technical key of the row, the only row
      fields kept in the epoch's data (or read from its id);
    - ``cron_iniziale`` / ``cron_finale``: ``start_time`` / ``end_time``
      (P82a / P82b), as whole years;
    - ``descrizione``: the ``name`` (P1);
    - ``datazione_estesa``: the ``description`` (P3_has_note), else the
      name.

    A value the fields do not have falls back to what an older graph
    carried in ``attributes`` / ``data`` (projector ≤ 1.6.0.dev143)."""
    out: Dict[str, Any] = {}
    p, f = epoch_key(epoch)
    if p is not None:
        out["periodo"], out["fase"] = p, f
    for col, field in (("cron_iniziale", "start_time"), ("cron_finale", "end_time")):
        year = _year(getattr(epoch, field, None))
        if year is None:
            year = _year(legacy_value(epoch, col))
        if year is not None:
            out[col] = year
    name = getattr(epoch, "name", None)
    if isinstance(name, str) and name.strip():
        out["descrizione"] = name
    desc = getattr(epoch, "description", None)
    if isinstance(desc, str) and desc.strip():
        out["datazione_estesa"] = desc
    else:
        old = legacy_value(epoch, "datazione_estesa")
        if old is not None:
            out["datazione_estesa"] = str(old)
        elif "descrizione" in out:
            out["datazione_estesa"] = out["descrizione"]
    return out


#: what an older projector wrote on an epoch besides its key
LEGACY_EPOCH_KEYS: Tuple[str, ...] = ("cron_iniziale", "cron_finale",
                                      "datazione_estesa")


def migrate_place_levels(graph) -> Dict[str, Any]:
    """A place a graph wrote before 27 Nov 2026 says its level with the
    pyArchInit column's name (``quad_par``), or says none (a room, kind
    functional: ``ambient``). The graph speaks EM (E.D., 27 Nov 2026): the
    level is the key of em-place-level (``quadrato``, ``ambiente``…,
    :func:`place_levels`). Read in memory, ONE warning; the next save
    writes the keys. A place with no level gets one only when its id or
    its group kind says its column (``loc::ambient::…``, ``group_kind:
    ambient``). Ids are not touched (``loc::<column>::…`` stays: an id is
    the stable identity of a place already published). Idempotent."""
    out: Dict[str, Any] = {"places": 0, "levels": {}, "warnings": []}
    levels = place_levels()
    for loc in list(getattr(graph, "nodes", None) or []):
        if type(loc).__name__ != "LocationNodeGroup":
            continue
        attrs = getattr(loc, "attributes", None)
        if not isinstance(attrs, dict):
            continue
        data = getattr(loc, "data", None)
        have = attrs.get("level")
        if have in (None, "") and isinstance(data, dict):
            have = data.get("level")
        col = None
        if have not in (None, ""):
            if str(have) in levels and levels[str(have)] != str(have):
                col = str(have)
        else:
            gk = attrs.get("group_kind")
            m = _LOC_ID.match(str(getattr(loc, "node_id", "") or ""))
            if gk in PLACE_COLUMNS:
                col = gk
            elif m and m.group(1) in PLACE_COLUMNS:
                col = m.group(1)
        if col is None:
            continue
        # where the place says it: an em.json read back keeps it in data
        if isinstance(data, dict) and "level" in data and "level" not in attrs:
            data["level"] = levels[col]
        else:
            attrs["level"] = levels[col]
        out["places"] += 1
        key = f"{have or '—'} → {levels[col]}"
        out["levels"][key] = out["levels"].get(key, 0) + 1
    if out["places"]:
        said = ", ".join(f"{k} {v}" for k, v in sorted(out["levels"].items()))
        out["warnings"].append(
            f"places written before 27 Nov 2026: their level is now the key "
            f"of em-place-level ({said}) — the next save writes them.")
    return out


def migrate_legacy_epoch_fields(graph) -> Dict[str, Any]:
    """An em.json written by pyArchInit's projector up to 1.6.0.dev143
    carries an epoch's row in its ``data``: ``cron_iniziale``,
    ``cron_finale``, ``datazione_estesa`` (the last one holding the
    ``descrizione`` column, the epoch's name). Read into the EpochNode's own
    fields — ``start_time`` / ``end_time`` when they are not set, the
    ``description`` when it is empty and the text is not the name — and
    dropped when the fields say them. ``periodo`` / ``fase`` stay: the
    technical key. A value the fields contradict stays, and is counted. ONE
    warning. Idempotent."""
    out: Dict[str, Any] = {"epochs": 0, "moved": {}, "kept": {}, "warnings": []}
    for ep in list(getattr(graph, "nodes", None) or []):
        if type(ep).__name__ != "EpochNode":
            continue
        bags = [b for b in _bags(ep) if any(k in b for k in LEGACY_EPOCH_KEYS)]
        if not bags:
            continue
        out["epochs"] += 1
        for bag in bags:
            for col, field in (("cron_iniziale", "start_time"),
                               ("cron_finale", "end_time")):
                if col not in bag:
                    continue
                year = _year(bag[col])
                have = getattr(ep, field, None)
                if year is not None and (have is None or (
                        _year(have) == 0 and year != 0)):
                    setattr(ep, field, float(year))
                    have = getattr(ep, field)
                if year is None or _year(have) == year:
                    bag.pop(col)
                    out["moved"][col] = out["moved"].get(col, 0) + 1
                else:
                    out["kept"][col] = out["kept"].get(col, 0) + 1
            if "datazione_estesa" in bag:
                text = str(bag["datazione_estesa"] or "")
                desc = str(getattr(ep, "description", "") or "")
                if text and text != str(getattr(ep, "name", "") or "") and not desc:
                    ep.description = text
                    desc = text
                if not text or text in (desc, str(getattr(ep, "name", "") or "")):
                    bag.pop("datazione_estesa")
                    out["moved"]["datazione_estesa"] = \
                        out["moved"].get("datazione_estesa", 0) + 1
                else:
                    out["kept"]["datazione_estesa"] = \
                        out["kept"].get("datazione_estesa", 0) + 1
    if out["epochs"]:
        said = ", ".join(f"{k} {v}" for k, v in sorted(out["moved"].items()))
        line = (f"periodizzazione fields in an epoch's data: {out['epochs']} "
                f"epoch(s) read into start_time / end_time / name / description "
                f"({said or 'nothing to move'})")
        if out["kept"]:
            line += "; left in data, the fields say otherwise: " + ", ".join(
                f"{k} {v}" for k, v in sorted(out["kept"].items()))
        out["warnings"].append(line + " — the next save writes the fields.")
    return out


class RowReader:
    """Reads the pyArchInit columns of the units of one graph.

    Build it once per graph (it indexes nodes and edges), then call
    :meth:`columns` per node."""

    def __init__(self, graph) -> None:
        self.graph = graph
        self.by_id: Dict[str, Any] = {}
        for n in getattr(graph, "nodes", None) or []:
            nid = getattr(n, "node_id", None)
            if nid:
                self.by_id[nid] = n
        self.out: Dict[str, List[Tuple[str, Any, Any]]] = {}
        #: (act_kind, role) → the person column (MICRO ruoli persone)
        self.person_of: Dict[Tuple[str, Optional[str]], str] = {
            v: k for k, v in person_columns().items()}
        #: level → place column (27 Nov 2026, the keys of em-place-level)
        self.place_column_of: Dict[str, str] = place_columns()
        for e in getattr(graph, "edges", None) or []:
            tgt = self.by_id.get(getattr(e, "edge_target", None))
            if tgt is None:
                continue
            self.out.setdefault(e.edge_source, []).append((e.edge_type, tgt, e))

    def is_layer_document(self, node) -> bool:
        """The document the footprint reader hangs on a pyArchInit GIS layer
        (``has_linked_resource`` → a resource whose source is pyarchinit):
        made by the import, not a row."""
        if type(node).__name__ != "DocumentNode" or is_row_born(node):
            return False
        for _t in self._targets(node, "has_linked_resource"):
            if legacy_value(_t, "source") == "pyarchinit":
                return True
        return False

    # ------------------------------------------------------------ pieces
    def _targets(self, node, edge_type: str, cls: Optional[str] = None):
        for et, tgt, _e in self.out.get(getattr(node, "node_id", None), ()):
            if et == edge_type and (cls is None or type(tgt).__name__ == cls):
                yield tgt

    def places(self, node) -> Dict[str, str]:
        found: Dict[str, str] = {}
        for loc in self._targets(node, "is_in_location", "LocationNodeGroup"):
            col = place_column(loc, self.place_column_of)
            if col and col not in found:
                name = str(getattr(loc, "name", "") or "").strip()
                if name:
                    found[col] = name
        return found

    def properties(self, node) -> Dict[str, str]:
        found: Dict[str, str] = {}
        nid = getattr(node, "node_id", "")
        for prop in self._targets(node, "has_property", "PropertyNode"):
            for col, pname in PROPERTY_COLUMNS.items():
                if col in found:
                    continue
                pid = str(getattr(prop, "node_id", "") or "")
                ptype = str(getattr(prop, "property_type", "") or "")
                if pid == f"{nid}_{pname}" or ptype.lower() == pname.lower():
                    value = getattr(prop, "value", None)
                    if value in (None, ""):
                        value = getattr(prop, "description", None)
                    if value not in (None, ""):
                        found[col] = str(value)
        return found

    def documents(self, node) -> Dict[str, str]:
        found: Dict[str, str] = {}
        nid = str(getattr(node, "node_id", "") or "")
        checklist: List[List[str]] = []
        for doc in self._targets(node, "has_documentation", "DocumentNode"):
            did = str(getattr(doc, "node_id", "") or "")
            if did.startswith(f"{nid}_doc_"):
                label = str(getattr(doc, "name", "") or "").strip()
                if label and [label, "Si"] not in checklist:
                    checklist.append([label, "Si"])
            elif did.startswith("doc::path::") and "doc_usv" not in found:
                url = getattr(doc, "url", None) or did[len("doc::path::"):]
                if url:
                    found["doc_usv"] = str(url)
        if checklist:
            found["documentazione"] = str(checklist)
        if type(node).__name__ == "DocumentNode" and "doc_usv" not in found:
            url = getattr(node, "url", None)
            if url:
                found["doc_usv"] = str(url)
        return found

    def epochs(self, node) -> Dict[str, str]:
        found: Dict[str, str] = {}
        for epoch in self._targets(node, "has_first_epoch", "EpochNode"):
            p, f = epoch_key(epoch)
            if p is not None:
                found["periodo_iniziale"], found["fase_iniziale"] = p, f
                break
        latest = None
        for epoch in self._targets(node, "survive_in_epoch", "EpochNode"):
            p, f = epoch_key(epoch)
            if p is None:
                continue
            start = getattr(epoch, "start_time", None)
            start = float(start) if isinstance(start, (int, float)) else float("-inf")
            if latest is None or start > latest[0]:
                latest = (start, p, f)
        if latest is not None:
            found["periodo_finale"], found["fase_finale"] = latest[1], latest[2]
        return found

    def persons(self, node) -> Dict[str, str]:
        """``schedatore`` / ``direttore_us`` / ``responsabile_us``: the
        author of the unit's act of that kind, with the role the column
        names on its ``has_author`` edge (none: the author the act's kind
        says). The first one met, in edge order, when an act has two."""
        found: Dict[str, str] = {}
        wanted = self.person_of
        for act in self._targets(node, "is_in_activity", "ActivityNodeGroup"):
            kind = (getattr(act, "data", None) or {}).get("act_kind")
            if not kind:
                continue
            for et, person, edge in self.out.get(getattr(act, "node_id", None), ()):
                if et != "has_author" or type(person).__name__ not in (
                        "AuthorNode", "AuthorAINode"):
                    continue
                role = (getattr(edge, "attributes", None) or {}).get("role") or None
                col = wanted.get((kind, role))
                name = str(getattr(person, "name", "") or "").strip()
                if col and name and col not in found:
                    found[col] = name
        return found

    # ------------------------------------------------------------ the row
    def columns(self, node) -> Dict[str, Any]:
        """The us_table columns of *node* the graph says. A column the graph
        is silent on is absent (the ingestor leaves it untouched); a value an
        older graph carried on the node fills a column the graph is silent
        on."""
        from .rapporti import us_number_of, strip_us_prefix
        row: Dict[str, Any] = {}
        uuid = node_uuid_of(node)
        if uuid:
            row["node_uuid"] = uuid
        us = us_number_of(node)
        if us is None and getattr(node, "name", None):
            us = strip_us_prefix(str(node.name))
        if us:
            row["us"] = str(us)
        code = row_code(node)
        if code:
            row["unita_tipo"] = code
        row.update(self.places(node))
        desc = getattr(node, "description", None)
        if desc is not None and str(desc).strip().lower() not in _EMPTY_DESCRIPTIONS:
            row["d_stratigrafica"] = str(desc)
        row.update(self.properties(node))
        row.update(self.documents(node))
        row.update(self.epochs(node))
        row.update(self.persons(node))
        # what an older graph carried on the node, where the graph is silent
        for key in ROW_COLUMNS:
            if key in row:
                continue
            v = legacy_value(node, key)
            if v is not None:
                row[key] = str(v)
        # an older graph's own unita_tipo wins over the class (the class may
        # be the generic one the old projector gave every row)
        old_code = legacy_value(node, "unita_tipo")
        if old_code:
            row["unita_tipo"] = str(old_code)
        old_us = legacy_value(node, "us")
        if old_us:
            row["us"] = str(old_us)
        return row


def documentation_entries(value: Any) -> List[str]:
    """The affirmative labels of a pyArchInit ``documentazione`` checklist."""
    try:
        entries = ast.literal_eval(str(value))
    except (ValueError, SyntaxError):
        return []
    out = []
    for entry in entries if isinstance(entries, (list, tuple)) else ():
        if isinstance(entry, (list, tuple)) and len(entry) >= 2 \
                and str(entry[1]).strip().lower() in {"si", "sì", "yes", "y", "true", "1", "x", "ja", "oui"}:
            out.append(str(entry[0]).strip())
    return out


# ---------------------------------------------------------------------------
# Files written before the rule: the row fields in node.data become the graph
# ---------------------------------------------------------------------------

#: kind of the place each column makes (pyarchinit_us_mapping)
_PLACE_KIND = {"area": "study", "settore": "study", "saggio": "study",
               "quad_par": "study", "ambient": "functional"}

#: the keys that are dropped once the graph says them (or that were only a
#: copy: the site is the graph's, the epoch's label is the epoch's, the
#: rapporti are the edges the same file carries)
_COPIES = ("sito", "datazione_estesa", "rapporti")


def _row_bag(node) -> Optional[dict]:
    """The dict holding an older projector's row fields on *node*, if any:
    ``node.data`` (an em.json read back) or ``attributes``."""
    for bag in (getattr(node, "data", None), getattr(node, "attributes", None)):
        if isinstance(bag, dict) and (bag.get("node_uuid") or bag.get("us")) \
                and any(k in bag for k in LEGACY_ROW_KEYS if k != "us"):
            return bag
    return None


def _reclass(graph, node, klass, **extra):
    """Replace *node* by an instance of *klass* with the same id, name,
    description, attributes and data. Edges keep pointing at the id."""
    new = klass(node_id=node.node_id, name=node.name,
                description=getattr(node, "description", "") or "", **extra)
    for bag in ("attributes", "data"):
        old = getattr(node, bag, None)
        if isinstance(old, dict):
            target = getattr(new, bag, None)
            if not isinstance(target, dict):
                setattr(new, bag, {})
                target = getattr(new, bag)
            target.update(old)
    idx = graph.nodes.index(node)
    graph.nodes[idx] = new
    if hasattr(graph, "invalidate_indices"):
        graph.invalidate_indices()
    return new


def migrate_legacy_row_fields(graph) -> Dict[str, Any]:
    """An em.json written before 27 Nov 2026 by pyArchInit's projector
    carries a unit's row columns in its ``data`` (sito, area, settore,
    saggio, ambient, unita_tipo, documentazione, d_stratigrafica,
    d_interpretativa, attivita, struttura, periodo / fase, rapporti,
    datazione_estesa, us). Read in memory as nodes and edges, ONE warning:

    - a place column → the unit ``is_in_location`` its place (the existing
      one of that column and name, else a new ``LocationNodeGroup``);
    - ``unita_tipo`` → the class (a Combinar on a US becomes a CombinerNode,
      a USVs a StructuralVirtualStratigraphicUnit), a localized code kept as
      ``source_code``;
    - ``documentazione`` → one document per «Si» (``has_documentation``);
    - ``d_stratigrafica`` → the description, when it has none;
    - ``d_interpretativa`` / ``attivita`` / ``struttura`` → the properties;
    - ``periodo_iniziale`` / ``fase_iniziale`` → ``has_first_epoch`` to the
      epoch of that code, when the file has it;
    - ``sito``, ``rapporti``, ``datazione_estesa``, ``us`` → dropped when
      the graph already says them (the site, the edges, the epoch, the name).

    A field the graph cannot say (an epoch code the file has no epoch for, a
    number that is not the name's) stays where it was, and is counted. The
    next save writes the nodes. Idempotent. ``node_uuid`` stays (the
    technical key); ``quad_par`` is a place like the others (27 Nov 2026).

    The epochs of such a file are read the same way
    (:func:`migrate_legacy_epoch_fields`)."""
    from .nodes.stratigraphic_node import StratigraphicNode
    from .rapporti import canonical_unita_tipo, strip_us_prefix
    out: Dict[str, Any] = {"units": 0, "moved": {}, "kept": {}, "warnings": []}
    candidates = [n for n in list(getattr(graph, "nodes", None) or [])
                  if _row_bag(n) is not None]
    epochs = migrate_legacy_epoch_fields(graph)
    if epochs["epochs"]:
        out["warnings"].extend(epochs["warnings"])
    if not candidates:
        return out
    moved, kept = out["moved"], out["kept"]
    levels = place_levels()
    columns = place_columns(levels)

    def _count(d, k):
        d[k] = d.get(k, 0) + 1

    def _edge(src, tgt, et):
        eid = f"{src}_{et}_{tgt}"
        if graph.find_edge_by_id(eid) is None:
            graph.add_edge(eid, src, tgt, et)

    for node in candidates:
        out["units"] += 1
        bag = _row_bag(node)
        # 1. the class
        code = str(bag.get("unita_tipo") or "").strip()
        if code:
            node = _migrate_class(graph, node, code)
            bag = _row_bag(node) or bag
            if row_code(node) == code:
                bag.pop("unita_tipo", None)
                _count(moved, "unita_tipo")
            else:
                _count(kept, "unita_tipo")
        reader = RowReader(graph)
        # 2. the places
        have = reader.places(node)
        for col in PLACE_COLUMNS:
            v = str(bag.get(col) or "").strip()
            if not v:
                bag.pop(col, None)
                continue
            if have.get(col) != v:
                loc = next((n for n in graph.nodes
                            if type(n).__name__ == "LocationNodeGroup"
                            and place_column(n, columns) == col
                            and str(getattr(n, "name", "")).strip() == v), None)
                if loc is None:
                    from .nodes.group_node import LocationNodeGroup
                    kind = _PLACE_KIND[col]
                    loc = LocationNodeGroup(node_id=f"loc::{col}::{kind}::{v}",
                                            name=v, kind=kind)
                    # the key of em-place-level, as the importer (1.6.8)
                    loc.attributes["level"] = levels[col]
                    graph.add_node(loc)
                _edge(node.node_id, loc.node_id, "is_in_location")
            bag.pop(col, None)
            _count(moved, col)
        # 3. the description
        d = bag.get("d_stratigrafica")
        if d is not None:
            if not str(getattr(node, "description", "") or "").strip():
                node.description = str(d)
            if str(node.description) == str(d):
                bag.pop("d_stratigrafica", None)
                _count(moved, "d_stratigrafica")
            else:
                _count(kept, "d_stratigrafica")
        # 4. the properties
        props = reader.properties(node)
        for col, pname in PROPERTY_COLUMNS.items():
            v = bag.get(col)
            if v in (None, ""):
                bag.pop(col, None)
                continue
            if props.get(col) != str(v):
                if props.get(col) is not None or not _allowed(node, "property", "has_property"):
                    _count(kept, col)
                    continue
                from .nodes.property_node import PropertyNode
                pid = f"{node.node_id}_{pname}"
                if graph.find_node_by_id(pid) is None:
                    graph.add_node(PropertyNode(node_id=pid, name=pname,
                                                description=str(v), value=str(v),
                                                property_type=pname))
                _edge(node.node_id, pid, "has_property")
            bag.pop(col, None)
            _count(moved, col)
        # 5. the documentation checklist
        v = bag.get("documentazione")
        if v not in (None, ""):
            labels = documentation_entries(v)
            if not labels:
                bag.pop("documentazione", None)
            elif isinstance(node, StratigraphicNode) and _allowed(
                    node, "document", "has_documentation"):
                from .nodes.document_node import DocumentNode
                for label in labels:
                    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
                    did = f"{node.node_id}_doc_{slug}"
                    if graph.find_node_by_id(did) is None:
                        graph.add_node(DocumentNode(
                            node_id=did, name=label,
                            description=f"pyArchInit documentation present: {label}",
                            content_nature="2d_object"))
                    _edge(node.node_id, did, "has_documentation")
                bag.pop("documentazione", None)
                _count(moved, "documentazione")
            else:
                _count(kept, "documentazione")
        # 6. the first epoch
        p = bag.get("periodo_iniziale")
        if p not in (None, ""):
            f = str(bag.get("fase_iniziale") or "")
            first = reader.epochs(node)
            if first.get("periodo_iniziale") is None:
                epoch = next((n for n in graph.nodes
                              if type(n).__name__ == "EpochNode"
                              and epoch_key(n) == (str(p), f)), None)
                if epoch is not None:
                    _edge(node.node_id, epoch.node_id, "has_first_epoch")
                    first = {"periodo_iniziale": str(p)}
            if first.get("periodo_iniziale") is not None:
                bag.pop("periodo_iniziale", None)
                bag.pop("fase_iniziale", None)
                _count(moved, "periodo_iniziale / fase_iniziale")
            else:
                _count(kept, "periodo_iniziale / fase_iniziale")
        else:
            bag.pop("periodo_iniziale", None)
            bag.pop("fase_iniziale", None)
        # 7. the copies
        for k in _COPIES:
            if k in bag:
                bag.pop(k)
                _count(moved, k)
        us = bag.get("us")
        if us is not None:
            if strip_us_prefix(str(node.name)) == str(us).strip():
                bag.pop("us")
                _count(moved, "us")
            else:
                _count(kept, "us")
    said = ", ".join(f"{k} {v}" for k, v in sorted(moved.items()))
    line = (f"pyArchInit row fields in node.data: {out['units']} unit(s) read "
            f"as nodes and edges ({said or 'nothing to move'})")
    if kept:
        line += "; left in data, the graph cannot say them: " + ", ".join(
            f"{k} {v}" for k, v in sorted(kept.items()))
    out["warnings"].append(line + " — the next save writes the nodes.")
    return out


def _allowed(node, target_type: str, edge_type: str) -> bool:
    from .graph import Graph
    return Graph.validate_connection(getattr(node, "node_type", None),
                                     target_type, edge_type)


def _migrate_class(graph, node, code: str):
    """The node with the class *code* names (see the importer's
    ``_class_of_row``), its code kept as ``source_code`` when the class does
    not say it back."""
    import importlib
    from .rapporti import canonical_unita_tipo
    from .utils.utils import (STRATIGRAPHIC_CLASS_MAP, apply_legacy_kind,
                              get_stratigraphic_node_class)
    from .nodes.stratigraphic_node import KIND_OF_CODE
    paradata = {"DOC": (".nodes.document_node", "DocumentNode"),
                "Combinar": (".nodes.combiner_node", "CombinerNode"),
                "Extractor": (".nodes.extractor_node", "ExtractorNode"),
                "property": (".nodes.property_node", "PropertyNode")}
    if code in paradata:
        mod, cls = paradata[code]
        klass = getattr(importlib.import_module(mod, __package__), cls)
        extra = {"property_type": "string"} if cls == "PropertyNode" else {}
    else:
        canon = canonical_unita_tipo(code)
        canon = "BR" if canon == "CON" else canon
        if canon not in STRATIGRAPHIC_CLASS_MAP and canon not in KIND_OF_CODE:
            klass, extra = None, {}
        else:
            klass, extra = get_stratigraphic_node_class(canon), {}
    # only a node of the GENERIC class the old projector gave every row is
    # re-classed; a node a person typed keeps its class
    if klass is not None and type(node) is not klass and \
            type(node).__name__ in ("StratigraphicUnit", "StratigraphicNode"):
        node = _reclass(graph, node, klass, **extra)
    if type(node).__name__ == "StratigraphicUnit":
        apply_legacy_kind(node, code)
    if keeps_source_code(node, code):
        node.source_code = code
    return node
