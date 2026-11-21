"""The Landscape Matrix table → a landscape em.json — MICRO-LG2 (21 Nov 2026).

Reads the long table of a Landscape Matrix (one row per identity of a site,
the form of ``_datasets/Sarmizegetusa/06_EM/LandscapeMatrix/landscape-matrix_v1.csv``)
and builds the Landscape Graph of it, with the rules of §14–15 of the brain
note ``decisioni/landscape-graph-semantica`` and E.D.'s decisions of 21 Nov
2026:

* the container is of kind ``landscape``;
* one SITE per ``sito_id`` — a ``LocationNodeGroup`` of level ``sito``
  (:func:`s3dgraphy.hdto.make_site_place`, so a study that took place there,
  in this file or another, names the same node);
* one FUNCTIONAL UNIT per row ``identità`` (``FunctionalUnitNodeGroup``,
  ``is_in_location`` its site): ``scale`` from ``scala``; ``primary_function``
  with an extractor and a document from the column ``fonte`` (one document
  per distinct cell, D.01…, the extractor ``D.nn.k``); the life from
  ``da_anno`` / ``a_anno`` (``absolute_time_start`` / ``_end`` with the same
  chain) or, when empty, the text of ``da`` / ``a`` in the description and a
  WARNING — no date is ever invented;
* a row whose ``tipo_cambio`` says it is a PHASE of the same functional unit
  (different US, the same function) does not make a unit: it joins the unit of
  the row before it on the same site as a dated property ``phase``;
* the chains: ``ingresso_da`` + ``tipo_cambio`` → ``changed_from`` with
  ``change_type`` ``transformation`` (``transformation_kind`` and the words of
  the table in ``note``); «dopo, sullo stesso sito (is_after)» → ``is_after``
  the first identity of the site, no chain;
* the rows ``UT`` → topographic units (``TopographicUnitNode``) ``is_in_location``
  the site; a supposed identity of the same site has its ``primary_function``
  extracted from them (the UT is a SOURCE, not a member);
* the rows «lettura alternativa» → functional units marked
  ``data.alternative_reading`` (the datamodel admits no functional unit in a
  ``TimeBranchNodeGroup``: ``is_in_timebranch`` takes stratigraphic nodes
  only), and a warning.

Everything the table says and the graph has no place for stays in the node's
``data`` (``row_v0``, ``where``, ``declared_evidence``, ``declared_horizon``,
``revision``). :func:`import_landscape_matrix_csv` answers the container and a
report (counts, warnings, decisions); ``scripts/import_landscape_matrix.py``
writes the em.json.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter, OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .. import hdto
from ..container import Container
from ..graph import Graph
from ..nodes.document_node import DocumentNode
from ..nodes.extractor_node import ExtractorNode
from ..nodes.group_node import FunctionalUnitNodeGroup
from ..nodes.landscape_unit_node import TopographicUnitNode
from ..nodes.property_node import PropertyNode

#: ``scala`` of the table → ``data.scale`` (node datamodel 1.6.52)
SCALES_IT = {"territorio": "territory", "complesso": "complex", "edificio": "building",
             "ambiente": "room", "componente": "component"}

_SITE_ID = re.compile(r"^\s*(S\d+)\b\s*(.*)$")
_ROW_REF = re.compile(r"\(r\.\s*(\d+)\)")
_WORD = re.compile(r"[a-zà-ÿ]{3,}", re.I)

KIND_WORDS = (("rovina", "ruin"), ("distruzione", "destruction"), ("ricostruzione", "reconstruction"),
              ("restauro", "reconstruction"), ("riuso", "reuse"), ("sostituzione", "replacement"),
              ("cambio d'identità", "identity_change"), ("cambio d'uso", "reuse"))


def _sid(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _num(text: Any) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _common_name(names: List[str]) -> str:
    """The common name of several labels of one thing: their common prefix
    cut back to a word boundary («Mura, prima fase» + «Mura, seconda fase» →
    «Mura»), else the most frequent (the first on a tie)."""
    names = [n for n in names if n]
    if not names:
        return ""
    prefix = names[0]
    for n in names[1:]:
        while not n.startswith(prefix):
            prefix = prefix[:-1]
    if len(set(names)) == 1:
        return names[0]
    if prefix and not all(len(n) == len(prefix) or not n[len(prefix)].isalnum() for n in names):
        prefix = re.sub(r"\S*$", "", prefix)
    prefix = prefix.strip().rstrip(",:;").strip()
    if prefix:
        return prefix
    return Counter(names).most_common(1)[0][0] if len(set(Counter(names).values())) > 1 \
        else names[0]


def _is_phase(tipo: str) -> bool:
    t = (tipo or "").lower()
    return t.startswith("fase della stessa")


def _is_after_rule(tipo: str) -> bool:
    return "is_after" in (tipo or "")


def _transformation_kind(tipo: str) -> Optional[str]:
    t = (tipo or "").lower()
    for word, kind in KIND_WORDS:
        if word in t:
            return kind
    return None


class _Builder:
    def __init__(self, title: str):
        self.g = Graph("LANDSCAPE", name=title)
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.decisions: List[str] = []
        self.documents: "OrderedDict[str, str]" = OrderedDict()   # fonte → doc id
        self.extractor_count: Counter = Counter()
        self.sites: Dict[str, str] = {}          # sito_id → node id
        self.uts: Dict[str, List[str]] = {}      # sito_id → UT ids
        self.fu_of_row: Dict[int, str] = {}      # index of the row → FU id
        self.row_v0_to_fu: Dict[str, str] = {}
        self.rows_by_site: Dict[str, List[int]] = {}
        self.counts: Counter = Counter()

    # ── paradata ────────────────────────────────────────────────────────────
    def document(self, fonte: str) -> Optional[str]:
        fonte = (fonte or "").strip()
        if not fonte:
            return None
        if fonte not in self.documents:
            name = f"D.{len(self.documents) + 1:02d}"
            did = "doc_" + _sid("doc", fonte)
            self.g.add_node(DocumentNode(did, name, description=fonte))
            self.documents[fonte] = did
            self.counts["documents"] += 1
        return self.documents[fonte]

    def extractor(self, fonte: str, why: str, *, also_from: Iterable[str] = ()) -> Optional[str]:
        did = self.document(fonte)
        if did is None and not list(also_from):
            return None
        doc_name = self.g.find_node_by_id(did).name if did else "UT"
        self.extractor_count[doc_name] += 1
        name = f"{doc_name}.{self.extractor_count[doc_name]}"
        eid = "ext_" + _sid("ext", name, why)
        self.g.add_node(ExtractorNode(eid, name, description=why))
        self.counts["extractors"] += 1
        if did:
            self.g.add_edge(f"{eid}_extracted_from_{did}", eid, did, "extracted_from")
        for src in also_from:
            self.g.add_edge(f"{eid}_extracted_from_{src}", eid, src, "extracted_from")
        return eid

    def prop(self, owner: str, ptype: str, value: Any, extractor: Optional[str], *,
             data: Optional[Dict[str, Any]] = None, key: str = "") -> str:
        pid = "prop_" + _sid(owner, ptype, key or value)
        p = PropertyNode(pid, ptype, value=value, property_type=ptype)
        if data:
            p.data = dict(getattr(p, "data", None) or {}, **data)
        self.g.add_node(p)
        self.g.add_edge(f"{owner}_has_property_{pid}", owner, pid, "has_property")
        if extractor:
            self.g.add_edge(f"{pid}_has_data_provenance_{extractor}", pid, extractor,
                            "has_data_provenance")
        self.counts["properties"] += 1
        return pid

    # ── places and units ────────────────────────────────────────────────────
    def site(self, sito_id: str, names: List[str]) -> str:
        if sito_id in self.sites:
            return self.sites[sito_id]
        name = _common_name(names) or sito_id
        node = hdto.make_site_place(name)
        node.attributes["sito_id"] = sito_id
        if not isinstance(getattr(node, "data", None), dict):
            node.data = {}
        node.data["sito_id"] = sito_id
        self.g.add_node(node)
        self.sites[sito_id] = node.node_id
        self.counts["sites"] += 1
        return node.node_id

    def topographic_unit(self, name: str, row: Dict[str, str], site_id: str) -> str:
        uid = "ut_" + _sid("ut", row["sito_id"], name)
        node = TopographicUnitNode(uid, name=name, description=row.get("identita", ""))
        node.data.update({k: v for k, v in (("row_v0", row.get("riga_v0")),
                                             ("where", row.get("dove (GIS/fonte)")),
                                             ("note", row.get("note")),
                                             ("declared_horizon", row.get("orizzonte")))
                          if v})
        self.g.add_node(node)
        self.g.add_edge(f"{uid}_is_in_location_{site_id}", uid, site_id, "is_in_location")
        self.counts["topographic_units"] += 1
        return uid

    def dates(self, owner: str, row: Dict[str, str], extractor: Optional[str], label: str) -> List[str]:
        """The two bounds of a life, or the words of the table and a warning."""
        missing = []
        for side, col_num, col_text in (("start", "da_anno", "da"), ("end", "a_anno", "a")):
            value = _num(row.get(col_num))
            if value is not None:
                self.prop(owner, f"absolute_time_{side}", value, extractor)
                continue
            text = (row.get(col_text) or "").strip()
            if text in ("", "—"):
                self.warnings.append(f"[date] {label}: {col_text} empty — no {side}")
                missing.append(f"{col_text}: —")
            elif text.lower() == "oggi" and side == "end":
                self.info.append(f"[date] {label}: a = «oggi» — the end stays open (still existing)")
                missing.append(f"{col_text}: {text}")
            else:
                self.warnings.append(f"[date] {label}: {col_text} «{text}» is not a year — kept as text, no {side}")
                missing.append(f"{col_text}: {text}")
        return missing


def read_rows(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def import_landscape_matrix_csv(path: str, *, title: str = "Landscape Matrix",
                                cited: Iterable[Dict[str, Any]] = (),
                                rows: Optional[List[Dict[str, str]]] = None
                                ) -> Tuple[Container, Dict[str, Any]]:
    """Build the landscape em.json of a Landscape Matrix table.

    ``cited`` — the studies the landscape cites (``{id, title, code?, path?}``,
    the header's ``composition``): read, never copied. Answers ``(container,
    report)``, ``report`` = ``{counts, warnings, info, decisions,
    unresolved_chains}``."""
    rows = read_rows(path) if rows is None else rows
    b = _Builder(title)
    g = b.g

    # sites first, named from every row of theirs
    names_by_site: Dict[str, List[str]] = OrderedDict()
    for i, r in enumerate(rows):
        names_by_site.setdefault(r["sito_id"], []).append((r.get("sito") or "").strip())
        b.rows_by_site.setdefault(r["sito_id"], []).append(i)
    for sid, names in names_by_site.items():
        b.site(sid, names)

    # UT rows (before the identities, which may extract from them)
    for i, r in enumerate(rows):
        if (r.get("tipo_riga") or "").strip() != "UT":
            continue
        site_id = b.sites[r["sito_id"]]
        sito = (r.get("sito") or "").strip()
        m = re.search(r"\((UT\d+)\)", sito)
        if m:
            names = [m.group(1)]
        else:
            names = re.findall(r"UT\s?\d+", sito) or [sito]
            names = [n.replace(" ", "") for n in names]
            if len(names) > 1:
                b.decisions.append(f"row v0 {r['riga_v0']}: «{sito}» → {len(names)} topographic units ({', '.join(names)})")
        for name in names:
            uid = b.topographic_unit(name, r, site_id)
            b.uts.setdefault(r["sito_id"], []).append(uid)
            ext = b.extractor(r.get("fonte", ""), f"{name}: {r.get('evidenza', '')}".strip())
            b.dates(uid, r, ext, f"{name} (row v0 {r['riga_v0']})")

    # identities and alternative readings
    phases_of: Dict[str, List[int]] = {}
    for i, r in enumerate(rows):
        kind = (r.get("tipo_riga") or "").strip()
        if kind == "UT":
            continue
        sid = r["sito_id"]
        if _is_phase(r.get("tipo_cambio", "")):
            before = [j for j in b.rows_by_site[sid] if j < i and j in b.fu_of_row]
            if before:
                fu = b.fu_of_row[before[-1]]
                b.fu_of_row[i] = fu
                b.row_v0_to_fu[r["riga_v0"]] = fu
                phases_of.setdefault(fu, []).append(i)
                continue
            b.warnings.append(f"[phase] row v0 {r['riga_v0']}: a phase with no identity before it on {sid} — kept as its own unit")
        fid = "fu_" + _sid("fu", sid, r["riga_v0"], r.get("identita"))
        scale_it = (r.get("scala") or "").strip()
        scale = SCALES_IT.get(scale_it)
        if scale_it and scale is None:
            b.warnings.append(f"[scale] row v0 {r['riga_v0']}: «{scale_it}» is not a scale of the vocabulary")
        node = FunctionalUnitNodeGroup(fid, (r.get("identita") or "").strip(),
                                       description=(r.get("note") or "").strip(), scale=scale)
        if not isinstance(getattr(node, "data", None), dict):
            node.data = {}
        node.data.update({k: v for k, v in (("row_v0", r.get("riga_v0")),
                                             ("sito_id", sid),
                                             ("where", r.get("dove (GIS/fonte)")),
                                             ("declared_evidence", r.get("evidenza")),
                                             ("declared_horizon", r.get("orizzonte")),
                                             ("revision", r.get("revisione_2026-11-21")))
                          if v})
        if kind != "identità":
            node.data["alternative_reading"] = kind
            b.counts["alternative_readings"] += 1
            b.warnings.append(f"[alternative] row v0 {r['riga_v0']}: «{kind}» — marked data.alternative_reading; "
                              "no TimeBranchNodeGroup (is_in_timebranch admits stratigraphic nodes only)")
        g.add_node(node)
        g.add_edge(f"{fid}_is_in_location_{b.sites[sid]}", fid, b.sites[sid], "is_in_location")
        b.fu_of_row[i] = fid
        b.row_v0_to_fu.setdefault(r["riga_v0"], fid)
        b.counts["functional_units"] += 1
        if "segnaposto" in (r.get("revisione_2026-11-21") or "") or (r.get("identita") or "").strip() == "da documentare":
            b.warnings.append(f"[placeholder] row v0 {r['riga_v0']}: «{node.name}» is a placeholder of the table")

    # the merged units: name, function, life, phases
    for i, r in enumerate(rows):
        fid = b.fu_of_row.get(i)
        if fid is None or (i in [p for ps in phases_of.values() for p in ps]):
            continue
        node = g.find_node_by_id(fid)
        phase_rows = [i] + phases_of.get(fid, [])
        label = f"«{node.name}» (row v0 {r['riga_v0']})"
        uts = b.uts.get(r["sito_id"], []) if "fonte la UT" in (r.get("evidenza") or "") else []
        if phases_of.get(fid):
            node.name = _common_name([(rows[j].get("sito") or "").strip() for j in phase_rows]) or node.name
            label = f"«{node.name}» (rows v0 {', '.join(rows[j]['riga_v0'] for j in phase_rows)})"
            b.decisions.append(f"{label}: one functional unit with {len(phase_rows)} phases (dated property `phase`)")
        ext = b.extractor(r.get("fonte", ""), f"{node.name}: {r.get('evidenza', '')}".strip(),
                          also_from=uts)
        b.prop(fid, "primary_function", node.name if phases_of.get(fid) else (r.get("identita") or "").strip(),
               ext)
        if phases_of.get(fid):
            first, last = rows[phase_rows[0]], rows[phase_rows[-1]]
            life_row = dict(first, a_anno=last.get("a_anno", ""), a=last.get("a", ""))
            for j in phase_rows:
                pr = rows[j]
                pext = ext if j == i else b.extractor(pr.get("fonte", ""), f"{node.name}, phase: {pr.get('evidenza', '')}")
                data = {k: v for k, v in (("valid_from", _num(pr.get("da_anno"))),
                                          ("valid_to", _num(pr.get("a_anno"))),
                                          ("row_v0", pr.get("riga_v0")),
                                          ("from_text", pr.get("da")), ("to_text", pr.get("a")))
                        if v not in (None, "")}
                b.prop(fid, "phase", (pr.get("identita") or "").strip(), pext, data=data,
                       key=pr.get("riga_v0"))
                b.counts["phases"] += 1
        else:
            life_row = r
        missing = b.dates(fid, life_row, ext, label)
        if missing:
            node.description = ((node.description + "\n") if node.description else "") + \
                "Date nella tabella: " + "; ".join(missing)

    # the chains
    unresolved = []
    for i, r in enumerate(rows):
        fid = b.fu_of_row.get(i)
        tipo = (r.get("tipo_cambio") or "").strip()
        if fid is None or _is_phase(tipo):
            continue
        if _is_after_rule(tipo):
            firsts = [b.fu_of_row[j] for j in b.rows_by_site[r["sito_id"]]
                      if j in b.fu_of_row and b.fu_of_row[j] != fid]
            if firsts:
                g.add_edge(f"{fid}_is_after_{firsts[0]}", fid, firsts[0], "is_after")
                b.counts["is_after"] += 1
                b.decisions.append(f"row v0 {r['riga_v0']}: «{tipo}» → is_after «{g.find_node_by_id(firsts[0]).name}»")
            continue
        src = (r.get("ingresso_da") or "").strip()
        if not src:
            continue
        former = _resolve(b, rows, i, src)
        if former is None:
            unresolved.append({"row_v0": r["riga_v0"], "ingresso_da": src})
            b.warnings.append(f"[chain] row v0 {r['riga_v0']}: «{src}» names no identity of the table")
            continue
        e = g.add_edge(f"{fid}_changed_from_{former}", fid, former, "changed_from")
        e.attributes["change_type"] = "transformation"
        kind = _transformation_kind(tipo)
        if kind:
            e.attributes["transformation_kind"] = kind
        if tipo:
            e.attributes["note"] = tipo
        b.counts["transformations"] += 1
        if "cambio d'uso" in tipo.lower():
            b.warnings.append(f"[chain] row v0 {r['riga_v0']}: «{tipo}» — read as a transformation (new roads on the "
                              "Roman layout are stratigraphic actions); a dated `use` of one unit if E.D. decides otherwise")

    cited = [dict(c) for c in cited]
    container = Container(graphs={g.graph_id: g}, active_graph_id=g.graph_id,
                          header={"title": title, "kind": "landscape",
                                  "composition": cited})
    report = {"counts": dict(b.counts), "warnings": b.warnings, "info": b.info,
              "decisions": b.decisions, "unresolved_chains": unresolved,
              "rows": len(rows)}
    return container, report


def _resolve(b: _Builder, rows: List[Dict[str, str]], i: int, src: str) -> Optional[str]:
    """The identity ``ingresso_da`` names: ``(r. NN)`` the row of the table;
    else ``S<nn> <words>`` — the identity of that site whose words (its
    identity, its phases, the name of its unit — not the site's name, shared by
    every row of the site) share most words with the label, the latest before
    the row on a tie."""
    m = _ROW_REF.search(src)
    if m and m.group(1) in b.row_v0_to_fu:
        return b.row_v0_to_fu[m.group(1)]
    ms = _SITE_ID.match(src)
    if not ms:
        return None
    sid, label = ms.group(1), _ROW_REF.sub("", ms.group(2))
    words = {w.lower() for w in _WORD.findall(label)}
    me = b.fu_of_row.get(i)
    best: Tuple[int, int, Optional[str]] = (0, -1, None)
    for j in b.rows_by_site.get(sid, []):
        fu = b.fu_of_row.get(j)
        if fu is None or fu == me:
            continue
        # the identity of the row and the name of its unit — not the name of
        # the site, which every row of the site shares (S01 «Colonia»)
        text = " ".join([rows[j].get("identita") or "",
                         b.g.find_node_by_id(fu).name or ""]).lower()
        score = sum(1 for w in words if w in text)
        order = j if j < i else -1  # later rows only win on a strictly better score
        if score > best[0] or (score == best[0] and score > 0 and order > best[1]):
            best = (score, order, fu)
    return best[2]


__all__ = ["SCALES_IT", "read_rows", "import_landscape_matrix_csv"]
