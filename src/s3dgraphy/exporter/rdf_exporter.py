"""
RDF Exporter for s3Dgraphy graphs.

Serializes s3Dgraphy graphs to RDF (Turtle, N-Triples, JSON-LD, RDF/XML)
using the CIDOC-CRM + HDT-O + EM ontology declared in companion files:

  * em.ttl              — Extended Matrix ontology (em: classes & properties)
  * hdto_extension.ttl  — HDT-O containment / granularity properties

Three driving datamodels are read at construction time as the single
source of truth — no class/edge/qualia type is hard-coded here:

  * s3Dgraphy_node_datamodel.json
      → class → IRI mapping via em_extension.uri (preferred) or mapping.cidoc.
        Multi-typing via em_extension.subclass_of (emitted as additional
        rdf:type triples so a CRM-only reader still sees the CRM superclasses).

  * s3Dgraphy_connections_datamodel.json
      → edge_type → predicate IRI.
        AP11_has_physical_relation_to discrimination via type_tag → em:abuts /
        em:cuts / em:fills / em:overlies / em:bondedTo / em:physicallyEquals
        subproperties (SPARQL-friendly: queries can be specific or fall
        back to AP11 via subproperty inference).
        Deprecated edges (deprecated: true) are skipped on write — see
        has_timebranch which is canonicalised to is_in_timebranch.

  * em_qualia_types.json
      → PropertyNode conditional mapping: a property's CIDOC class is
        looked up by property_type (height → E54_Dimension, color → E55_Type,
        aesthetic_value → crminf:I4_Proposition_Set, etc.).

Named-graph wrapping:
  Each s3Dgraphy Graph is serialized into its own named graph IRI of the
  form <base>/graph/<graph_id>, anchored by an em:EMGraph triple plus the
  graph-level metadata (default author, license).

Author:  Emanuele Demetrescu
Version: 1.6.0 — initial RDF export pipeline
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from rdflib import ConjunctiveGraph, Literal, Namespace, URIRef
    from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD
except ImportError as _e:  # pragma: no cover
    raise ImportError(
        "RDFExporter requires rdflib. Install with: pip install rdflib"
    ) from _e

from ..graph import Graph as S3DGraph
from ..multigraph.multigraph import get_all_graph_ids, get_graph


# ─────────────────────────────────────────────────────────────────────────────
# Namespaces
# ─────────────────────────────────────────────────────────────────────────────

EM         = Namespace("https://w3id.org/em/ontology#")
S3D        = Namespace("https://w3id.org/em/s3dgraphy#")
CRM        = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
CRMINF     = Namespace("http://www.cidoc-crm.org/extensions/crminf/")
CRMARCHAEO = Namespace("http://www.cidoc-crm.org/extensions/crmarchaeo/")
CRMDIG     = Namespace("http://www.cidoc-crm.org/extensions/crmdig/")
CRMGEO     = Namespace("http://www.cidoc-crm.org/extensions/crmgeo/")
HDTO       = Namespace("https://w3id.org/hdto/ontology#")
# W3C Web Annotation: only the quote of a passage uses it (oa:TextQuoteSelector
# + oa:exact) — the one piece of a reading's place with no fragment-string form.
OA         = Namespace("http://www.w3.org/ns/oa#")
# QUDT units: the E58 Measurement Unit a measured length points at (P91).
QUDT_UNIT  = Namespace("http://qudt.org/vocab/unit/")
# GeoSPARQL 1.1: the vertices of a 3D reading (node datamodel 1.6.15) leave as
# one geo:wktLiteral on <region>/geometry — see geometry/wkt.py.
GEO        = Namespace("http://www.opengis.net/ont/geosparql#")

#: The length units a measure is written in → the QUDT unit IRI. A unit not in
#: this table is minted as `s3d:unit_<u>` rather than dropped or guessed at.
MEASURE_UNIT_IRI: Dict[str, URIRef] = {
    "m":  QUDT_UNIT.M,
    "cm": QUDT_UNIT.CentiM,
    "mm": QUDT_UNIT.MilliM,
    "km": QUDT_UNIT.KiloM,
}

DEFAULT_BASE_URI = "https://w3id.org/em/id/"

PREFIX_MAP: Dict[str, Namespace] = {
    "em":         EM,
    "s3d":        S3D,
    "crm":        CRM,
    "crminf":     CRMINF,
    "crmarchaeo": CRMARCHAEO,
    "crmdig":     CRMDIG,
    "crmgeo":     CRMGEO,
    "hdto":       HDTO,
    "oa":         OA,
    "geo":        GEO,
    "prov":       PROV,
    "dcterms":    DCTERMS,
    "skos":       Namespace(str(SKOS)),
    "rdfs":       Namespace(str(RDFS)),
    "owl":        Namespace(str(OWL)),
    "xsd":        Namespace(str(XSD)),
}

# authority_ref `match` strength → RDF predicate (E.D.: concept alignment via
# SKOS; owl:sameAs ONLY for a human-confirmed identity, NEVER for a ranked or
# uncertain candidate; unqualified default = skos:closeMatch).
AUTHORITY_MATCH_PREDICATE: Dict[str, URIRef] = {
    "exact":    SKOS.exactMatch,
    "close":    SKOS.closeMatch,
    "broad":    SKOS.broadMatch,
    "narrow":   SKOS.narrowMatch,
    "related":  SKOS.relatedMatch,
    "sameAs":   OWL.sameAs,
    "identity": OWL.sameAs,
}
DEFAULT_AUTHORITY_PREDICATE: URIRef = SKOS.closeMatch


# ─────────────────────────────────────────────────────────────────────────────
# IRI resolution helpers
# ─────────────────────────────────────────────────────────────────────────────

def _iri_local(text: str) -> str:
    """Slugify a free-text label into a safe IRI local part.

    Property/qualia types are user text (e.g. ``"max level"``,
    ``"Shape; dimensions"``); minted verbatim they yield IRIs with spaces or
    ``;`` that rdflib refuses to serialize as Turtle. Keep [A-Za-z0-9_.-],
    collapse every other run to a single ``_``, and trim. Deterministic, so
    equal inputs still mint the same IRI (intra-graph joins hold).
    """
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_")
    return slug or "unknown"


def _resolve_prefixed(name: Optional[str]) -> Optional[URIRef]:
    """
    Resolve 'prefix:LocalName' or a bare CRM code (e.g. 'A2_Stratigraphic_Volume_Unit',
    'P67_refers_to') to a URIRef using PREFIX_MAP.

    Heuristics for un-prefixed codes (legacy datamodel fields):
        A<digit> → crmarchaeo;   I<digit> → crminf;   D<digit> → crmdig;
        SP / Q / OA prefixes → crmgeo;
        E<digit> / P<digit>   → crm core.

    Returns None for empty, non-string or unrecognised input.
    """
    if not name or not isinstance(name, str):
        return None
    name = name.strip()
    if not name:
        return None

    # Explicit prefix
    if ":" in name and not name.startswith(("http://", "https://")):
        prefix, local = name.split(":", 1)
        ns = PREFIX_MAP.get(prefix)
        return ns[local] if ns else None

    # Absolute URI passthrough
    if name.startswith(("http://", "https://")):
        return URIRef(name)

    # Datamodel uses human strings like "A2 Stratigraphic Volume Unit" —
    # the canonical CRM URI joins the code and the label with underscores
    # ("crmarchaeo:A2_Stratigraphic_Volume_Unit"). Normalise spaces so both
    # "E54 Dimension" and "E54_Dimension" resolve identically.
    full = name.replace(" ", "_")
    code = full.split("_")[0]

    # CRMarchaeo PROPERTIES are AP<n>, not A<n> — A<n> are its classes. The
    # heuristic below reads two characters and requires the second to be a
    # digit, so every AP code fell through to None and the extension predicate
    # was silently never emitted: 26 of the 47 declared extension_mappings,
    # AP28/AP4/AP22/AP12 among them. Verified against the CRMarchaeo v2.1.1
    # declaration (AP1–AP32).
    if len(code) >= 3 and code[:2] == "AP" and code[2].isdigit():
        return CRMARCHAEO[full]

    head = code[:2]
    if len(head) >= 2 and head[1].isdigit():
        first = head[0]
        if first == "A":
            return CRMARCHAEO[full]
        if first == "I":
            return CRMINF[full]
        if first == "D":
            return CRMDIG[full]
        # NOT resolved here, deliberately: CRMdig L<n> and CRMinf J<n> — the
        # property letters of those two extensions, as against their class
        # letters D<n> and I<n>. They exist (CRMdig v5.0, CRMinf v1.0) and the
        # datamodel declares four of them, but J7 is already claimed by the
        # inference apparatus: the importer lists it in ARTEFACT_PREDICATES as
        # part of the belief skeleton. Emitting it as `extracted_from`'s
        # signature makes the importer discard the triple and the edge is lost
        # on the return leg — measured, 11 round-trip tests. The collision is
        # real and needs a decision about which reading of J7 wins, not a
        # widened heuristic.
        if first in ("E", "P"):
            return CRM[full]
    if code[:2] in ("SP", "OA") or code[:1] == "Q":
        return CRMGEO[full]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# AP11 type_tag → em: subproperty (CRMarchaeo physical relation discrimination)
# ─────────────────────────────────────────────────────────────────────────────

def ap11_subprops(connections_datamodel: Dict[str, Any]) -> Dict[str, URIRef]:
    """``type_tag`` → ``em:`` subproperty, read from the connections datamodel.

    Every edge of the AP11 family declares both in its ``mapping``
    (``"type_tag": "bonded to"``, ``"subproperty": "em:bondedTo"``, connections
    1.6.32). Two spellings of one relation share a subproperty, so the table
    has fewer values than keys. A tag without a subproperty is left out: the
    edge still leaves as the generic AP11.
    """
    out: Dict[str, URIRef] = {}
    for entry in (connections_datamodel.get("edge_types") or {}).values():
        mapping = (entry or {}).get("mapping") or {}
        tag, sub = mapping.get("type_tag"), mapping.get("subproperty")
        if tag and isinstance(sub, str) and sub.startswith("em:"):
            out.setdefault(tag, EM[sub[len("em:"):]])
    return out


with open(Path(__file__).parent.parent / "JSON_config" / "s3Dgraphy_connections_datamodel.json",
          encoding="utf-8") as _fh:
    #: Until connections 1.6.31 this was a list of its own, here; now the
    #: datamodel holds the pairing and this is read from it once.
    AP11_SUBPROPS: Dict[str, URIRef] = ap11_subprops(json.load(_fh))


# ─────────────────────────────────────────────────────────────────────────────
# Datamodel loader (caches the three JSON datamodels)
# ─────────────────────────────────────────────────────────────────────────────

class _Datamodel:
    """Reads and indexes the three JSON datamodels once per exporter instance."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "JSON_config"
        self.config_dir = Path(config_dir)

        self.node_datamodel        = self._load_json("s3Dgraphy_node_datamodel.json")
        self.connections_datamodel = self._load_json("s3Dgraphy_connections_datamodel.json")
        self.qualia_types          = self._load_json("em_qualia_types.json")

        self._node_class_index: Dict[str, Dict[str, Any]] = {}
        self._build_node_class_index(self.node_datamodel)

        self._qualia_class_index: Dict[str, str] = {}
        #: the qualia whose value is text in a natural language (em_qualia_types
        #: `natural_language: true`), read by is_natural_language
        self._qualia_natural_language: set = set()
        self._build_qualia_index(self.qualia_types)

        #: reverse edge name → canonical edge name. The connections datamodel
        #: declares `reverse` on every non-symmetric canonical but keys the
        #: dictionary by the CANONICAL name only, so a graph holding an
        #: `is_before` edge finds nothing here unless we index the other
        #: direction ourselves. See resolve_edge_direction().
        self._reverse_of: Dict[str, str] = {}
        for _canon, _entry in (self.connections_datamodel.get("edge_types") or {}).items():
            _rev = (_entry or {}).get("reverse") or {}
            _rev_name = _rev.get("name")
            if _rev_name:
                self._reverse_of[_rev_name] = _canon

    def _load_json(self, name: str) -> Dict[str, Any]:
        path = self.config_dir / name
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _build_node_class_index(self, node: Any) -> None:
        """Recursive descent collecting every entry with a 'class' field."""
        if isinstance(node, dict):
            cls = node.get("class")
            if isinstance(cls, str):
                self._node_class_index[cls] = node
            for v in node.values():
                self._build_node_class_index(v)
        elif isinstance(node, list):
            for item in node:
                self._build_node_class_index(item)

    def _build_qualia_index(self, qualia_doc: Dict[str, Any]) -> None:
        for cat in qualia_doc.get("qualia_categories", []):
            for sub in (cat.get("subcategories") or {}).values():
                for q in sub.get("qualia", []) or []:
                    qid = q.get("id")
                    mappings = q.get("mappings") or {}
                    crm_class = mappings.get("cidoc_crm")
                    if qid and crm_class:
                        self._qualia_class_index[qid] = crm_class
                    if qid and q.get("natural_language") is True:
                        self._qualia_natural_language.add(qid)

    # ─── public lookups ─────────────────────────────────────────────────────

    def get_node_primary_iri(self, class_name: str) -> Optional[URIRef]:
        """em_extension.uri preferred; falls back to mapping.cidoc."""
        entry = self._node_class_index.get(class_name)
        if not entry:
            return None
        ext = entry.get("em_extension") or {}
        uri = ext.get("uri")
        if uri:
            resolved = _resolve_prefixed(uri)
            if resolved:
                return resolved
        mapping = entry.get("mapping") or {}
        return _resolve_prefixed(mapping.get("cidoc"))

    def get_node_superclasses(self, class_name: str) -> List[URIRef]:
        """All em_extension.subclass_of IRIs (multi-typing)."""
        entry = self._node_class_index.get(class_name)
        if not entry:
            return []
        ext = entry.get("em_extension") or {}
        result: List[URIRef] = []
        for sc in ext.get("subclass_of", []) or []:
            iri = _resolve_prefixed(sc)
            if iri is not None:
                result.append(iri)
        return result

    def resolve_edge_direction(self, edge_type: str) -> Tuple[str, bool]:
        """``edge_type`` → ``(canonical_name, inverted)``.

        RDF has no reading direction: `A is_after B` and `B is_before A` state
        the same fact, and a triple store should not be able to tell which way
        the author happened to draw it. So a reverse edge resolves to its
        canonical name with ``inverted=True``, and the caller swaps subject and
        object. Every stratigraphic relation then leaves in one shape, and a
        SPARQL query written against the canonical predicate finds all of them.

        An unknown or already-canonical name comes back unchanged with
        ``inverted=False``.
        """
        canon = self._reverse_of.get(edge_type)
        drawn_reversed = canon is not None
        canonical = canon if drawn_reversed else edge_type

        # A mapping may itself run against the edge. `is_after` points from the
        # more recent unit to the more ancient one, while P120/AP28 put the
        # EARLIER entity in the subject position — so emitting source-first
        # states the sequence backwards. The datamodel declares this with
        # `mapping.rdf_subject: "target"` rather than the exporter knowing it
        # about one edge by name, because the next mapping with the same shape
        # should be a data change, not a code change.
        entry = (self.connections_datamodel.get("edge_types") or {}).get(canonical) or {}
        mapping_inverts = ((entry.get("mapping") or {}).get("rdf_subject") == "target")

        # The two inversions compose: an edge drawn the reverse way, under a
        # mapping that itself inverts, comes out the right way round. So
        # `A is_after B` and `B is_before A` land on the same correct triple.
        return canonical, (drawn_reversed != mapping_inverts)

    def get_edge_mapping(self, edge_type: str) -> Tuple[Optional[URIRef], Optional[URIRef], Optional[str], bool]:
        """
        Returns (predicate_iri, extension_iri, type_tag, deprecated).

        predicate_iri  — the core predicate from mapping.cidoc.
        extension_iri  — the resolved mapping.extension_mapping predicate
                         (e.g. em:hasVisualReference, em:survivesInEpoch),
                         or None when absent/unresolvable. The caller emits
                         BOTH, generalising the AP11 dual-emission pattern:
                         specific em: subproperty for expressive SPARQL,
                         generic CRM predicate for CRM-only readers.
        type_tag is set for the AP11 family — caller resolves the specific
        subproperty via AP11_SUBPROPS. deprecated edges should be skipped on
        write (already canonicalised aliases like has_timebranch).
        """
        edges = self.connections_datamodel.get("edge_types", {})
        canonical, _inverted = self.resolve_edge_direction(edge_type)
        entry = edges.get(canonical) or {}
        if not entry:
            return None, None, None, False
        deprecated = bool(entry.get("deprecated"))
        mapping = entry.get("mapping") or {}
        type_tag = mapping.get("type_tag")
        cidoc = mapping.get("cidoc")
        # extension_mapping may carry a legacy parenthesised reverse label,
        # e.g. "AP13_has_stratigraphic_relation_to (is_stratigraphic_relation_of)"
        # — strip it before resolution.
        ext_raw = mapping.get("extension_mapping")
        if isinstance(ext_raw, str) and "(" in ext_raw:
            ext_raw = ext_raw.split("(", 1)[0].strip()
        ext_iri = _resolve_prefixed(ext_raw)
        # AP11 family: prefer the generic AP11 predicate; caller adds subproperty.
        if type_tag:
            return CRMARCHAEO.AP11_has_physical_relation_to, None, type_tag, deprecated
        return _resolve_prefixed(cidoc), ext_iri, None, deprecated

    def get_extension_guard(self, edge_type: str) -> Optional[List[str]]:
        """Target node classes the declared extension predicate is valid for.

        An extension predicate can be NARROWER than the core one it sits
        beside. `is_part_of` projects to P46i for every containment, but
        CRMarchaeo's AP21i ranges strictly over A2 Stratigraphic Volume Unit —
        which here is only `StratigraphicUnit`: USD and the virtual units map
        to A8, VSF to E89/E19, a FunctionalUnit to E24. Emitted at those
        targets, AP21i would be range-inconsistent, so the datamodel declares
        `mapping.extension_when.target_node_class` and the exporter honours it.

        The guard lives in the data, not in a name this function knows, because
        the next narrower extension should be a datamodel change and not a code
        change — the same reason `mapping.rdf_subject` exists.

        Returns None when no guard is declared, meaning no restriction.
        """
        classes = (self.get_extension_condition(edge_type) or {}).get("target_node_class")
        return list(classes) if classes else None

    def get_extension_condition(self, edge_type: str) -> Optional[Dict[str, List[str]]]:
        """The whole ``mapping.extension_when`` of an edge: the classes the
        LOGICAL source (``source_node_class``) and target (``target_node_class``)
        must have for the extension predicate to be emitted. None when the
        extension is unconditional.

        The target guard came first (is_part_of → AP21i, 2026-09-25); the source
        guard is has_documentation → em:derivedFromDocument (connections 1.6.33),
        whose domain is the USD, the side the edge starts from."""
        edges = self.connections_datamodel.get("edge_types", {})
        canonical, _inv = self.resolve_edge_direction(edge_type)
        entry = edges.get(canonical) or {}
        when = (entry.get("mapping") or {}).get("extension_when") or {}
        out = {key: list(when[key]) for key in ("source_node_class", "target_node_class")
               if when.get(key)}
        return out or None

    def get_inverse_extension(self, edge_type: str
                              ) -> Optional[Tuple[URIRef, Dict[str, List[str]]]]:
        """``mapping.inverse_extension``: a predicate that restates the edge FROM
        THE OTHER SIDE (``<target> pred <source>``), and the classes the logical
        source and target must have. is_part_of → em:reconstructsFrom (a VSF is
        reconstructed from the SF that is part of it), connections 1.6.33."""
        edges = self.connections_datamodel.get("edge_types", {})
        canonical, _inv = self.resolve_edge_direction(edge_type)
        entry = edges.get(canonical) or {}
        inverse = (entry.get("mapping") or {}).get("inverse_extension") or {}
        predicate = _resolve_prefixed(inverse.get("predicate"))
        if predicate is None:
            return None
        when = inverse.get("when") or {}
        return predicate, {key: list(when[key])
                           for key in ("source_node_class", "target_node_class")
                           if when.get(key)}

    def inverse_extension_predicates(self) -> List[URIRef]:
        """Every predicate declared as an inverse_extension — the importer skips
        them, since the edge comes back from its core predicate."""
        out = []
        for edge_type in (self.connections_datamodel.get("edge_types") or {}):
            found = self.get_inverse_extension(edge_type)
            if found is not None and found[0] not in out:
                out.append(found[0])
        return out

    def edge_predicate_declared_absent(self, edge_type: str) -> bool:
        """True when the datamodel says, in so many words, that this edge has
        no CRM predicate — `mapping.cidoc` present and empty.

        The distinction matters because the two silences are different. An edge
        type the datamodel does not know at all is an accident, and the caller's
        P130 fallback keeps it from vanishing. An edge whose `cidoc` was emptied
        DELIBERATELY (is_in_activity, 2026-09-21: neither P9i nor P129i holds
        its domain, and nothing was invented in the gap) must not be given a
        predicate by a fallback — P130_shows_features_of is a live IRI making a
        claim about shared features, which is a different false statement from
        the one that was removed.
        """
        edges = self.connections_datamodel.get("edge_types", {})
        canonical, _inv = self.resolve_edge_direction(edge_type)
        entry = edges.get(canonical) or {}
        mapping = entry.get("mapping") or {}
        return "cidoc" in mapping and not (mapping.get("cidoc") or "").strip()

    def get_node_element_rule(self, node: Any, element: str) -> Optional[Dict[str, Any]]:
        """The declaration of a NODE ELEMENT (``properties.<element>`` given as
        an object, e.g. ``StratigraphicNode.properties.definition``), inherited
        down the class hierarchy: the first class in the MRO of ``node`` (a node
        or a node class) whose datamodel entry declares it answers. A plain
        string value (``"name": "P1_is_identified_by"``) is a mapping note, not
        a declaration, and is not returned."""
        klass = node if isinstance(node, type) else type(node)
        for klass in klass.__mro__:
            entry = self._node_class_index.get(klass.__name__) or {}
            rule = (entry.get("properties") or {}).get(element)
            if isinstance(rule, dict):
                return rule
        return None

    def is_natural_language(self, node: Any, prop: str) -> bool:
        """Is this property of this node TEXT IN A NATURAL LANGUAGE? THE one
        answer (la lingua dei dati, 2026-09-28): the exporter tags a literal only
        when this says yes, and the importer reads a tag back only from one.

        * a node property (``description``…): the first class in the MRO of
          ``node`` (a node or a node class) whose datamodel entry declares
          ``properties.<prop>`` as an object carrying ``natural_language``
          answers. A plain string there is a mapping note and does not withdraw
          what an ancestor declared — node datamodel 1.6.19 marks
          ``Node.properties.description``, and every class inherits it.
        * the ``value`` of a PropertyNode: the quale its property_type names
          (resolved as :meth:`get_qualia_crm_iri` resolves it) carries
          ``natural_language: true`` in em_qualia_types — ``narrative_content``
          does, ``inventory_number`` (a code, though a string) does not.

        ``name`` is marked nowhere, and so is never tagged."""
        if prop == "value" and getattr(node, "node_type", None) == "property":
            ptype = getattr(node, "property_type", None)
            if not ptype or str(ptype).lower() == "string":
                ptype = getattr(node, "name", None)
            return self._qualia_key(ptype, self._qualia_natural_language) is not None
        klass = node if isinstance(node, type) else type(node)
        for klass in klass.__mro__:
            entry = self._node_class_index.get(klass.__name__) or {}
            rule = (entry.get("properties") or {}).get(prop)
            if isinstance(rule, dict) and "natural_language" in rule:
                return rule.get("natural_language") is True
        return False

    @staticmethod
    def _qualia_key(property_type: Optional[str], index) -> Optional[str]:
        """The quale id ``property_type`` names in ``index``, with the same four
        steps as :meth:`get_qualia_crm_iri` (exact, last dotted segment,
        lowercase, lowercase last segment)."""
        if not property_type:
            return None
        text = str(property_type)
        tail = text.rsplit(".", 1)[-1]
        for key in (text, tail, text.lower(), tail.lower()):
            if key in index:
                return key
        return None

    def get_qualia_crm_iri(self, property_type: Optional[str]) -> Optional[URIRef]:
        """Resolve a property_type string to its CIDOC class IRI.

        Lookup strategy (graceful, three steps):
          1. Exact match against em_qualia_types.json `id` (e.g.
             "absolute_time_start", "height", "color").
          2. Last segment after dot — handles EM yEd convention where
             properties are labelled with a category prefix
             (e.g. "Dimension.height" → "height", "Spatial.elevation" →
             "elevation").
          3. Lowercase match — handles minor case mismatches between
             graphml labels and qualia ids (e.g. "Height" → "height").

        Returns None if no strategy matches; the caller (typically
        ``_compute_primary_iri``) falls back to the generic PropertyNode
        default mapping.
        """
        if not property_type:
            return None
        # 1) Exact match
        crm = self._qualia_class_index.get(property_type)
        if crm:
            return _resolve_prefixed(crm)
        # 2) Last segment after dot (yEd category prefix convention)
        if "." in property_type:
            tail = property_type.rsplit(".", 1)[-1]
            crm = self._qualia_class_index.get(tail)
            if crm:
                return _resolve_prefixed(crm)
        # 3) Lowercase fallback
        crm = self._qualia_class_index.get(property_type.lower())
        if crm:
            return _resolve_prefixed(crm)
        # 4) Combined: lowercase last segment
        if "." in property_type:
            tail_lower = property_type.rsplit(".", 1)[-1].lower()
            crm = self._qualia_class_index.get(tail_lower)
            if crm:
                return _resolve_prefixed(crm)
        return None


def _narrative_authors_from_data(data: Dict[str, Any]) -> List[str]:
    """Author ids read out of a serialised narrative payload (chapters and
    blocks), for the case where the node degraded to a base ``Node``."""
    seen, out = set(), []
    for chapter in data.get("chapters") or []:
        for key in ("authored_by",):
            value = (chapter or {}).get(key)
            if value and value not in seen:
                seen.add(value)
                out.append(value)
        for block in (chapter or {}).get("blocks") or []:
            for key in ("authored_by", "validated_by"):
                value = (block or {}).get(key)
                if value and value not in seen:
                    seen.add(value)
                    out.append(value)
    return out


def _narrative_validators(node: Any, data: Dict[str, Any]) -> List[str]:
    """The humans who have endorsed content in this narrative."""
    seen, out = set(), []
    blocks = ([b for _c, b in node.blocks_iter()]
              if hasattr(node, "blocks_iter") else [])
    if blocks:
        values = [getattr(b, "validated_by", None) for b in blocks]
    else:
        values = [(b or {}).get("validated_by")
                  for c in (data.get("chapters") or [])
                  for b in ((c or {}).get("blocks") or [])]
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _narrative_refs_from_data(data: Dict[str, Any]) -> List[str]:
    """Referenced ids read straight out of a serialised narrative payload.

    Used when the node arrives as a plain ``Node`` — a reader older than the
    NarrativeNode class still carries the chapters in ``data``, and the
    projection should not lose the references just because the class was not
    recognised.
    """
    seen, out = set(), []
    for chapter in data.get("chapters") or []:
        for block in (chapter or {}).get("blocks") or []:
            ref = (block or {}).get("ref")
            if ref and ref not in seen:
                seen.add(ref)
                out.append(ref)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main exporter
# ─────────────────────────────────────────────────────────────────────────────

class RDFExporter:
    """
    Export s3Dgraphy graphs to RDF formats.

    Usage:
        exporter = RDFExporter("out.ttl", format="turtle")
        exporter.export_graphs()                  # all graphs
        exporter.export_graphs(["my_site"])       # specific ones
    """

    SUPPORTED_FORMATS: Dict[str, Tuple[str, str]] = {
        # alias        : (filename_extension, rdflib_format)
        "turtle":      ("ttl",    "turtle"),
        "ttl":         ("ttl",    "turtle"),
        "n-triples":   ("nt",     "nt"),
        "ntriples":    ("nt",     "nt"),
        "nt":          ("nt",     "nt"),
        "n-quads":     ("nq",     "nquads"),
        "nquads":      ("nq",     "nquads"),
        "trig":        ("trig",   "trig"),
        "json-ld":     ("jsonld", "json-ld"),
        "jsonld":      ("jsonld", "json-ld"),
        "rdf-xml":     ("rdf",    "xml"),
        "xml":         ("rdf",    "xml"),
    }

    #: The two readings of an RDF projection, and they disagree about the dead.
    #:
    #: ``round_trip`` (default) is the isomorphic one: a tombstone is a FACT
    #: about the graph and travels as ``EM.removedAt`` / ``EM.removedBy``, which
    #: is what makes ttl → em.json give back what went in.
    #: ``publish`` is a dissemination surface: the dead are ABSENT — no node, no
    #: ``removedAt``, no edge dangling on the hole. See
    #: :mod:`s3dgraphy.dissemination` for the per-surface policy.
    #:
    #: The same line holds for what no person verified (ai_validation, E.D.
    #: 2026-09-29): the round trip is a technical transformation, not a
    #: publication, so an AI-made node travels with its ``ai_assisted`` marker
    #: and comes back unvalidated; ``publish`` is an exit towards others and
    #: leaves it out, or — ``include_unvalidated=True`` — carries it with «⚠︎».
    #:
    #: The default is round_trip on purpose: publishing is a deliberate act, and
    #: a projection that silently dropped information would be the wrong kind of
    #: helpful.
    MODES = ("round_trip", "publish")

    def __init__(self,
                 output_path: str,
                 format: str = "turtle",
                 base_uri: str = DEFAULT_BASE_URI,
                 parent_hdt_iri: Optional[str] = None,
                 config_dir: Optional[Path] = None,
                 mode: str = "round_trip",
                 include_unvalidated: bool = False):
        """
        Args:
            output_path: target file path (extension auto-fixed by format).
            format: 'turtle' (default), 'n-triples', 'json-ld', 'trig', 'xml'.
            base_uri: base URI for minted node IRIs.
            mode: 'round_trip' (default: keeps tombstones and unvalidated AI
                nodes, so ttl → graph gives back what went in) or 'publish'
                (drops both). See :attr:`MODES`.
            parent_hdt_iri: if set, every exported EMGraph (HC16) gets a
                triple `<emgraph> hdto:HP33i_is_proposition_set_of <parent>`
                binding it as a proposition set of the given HC2 Heritage
                Digital Twin. The parent HDT IRI is also declared as
                rdf:type hdto:HC2_Heritage_Digital_Twin so a SPARQL query
                can discover the parent without a separate type assertion.
            config_dir: override location of JSON_config/ (default: alongside exporter).
            include_unvalidated: only for ``publish``. A node made with AI
                that no person verified (ai_validation) is left out of a
                publication by default; True keeps it, with «⚠︎» at the start
                of each touched literal. ``self.excluded`` lists what was left
                out or flagged. In ``round_trip`` nothing is left out and
                nothing is flagged — the marker travels as em:aiAssistedBy /
                em:aiModel / em:aiPromptRef / em:aiAssistedField — so asking
                for it there is an error, not a no-op.
        """
        fmt = (format or "turtle").lower()
        if fmt not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported RDF format '{format}'. Supported: "
                f"{sorted(set(self.SUPPORTED_FORMATS.keys()))}"
            )
        self.format_key = fmt
        if mode not in self.MODES:
            raise ValueError(
                f"Unsupported RDF mode {mode!r}. Supported: {list(self.MODES)}"
            )
        if include_unvalidated and mode != "publish":
            raise ValueError(
                "include_unvalidated only applies to mode='publish': the "
                "round trip already carries every AI-made node, unflagged")
        self.mode = mode
        self.include_unvalidated = bool(include_unvalidated)
        self.excluded: List[Dict[str, Any]] = []
        self.ext, self.rdflib_format = self.SUPPORTED_FORMATS[fmt]
        self.output_path = self._adjust_extension(output_path)
        self.base_uri = base_uri.rstrip("/") + "/"
        self.parent_hdt_iri = self._normalize_iri(parent_hdt_iri)
        self.datamodel = _Datamodel(config_dir=config_dir)

        # Stats for the caller (verbose logging, eval)
        self.stats: Dict[str, int] = {
            "graphs": 0, "nodes": 0, "edges_emitted": 0,
            "edges_skipped_deprecated": 0, "edges_unmapped": 0,
            "nodes_unmapped": 0,
            "parent_hdt_bindings": 0,
            # what `publish` left out; stays 0 in round_trip, where nothing is
            # left out and saying so is the point
            "removed_hidden": 0,
            # definitions that carried a label and no concept URI, and so
            # projected to whatever `rdf.label_only` says (by default: nothing)
            "definitions_label_only": 0,
            # nodes made with AI that no person verified, in `publish`: left
            # out (default) or kept with the mark (include_unvalidated); 0 in
            # round_trip, where they travel as they are
            "ai_unvalidated": 0,
            # la lingua dei dati: literals of the properties the datamodel marks
            # as natural language, by where their tag came from — the node's own
            # data.lang, or the study's working language — and the ones that
            # left WITHOUT a tag because no language was ever declared (never
            # guessed). A declared `und` is tagged, and counted under its origin.
            "literals_tagged_node": 0,
            "literals_tagged_study": 0,
            "literals_untagged": 0,
        }
        #: the working language of the graph being serialised (language.py)
        self._study_lang: Optional[str] = None
        #: node id → its TranslationNodes, in the graph being serialised
        self._translations_of: Dict[str, List[Any]] = {}

    @staticmethod
    def _normalize_iri(value: Optional[str]) -> Optional[str]:
        """Trim and lightly validate an IRI for the parent HDT binding.

        Accepts absolute http(s) URIs and urn: identifiers. Returns None for
        empty/whitespace inputs (treated as 'no binding requested'). Raises
        ValueError on clearly malformed input so the caller fails loudly
        rather than emitting a broken triple.
        """
        if value is None:
            return None
        v = value.strip()
        if not v:
            return None
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("urn:")):
            raise ValueError(
                f"parent_hdt_iri must be an absolute IRI (http://, https:// or urn:); got: {v!r}"
            )
        return v

    # ── public entry points ─────────────────────────────────────────────────

    def export_graphs(self, graph_ids: Optional[List[str]] = None) -> str:
        """Serialize specified (or all) graphs into one RDF document. Returns output path."""
        if graph_ids is None:
            graph_ids = get_all_graph_ids()

        store = ConjunctiveGraph()
        self._bind_namespaces(store)

        for gid in graph_ids:
            g = get_graph(gid)
            if g is None:
                continue
            ctx = store.get_context(self._graph_iri(g))
            self._serialize_graph(g, ctx)
            self.stats["graphs"] += 1

        store.serialize(destination=self.output_path, format=self.rdflib_format)
        return self.output_path

    def export_single_graph(self, graph: S3DGraph) -> str:
        """Serialize an in-memory graph directly (no MultiGraphManager lookup)."""
        store = ConjunctiveGraph()
        self._bind_namespaces(store)
        ctx = store.get_context(self._graph_iri(graph))
        self._serialize_graph(graph, ctx)
        self.stats["graphs"] += 1
        store.serialize(destination=self.output_path, format=self.rdflib_format)
        return self.output_path

    def export_container(self, container) -> str:
        """Serialize a whole PROJECT: every member graph plus its version (P3).

        The project is a subject of its own — `<base>project/<digest>` — because
        the version is a fact about the project and not about any one graph.
        Each member is declared part of it, so a reader can go from a graph to
        the revision it belongs to without knowing how the file was arranged.
        """
        store = ConjunctiveGraph()
        self._bind_namespaces(store)
        members = list(container.graphs.values())
        if getattr(container, "shelf", None) is not None:
            members.append(container.shelf)
        for graph in members:
            ctx = store.get_context(self._graph_iri(graph))
            self._serialize_graph(graph, ctx)
            self.stats["graphs"] += 1
        self._serialize_project_version(container, store)
        store.serialize(destination=self.output_path, format=self.rdflib_format)
        return self.output_path

    def _serialize_project_version(self, container, store) -> None:
        """The light-weight versioning triples: PROV + DCTERMS, and no DTC.

        `prov:wasRevisionOf` is the standard way to say "this grew out of that",
        and `dcterms:hasVersion` carries the number people say out loud. The DTC
        (crmdig:D7 and friends) is deliberately NOT used: it records how a
        digital object was MADE, and using it to track that a document changed
        would be a category error — a DTC tracking the DTC.

        OPEN (confirm_with: Felicetti): a CIDOC-native reading would make each
        revision an E73 with a P148/E13 chain or an F-series work/expression
        split; PROV/DCTERMS is the defensible default for a counter and a
        pointer, which is all this is.
        """
        version = getattr(container, "version", None)
        if version is None:
            return
        project_iri = URIRef(f"{self.base_uri}project/{_iri_local(version.id or 'unversioned')}")
        ctx = store.get_context(project_iri)
        ctx.add((project_iri, RDF.type, PROV.Entity))
        ctx.add((project_iri, RDF.type, CRM.E73_Information_Object))
        ctx.add((project_iri, DCTERMS.hasVersion, Literal(str(version.number))))
        if version.id:
            ctx.add((project_iri, DCTERMS.identifier, Literal(version.id)))
        if version.was_revision_of:
            ctx.add((project_iri, PROV.wasRevisionOf,
                     URIRef(f"{self.base_uri}project/"
                            f"{_iri_local(version.was_revision_of)}")))
        if version.modified_at:
            ctx.add((project_iri, DCTERMS.modified,
                     Literal(str(version.modified_at), datatype=XSD.dateTime)))
        members = list(container.graphs.values())
        if getattr(container, "shelf", None) is not None:
            members.append(container.shelf)
        for graph in members:
            ctx.add((self._graph_iri(graph), DCTERMS.isPartOf, project_iri))
        self.stats["project_versions"] = self.stats.get("project_versions", 0) + 1

    # ── path/format helpers ─────────────────────────────────────────────────

    def _adjust_extension(self, path: str) -> str:
        """Ensure the file path ends with the format-correct extension.

        Defensive against the leading-dot trap: a basename like ".ttl" is
        treated by pathlib.Path as a hidden-file name (no suffix), so
        ``with_suffix(".ttl")`` would produce ".ttl.ttl". We detect that case
        and leave the path untouched if its name IS already the wanted ext.
        """
        p = Path(path)

        # Leading-dot trap: basename equals "." + wanted ext (e.g. ".ttl")
        # → treat as already correct, don't double-append.
        if p.name.startswith('.') and p.name.lower().lstrip('.') == self.ext.lower():
            return str(p)

        current_ext = p.suffix.lstrip(".").lower()
        if current_ext != self.ext.lower():
            return str(p.with_suffix("." + self.ext))
        return str(p)

    def _bind_namespaces(self, g: ConjunctiveGraph) -> None:
        for prefix, ns in PREFIX_MAP.items():
            g.bind(prefix, ns)

    # ── IRI minting ─────────────────────────────────────────────────────────

    def _graph_iri(self, g: S3DGraph) -> URIRef:
        return URIRef(f"{self.base_uri}graph/{g.graph_id}")

    def _node_iri(self, graph_id: str, node_id: str) -> URIRef:
        # rdflib URIRef does not URL-encode by default — keep node_id safe.
        safe = str(node_id).replace(" ", "_")
        return URIRef(f"{self.base_uri}graph/{graph_id}/node/{safe}")

    # ── value extraction (graph.name / .description can be dict or str) ─────

    @staticmethod
    def _to_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get("default") or next(iter(value.values()), None)
        if isinstance(value, str):
            return value
        return str(value)

    # ── graph-level serialization ───────────────────────────────────────────

    def _serialize_graph(self, g: S3DGraph, ctx) -> None:
        # `publish` is a dissemination surface, so the dead are dropped ONCE
        # here — before nodes, before edges, before the belief post-pass, which
        # all read `g` and would otherwise each need their own filter.
        if self.mode == "publish":
            from ..dissemination import live_view
            g, hidden = live_view(g, surface="rdf:publish")
            self.stats["removed_hidden"] += hidden.total
            # What no person verified is not published (ai_validation): once,
            # here, for the same reason as the tombstones above. The round trip
            # skips this on purpose: it is a transformation, not a publication.
            from ..ai_validation import export_view
            g, ai_rows = export_view(
                g, include_unvalidated=self.include_unvalidated)
            self.excluded.extend(ai_rows)
            self.stats["ai_unvalidated"] += len(ai_rows)
        graph_iri = self._graph_iri(g)

        ctx.add((graph_iri, RDF.type, EM.EMGraph))
        ctx.add((graph_iri, RDF.type, CRM.E73_Information_Object))
        ctx.add((graph_iri, RDF.type, PROV.Bundle))
        # em:EMGraph rdfs:subClassOf hdto:HC16 is declared in em.ttl, but we
        # also emit the HC16 type explicitly so HDT-O-aware consumers that
        # don't run an OWL reasoner can find the proposition set directly.
        ctx.add((graph_iri, RDF.type, HDTO.HC16_Heritage_Proposition_Set))

        # Parent HDT binding (HP33i is_proposition_set_of) — when configured,
        # every exported EMGraph is declared as a proposition set of the
        # given HC2 HDT. We also emit a type triple for the parent so its
        # role is discoverable via SPARQL without external coordination.
        if self.parent_hdt_iri:
            parent_iri = URIRef(self.parent_hdt_iri)
            ctx.add((graph_iri, HDTO.HP33i_is_proposition_set_of, parent_iri))
            ctx.add((parent_iri, RDF.type, HDTO.HC2_Heritage_Digital_Twin))
            self.stats["parent_hdt_bindings"] += 1

        # The study's working language (language.py): declared on the graph as
        # dcterms:language, and the second step of every text literal's cascade.
        from ..language import working_language
        self._study_lang = working_language(g)
        if self._study_lang:
            ctx.add((graph_iri, DCTERMS.language, Literal(self._study_lang)))
        # The translations (translation.py), by the node they translate: each
        # adds a literal on the predicate of its field. Read off THIS `g` — in
        # `publish` the view without the unverified AI ones, so what is left out
        # is left out everywhere at once.
        self._translations_of = self._index_translations(g)

        # The graph's name is a name (untagged); its description is text, in the
        # study's language when one is declared — a graph has no data.lang.
        gname = self._to_text(getattr(g, "name", None))
        if gname:
            ctx.add((graph_iri, RDFS.label, Literal(gname)))
        gdesc = self._to_text(getattr(g, "description", None))
        if gdesc:
            ctx.add((graph_iri, DCTERMS.description, self._tagged(gdesc, None)))

        data = getattr(g, "data", {}) or {}
        for aid in data.get("authors", []) or []:
            ctx.add((graph_iri, CRM.P94_has_created,
                     self._node_iri(g.graph_id, aid)))
        license_val = data.get("license")
        if license_val:
            ctx.add((graph_iri, CRM.P104_is_subject_to, Literal(license_val)))
        # BUGFIX-CANVAS-IMPORT (2026-08-06): the canonical canvas-scope key is
        # `embargo` (what CANVAS1 writes and the funnel reads); `embargo_until` is
        # the legacy key. Read the canonical first, fall back to legacy so old
        # em.json still exports. ONE read, one meaning.
        embargo = data.get("embargo") or data.get("embargo_until")
        if embargo:
            ctx.add((graph_iri, EM.embargoUntil, Literal(embargo)))

        # Nodes
        for node in g.nodes:
            self._serialize_node(g, node, ctx)

        # Edges
        for edge in g.edges:
            self._serialize_edge(g, edge, ctx)

        # A property with several owners (ownership.py): every owner's
        # has_property went out above as em:hasQualia, the inheriting ones are
        # also declared as em:inheritsQualia (a subproperty), so the original
        # owner is still readable from the triplestore and the importer can put
        # the declaration back on the edge.
        from ..ownership import is_inherited_edge
        for edge in g.edges:
            if edge.edge_type == "has_property" and is_inherited_edge(edge):
                ctx.add((self._node_iri(g.graph_id, edge.edge_source),
                         EM.inheritsQualia,
                         self._node_iri(g.graph_id, edge.edge_target)))

        # CRMinf belief propositions (J4 → I17) — needs the full edge
        # topology, so it runs as a post-pass after nodes and edges.
        self._emit_belief_propositions(g, ctx)

    def _emit_belief_propositions(self, g: S3DGraph, ctx) -> None:
        """J4 linking: connect each argumentation belief to its proposition.

        Design (WP3 coverage analysis, Appendix D.3, approved E.D.
        2026-07-11). The belief skeleton (<arg> J2_concluded_that
        <arg>/belief, typed I2) is emitted per argumentation node by
        ``_emit_belief_skeleton``. This post-pass adds WHAT each belief
        concludes, derived from the existing graph topology — the user
        never authors beliefs:

        * Property claim ("US12 has height 3.2 m"): for every chain
          unit --has_property--> property --has_data_provenance--> arg,
          emit an I17 One-Proposition Set at <property>/proposition:
              <i17> a crminf:I17_One-Proposition_Set ;
                    crminf:J30_has_domain <unit> ;
                    crminf:J32_has_property_type <s3d:qualia_TYPE> ;
                    crminf:J31_has_range "VALUE" .
              <arg>/belief crminf:J4_that <i17> .
          The J32 target is a placeholder E55 IRI in the s3d: namespace
          until the SKOS vocabulary layer (Appendix E) provides
          dereferenceable concept URIs.

        * Reconstruction claim ("there was a colonnade here"): when the
          justified property is the existence of a virtual-family unit
          (qualia id 'existence'), the proposition IS the unit itself —
          em:VirtualSU is declared subclass of crminf:I4 in em.ttl — so
          the belief links J4 directly to the unit and no I17 is minted.

        * J5 holds to be: when the same argumentation node also
          justifies a confidence_level property (typed I6_Belief_Value
          via the qualia catalogue), the belief links J5 to it.
        """
        VIRTUAL_TYPES = {"USVs", "USVn", "USD", "VSF",
                         "serUSVs", "serUSVn", "serUSD"}
        ARG_TYPES = {"extractor", "combiner"}

        node_by_id = {n.node_id: n for n in g.nodes}

        # property_id → [unit_id] — ALL the units that claim this property.
        # It was a single id, which meant a property with several parents lost
        # every attribution but one. See the I17-per-pair emission below.
        prop_units: Dict[str, List[str]] = {}
        # arg_id → [property_id] (has_data_provenance: property → arg)
        arg_props: Dict[str, List[str]] = {}

        for edge in g.edges:
            if edge.edge_type == "has_property":
                # Every parent is kept. This was first a plain assignment (so the
                # LAST edge won and the projection depended on edge ORDER — found
                # by the round-trip), then a deterministic min(). Both named ONE
                # unit, and a property claimed by three units then said so about
                # one: the other two attributions were simply absent from the
                # RDF. Now all of them are collected and each becomes its own
                # I17 below. Sorted, so the emission is order-independent.
                prop_units.setdefault(edge.edge_target, []).append(edge.edge_source)
            elif edge.edge_type == "has_data_provenance":
                tgt = node_by_id.get(edge.edge_target)
                if tgt is not None and getattr(tgt, "node_type", None) in ARG_TYPES:
                    arg_props.setdefault(edge.edge_target, []).append(edge.edge_source)

        for arg_id, prop_ids in arg_props.items():
            belief_iri = URIRef(str(self._node_iri(g.graph_id, arg_id)) + "/belief")
            for prop_id in prop_ids:
                prop_node = node_by_id.get(prop_id)
                if prop_node is None:
                    continue
                ptype = getattr(prop_node, "property_type", None)
                if not ptype or (isinstance(ptype, str) and ptype.lower() == "string"):
                    ptype = getattr(prop_node, "name", None) or "unknown"
                unit_ids = sorted(set(prop_units.get(prop_id, [])))

                # J5: confidence qualia → I6 Belief Value
                if str(ptype).lower().endswith("confidence_level"):
                    ctx.add((belief_iri, CRMINF.J5_holds_to_be,
                             self._node_iri(g.graph_id, prop_id)))
                    continue

                # Reconstruction claim: belief J4 → the virtual unit (⊂ I4).
                # Unchanged in meaning; it just runs per parent now, since a
                # property may be claimed by more than one.
                virtual_units = [
                    uid for uid in unit_ids
                    if getattr(node_by_id.get(uid), "node_type", None) in VIRTUAL_TYPES
                ]
                if virtual_units and str(ptype).lower().endswith("existence"):
                    for uid in virtual_units:
                        ctx.add((belief_iri, CRMINF.J4_that,
                                 self._node_iri(g.graph_id, uid)))
                        self.stats["belief_propositions"] = self.stats.get("belief_propositions", 0) + 1
                    continue

                # Property claim: ONE I17 One-Proposition Set PER (property, unit)
                # PAIR. A proposition is "THIS unit has THIS value for THIS
                # property" — so a property claimed by three units is three
                # propositions, not one with a chosen subject. Naming one and
                # dropping the others made the RDF quietly lossy, and no importer
                # could have recovered what was never written.
                #
                # The IRI carries the pair (`…/proposition/<unit_id>`), which is
                # what makes the set deterministic and re-readable: each I17 has
                # a stable name derived from the two things it relates, so
                # re-exporting the same graph mints the same IRIs whatever the
                # order of the edges. A property with no parent at all still gets
                # its bare `…/proposition` — the claim exists, its subject is
                # simply not stated.
                prop_iri = self._node_iri(g.graph_id, prop_id)
                qualia_iri = S3D["qualia_" + _iri_local(str(ptype).rsplit(".", 1)[-1])]
                raw_value = getattr(prop_node, "value", None)
                if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
                    raw_value = getattr(prop_node, "description", None)
                has_value = raw_value is not None and (
                    not isinstance(raw_value, str) or raw_value.strip())

                for uid in (unit_ids or [None]):
                    i17_iri = URIRef(
                        f"{prop_iri}/proposition/{_iri_local(uid)}" if uid
                        else f"{prop_iri}/proposition")
                    ctx.add((i17_iri, RDF.type, CRMINF["I17_One-Proposition_Set"]))
                    if uid:
                        ctx.add((i17_iri, CRMINF.J30_has_domain,
                                 self._node_iri(g.graph_id, uid)))
                    ctx.add((i17_iri, CRMINF.J32_has_property_type, qualia_iri))
                    ctx.add((qualia_iri, RDF.type, CRM.E55_Type))
                    if has_value:
                        ctx.add((i17_iri, CRMINF.J31_has_range, Literal(raw_value)))
                    ctx.add((belief_iri, CRMINF.J4_that, i17_iri))
                    self.stats["belief_propositions"] = self.stats.get("belief_propositions", 0) + 1

    # ── node serialization ──────────────────────────────────────────────────

    def _serialize_node(self, g: S3DGraph, node: Any, ctx) -> None:
        node_iri = self._node_iri(g.graph_id, node.node_id)
        cls_name = type(node).__name__
        node_type = getattr(node, "node_type", None)

        # Primary class — conditional for PropertyNode (qualia takes precedence)
        # and for an acquisition whose KIND declares its own class (a capture).
        kind_mapping = self._dtc_kind_mapping(node, node_type)
        if kind_mapping is not None:
            primary_iri, superclasses = kind_mapping
        else:
            primary_iri = self._compute_primary_iri(node, cls_name, node_type)
            superclasses = self.datamodel.get_node_superclasses(cls_name)
        if primary_iri is not None:
            ctx.add((node_iri, RDF.type, primary_iri))
        else:
            self.stats["nodes_unmapped"] += 1

        # Multi-type via subclass_of
        for sc in superclasses:
            ctx.add((node_iri, RDF.type, sc))

        # Base triples — label, description, identifier
        name = self._to_text(getattr(node, "name", None))
        if name:
            ctx.add((node_iri, RDFS.label, Literal(name)))
        desc = self._to_text(getattr(node, "description", None))
        if desc:
            ctx.add((node_iri, DCTERMS.description,
                     self._text_literal(node, "description", desc)))
        ctx.add((node_iri, DCTERMS.identifier, Literal(node.node_id)))

        # Which language is the ORIGINAL (le traduzioni, 2b): written whenever
        # the node itself declares one, equal to the study's or not — so the
        # round trip gives data.lang back where it was and nowhere else, and a
        # reader can tell the original literal from its translations. A
        # translation's own data.lang is its language of arrival, not an
        # original's: it leaves as P72 on the translation (_serialize_translation).
        if node_type != "translation":
            from ..language import node_language
            declared = node_language(node)
            if declared:
                ctx.add((node_iri, EM.originalLanguage, Literal(declared)))
            self._emit_translation_literals(g, node, node_iri, ctx)
        else:
            self._serialize_translation(g, node, node_iri, ctx)

        # Authority cross-references (P1-D) — GENERALISED to any node carrying
        # `data.authority_refs` (nodes AND qualia). Redundant by design: every
        # ranked ref is emitted, with the strength-aware predicate.
        self._serialize_authority_refs(node, node_iri, ctx)

        # AUDIT1 · the editorial stamps (who typed this, and when) — every node
        # type, so it belongs here and not in the per-type branches.
        self._serialize_editorial(node, node_iri, ctx)

        # The AI marker and the person's verification (ai_validation).
        self._serialize_ai(g, node, node_iri, ctx)

        # The unit's DEFINITION — an element of the node, declared (and its
        # projection with it) in the node datamodel.
        self._serialize_definition(node, node_iri, ctx)

        # Type-specific (node_type already computed above for primary IRI logic)
        self._serialize_type_specific(node, node_type, node_iri, ctx,
                                      graph_id=g.graph_id)

        self.stats["nodes"] += 1

    def _text_literal(self, node: Any, prop: str, value: Any) -> Literal:
        """THE literal of a node's text (la lingua dei dati, 2026-09-28).

        Asks the datamodel whether ``prop`` of ``node`` is natural language
        (:meth:`_Datamodel.is_natural_language`); if not — a name, a code, a
        number — the literal is plain, as it always was. If it is, the language
        comes in a cascade: the node's ``data.lang``, else the study's working
        language, else none, and the literal says so (``@it``, ``@und``, or no
        tag, counted in ``literals_untagged``). Never guessed from the text."""
        if not self.datamodel.is_natural_language(node, prop):
            return Literal(value)
        from ..language import node_language
        return self._tagged(value, node_language(node))

    def _tagged(self, value: Any, node_lang: Optional[str]) -> Literal:
        """The cascade's tail, shared with the graph's own description (which has
        only the study step)."""
        if node_lang:
            self.stats["literals_tagged_node"] += 1
            return Literal(value, lang=node_lang)
        if self._study_lang:
            self.stats["literals_tagged_study"] += 1
            return Literal(value, lang=self._study_lang)
        self.stats["literals_untagged"] += 1
        return Literal(value)

    #: the field of a translation → the predicate its literal joins on the
    #: translated node (the same predicate the original leaves with). A field
    #: with no literal of its own on the node (another data.<key>) has none:
    #: the translation still leaves as its own resource.
    _TRANSLATED_FIELD_PREDICATE = {"description": DCTERMS.description,
                                   "data.value": CRM.P90_has_value}

    @staticmethod
    def _index_translations(g: S3DGraph) -> Dict[str, List[Any]]:
        by_id = {n.node_id: n for n in g.nodes}
        out: Dict[str, List[Any]] = {}
        for e in g.edges:
            if e.edge_type != "has_translation":
                continue
            t = by_id.get(e.edge_target)
            if t is not None and getattr(t, "node_type", None) == "translation":
                out.setdefault(e.edge_source, []).append(t)
        return out

    def _emit_translation_literals(self, g: S3DGraph, node: Any,
                                   node_iri: URIRef, ctx) -> None:
        """One more literal per translation, on the predicate of its field and
        with its own tag (``dcterms:description "…"@it`` beside the original
        ``"…"@la``). A translation «da riallineare» (its original changed)
        does not join: it no longer translates what the node says, and only
        its own resource leaves."""
        from ..translation import is_stale
        for t in self._translations_of.get(node.node_id, ()):
            data = getattr(t, "data", None) or {}
            field, text, lang = data.get("field"), data.get("text"), data.get("lang")
            pred = self._TRANSLATED_FIELD_PREDICATE.get(field or "")
            if pred is None or not text or not lang:
                continue
            if pred == CRM.P90_has_value and getattr(node, "node_type", None) != "property":
                continue
            if is_stale(g, t):
                self.stats["translations_stale"] = self.stats.get(
                    "translations_stale", 0) + 1
                continue
            ctx.add((node_iri, pred, Literal(text, lang=lang)))
            self.stats["literals_translation"] = self.stats.get(
                "literals_translation", 0) + 1

    def _serialize_translation(self, g: S3DGraph, node: Any,
                               node_iri: URIRef, ctx) -> None:
        """A TranslationNode as its own resource (crm:E33): the text with its
        tag (crm:P190_has_symbolic_content) and its language (crm:P72), what it
        translates (prov:wasDerivedFrom → the node; has_translation leaves as
        crm:P73 from the other side), and the four facts CIDOC has no term for
        — which field, from which language, how, of which text (em:)."""
        data = getattr(node, "data", None) or {}
        lang = data.get("lang")
        text = data.get("text")
        if text:
            ctx.add((node_iri, CRM.P190_has_symbolic_content,
                     Literal(text, lang=lang) if lang else Literal(text)))
        if lang:
            ctx.add((node_iri, CRM.P72_has_language, Literal(lang)))
        for key, pred in (("from_lang", EM.sourceLanguage),
                          ("field", EM.translatedField),
                          ("method", EM.translationMethod),
                          ("source_digest", EM.sourceDigest)):
            if data.get(key):
                ctx.add((node_iri, pred, Literal(str(data[key]))))
        if data.get("review_requested"):
            ctx.add((node_iri, EM.reviewRequested,
                     Literal(True, datatype=XSD.boolean)))
        for e in g.edges:
            if e.edge_type == "has_translation" and e.edge_target == node.node_id:
                ctx.add((node_iri, PROV.wasDerivedFrom,
                         self._node_iri(g.graph_id, e.edge_source)))
        self.stats["translations"] = self.stats.get("translations", 0) + 1

    def summary(self) -> str:
        """One line of what the export did, for the caller's report: what went
        out, and what the language of the texts was. ``definitions_label_only``
        and the literal counts are the ones a reader should look at before
        trusting a projection as complete."""
        s = self.stats
        return (f"{s['graphs']} graphs, {s['nodes']} nodes, "
                f"{s['edges_emitted']} edges emitted, "
                f"{s['edges_skipped_deprecated']} deprecated skipped, "
                f"{s['nodes_unmapped']} nodes unmapped, "
                f"{s['edges_unmapped']} edges unmapped, "
                f"{s['definitions_label_only']} definitions label-only; "
                f"texts tagged {s['literals_tagged_node']} by the node, "
                f"{s['literals_tagged_study']} by the study, "
                f"{s['literals_untagged']} untagged (language never declared)"
                + (f"; {s['translations']} translations "
                   f"({s.get('literals_translation', 0)} literals beside their "
                   f"original, {s.get('translations_stale', 0)} to realign)"
                   if s.get("translations") else ""))

    def _serialize_definition(self, node: Any, node_iri: URIRef, ctx) -> None:
        """Project the DEFINITION of a unit (datamodel 1.6.9). THE one place.

        What is emitted is not decided here but read from the datamodel entry
        ``StratigraphicNode.properties.definition.rdf``, so changing the
        projection is one line of JSON:

        * the value carries a concept URI →
          ``<unit> <rdf.with_concept> <concept>`` (default ``crm:P2_has_type``)
          and ``<concept> rdf:type <rdf.concept_class>`` (``crm:E55_Type``).
          The label is NOT written on the concept: the concept belongs to its
          vocabulary, which already labels it, and the label resolves at reading.
        * the value carries only a label → ``rdf.label_only`` decides: ``null``
          (default) = no triple, because a word is not a concept and an IRI
          minted for it would claim a vocabulary entry that does not exist; a
          property name (e.g. ``crm:P3_has_note``) = that property with the
          label as a literal. Either way the case is counted in
          ``stats["definitions_label_only"]``.
        * no definition, or a node type that does not declare one → nothing.
        """
        rule = self.datamodel.get_node_element_rule(node, "definition")
        if not rule:
            return
        data = getattr(node, "data", None)
        value = data.get("definition") if isinstance(data, dict) else None
        if value is None:
            value = getattr(node, "definition", None)
        from ..nodes.stratigraphic_node import definition_parts
        concept, label = definition_parts(value)
        rdf = rule.get("rdf") or {}
        if concept:
            predicate = _resolve_prefixed(rdf.get("with_concept"))
            if predicate is None:
                return
            concept_iri = URIRef(concept)
            ctx.add((node_iri, predicate, concept_iri))
            concept_class = _resolve_prefixed(rdf.get("concept_class"))
            if concept_class is not None:
                ctx.add((concept_iri, RDF.type, concept_class))
        elif label:
            self.stats["definitions_label_only"] += 1
            predicate = _resolve_prefixed(rdf.get("label_only"))
            if predicate is not None:
                ctx.add((node_iri, predicate, Literal(label)))

    def _serialize_authority_refs(self, node: Any, node_iri: URIRef, ctx) -> None:
        """Emit `data.authority_refs` as SKOS/OWL alignment triples.

        Each ref ``{uri, authority, label, rank, match}`` becomes
        ``<node> <predicate(match)> <uri>`` where the predicate is chosen by
        match strength (default skos:closeMatch). Non-http URIs are skipped
        (an authority ref must be a resolvable IRI)."""
        data = getattr(node, "data", {}) or {}
        refs = data.get("authority_refs")
        if not isinstance(refs, list):
            return
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            uri = ref.get("uri")
            if not uri or not (isinstance(uri, str)
                               and uri.startswith(("http://", "https://"))):
                continue
            pred = AUTHORITY_MATCH_PREDICATE.get(
                ref.get("match"), DEFAULT_AUTHORITY_PREDICATE)
            ctx.add((node_iri, pred, URIRef(uri)))
            self.stats["authority_refs"] = self.stats.get("authority_refs", 0) + 1

    def _serialize_ai(self, g: S3DGraph, node: Any, node_iri: URIRef, ctx) -> None:
        """Emit ``data.ai_assisted`` and the verification of a node.

        ``em:aiAssistedBy`` → the AuthorAINode, ``em:aiModel``,
        ``em:aiPromptRef`` → the prompt node, one ``em:aiAssistedField`` per
        touched field; ``em:validatedBy`` → the person who verified it and
        ``em:validatedAt``. Only for a node that carries the marker — an
        unverified one reaches here in every round trip, and in a publication
        only when it was forced.
        """
        from ..ai_validation import (VALIDATED_AT, VALIDATED_BY, ai_marker,
                                     touched_fields)
        marker = ai_marker(node)
        if marker is None:
            return
        data = getattr(node, "data", {}) or {}
        if marker.get("by"):
            ctx.add((node_iri, EM.aiAssistedBy,
                     self._node_iri(g.graph_id, marker["by"])))
        if marker.get("model"):
            ctx.add((node_iri, EM.aiModel, Literal(str(marker["model"]))))
        if marker.get("prompt_ref"):
            ctx.add((node_iri, EM.aiPromptRef,
                     self._node_iri(g.graph_id, marker["prompt_ref"])))
        for f in touched_fields(node) or []:
            ctx.add((node_iri, EM.aiAssistedField, Literal(f)))
        if not (marker.get("by") or marker.get("model")
                or marker.get("prompt_ref") or touched_fields(node)):
            # the fact without its detail still has to be stated
            ctx.add((node_iri, EM.aiAssistedField, Literal("*")))
        if data.get(VALIDATED_BY):
            ctx.add((node_iri, EM.validatedBy,
                     self._node_iri(g.graph_id, data[VALIDATED_BY])))
            ctx.add((node_iri, PROV.wasInfluencedBy,
                     self._node_iri(g.graph_id, data[VALIDATED_BY])))
        if data.get(VALIDATED_AT):
            ctx.add((node_iri, EM.validatedAt,
                     Literal(str(data[VALIDATED_AT]), datatype=XSD.dateTime)))

    def _serialize_editorial(self, node: Any, node_iri: URIRef, ctx) -> None:
        """Emit the last-hand stamps (AUDIT1) as PROV-O.

        ``created_by`` → ``em:createdBy`` AND the plain ``prov:wasAttributedTo``;
        ``modified_by`` → ``em:lastEditedBy`` (a subproperty of the same);
        ``created_at`` → ``prov:generatedAtTime``;
        ``modified_at`` → ``em:modifiedAt`` and ``dcterms:modified``.

        The pairs are deliberate. The em: predicates are what the round-trip
        reads, because ``prov:wasAttributedTo`` alone cannot say WHICH hand it
        was; the PROV/DC ones are what a reader who never heard of EM gets for
        free. Nothing is emitted for a field the node does not carry: these
        stamps are automatic, and an automatic "unknown" written into a store is
        an invented record.

        The agent is the ORCID iD as an IRI — an ORCID iD IS a URL, so there is
        no minting to do. A ``*_by`` that is not a well-formed iD is written as a
        literal instead of being dropped: it is still the only trace of who was
        editing.
        """
        data = getattr(node, "data", {}) or {}
        if not isinstance(data, dict):
            return
        from ..editorial import normalize_orcid

        def agent(value: Any):
            orcid = normalize_orcid(value)
            return URIRef(f"https://orcid.org/{orcid}") if orcid else Literal(str(value))

        created_by = data.get("created_by")
        if created_by:
            who = agent(created_by)
            ctx.add((node_iri, EM.createdBy, who))
            ctx.add((node_iri, PROV.wasAttributedTo, who))
        modified_by = data.get("modified_by")
        if modified_by:
            ctx.add((node_iri, EM.lastEditedBy, agent(modified_by)))
        created_at = data.get("created_at")
        if created_at:
            ctx.add((node_iri, PROV.generatedAtTime,
                     Literal(str(created_at), datatype=XSD.dateTime)))
        modified_at = data.get("modified_at")
        if modified_at:
            stamp = Literal(str(modified_at), datatype=XSD.dateTime)
            ctx.add((node_iri, EM.modifiedAt, stamp))
            ctx.add((node_iri, DCTERMS.modified, stamp))
        # P4.1 · the TOMBSTONE. A deletion is a fact somebody stated, with a hand
        # and an instant, and a projection that dropped it would publish a graph
        # in which the deletion never happened — which is how a deleted node
        # comes back from a triplestore. Emitted only when the node carries one.
        removed = data.get("removed")
        if isinstance(removed, dict) and removed.get("ts"):
            ctx.add((node_iri, EM.removedAt,
                     Literal(str(removed["ts"]), datatype=XSD.dateTime)))
            if removed.get("by"):
                ctx.add((node_iri, EM.removedBy, agent(removed["by"])))

    @staticmethod
    def _dtc_kind_mapping(node: Any, node_type: Optional[str]
                          ) -> Optional[Tuple[URIRef, List[URIRef]]]:
        """``(class, superclasses)`` an ACQUISITION takes from its kind, or
        ``None`` for the class mapping (em_visual_rules 1.6.24,
        ``dtc_kinds.acquisition.<kind>.mapping``). A capture is not a transfer:
        a photograph or a scan is a crmdig:D2 Digitization Process, a survey a
        crmdig:D11 Digital Measurement Event, a drawing or a sheet made by hand
        a crm:E65 Creation. A retrieval declares nothing and stays the D12 of
        DTCAcquisitionNode."""
        if node_type != "dtc_acquisition":
            return None
        from ..utils.utils import get_dtc_kind_mapping
        kind = (getattr(node, "data", None) or {}).get("dtc_kind")
        mapping = get_dtc_kind_mapping(kind) if isinstance(kind, str) else None
        primary = _resolve_prefixed(mapping.get("cidoc")) if mapping else None
        if primary is None:
            return None
        supers = [iri for iri in (_resolve_prefixed(sc)
                                  for sc in mapping.get("subclass_of") or [])
                  if iri is not None]
        return primary, supers

    def _compute_primary_iri(self, node: Any, cls_name: str,
                             node_type: Optional[str]) -> Optional[URIRef]:
        """
        Resolve the rdf:type primary IRI for a node, applying conditional rules.

        Conditional rule for PropertyNode:
            The qualia-type-specific class (looked up in em_qualia_types.json)
            takes precedence over the generic PropertyNode default class
            (typically crm:E54_Dimension). Without this, an aesthetic_value
            property would be typed as BOTH crm:E54_Dimension (PropertyNode
            default) and crminf:I4_Proposition_Set (qualia-specific), which is
            semantically misleading: aesthetic value is NOT a dimension.

        Lookup key resolution (PropertyNode):
            The s3dgraphy graphml importer preserves raw graphml data
            (``node.name`` carries the NodeLabel, ``node.property_type`` is
            the default "string" unless populated by the
            ``_s3d_property_metadata`` side channel). To enrich at export
            time without burdening the importer with vocabulary knowledge,
            we try the lookup key in this order:
              1. ``node.property_type`` if explicitly set (not "string")
              2. ``node.name`` if available (the yEd NodeLabel — qualia
                 identifier in EM convention)
            Either string is resolved through the multi-step graceful
            matcher in ``_Datamodel.get_qualia_crm_iri`` (exact / dot-split
            / lowercase). Falls back to the generic node datamodel mapping
            when no qualia term matches (e.g. custom labels like
            "lenght_pipe" stay as em:Qualia + crm:E1_CRM_Entity).
        """
        if node_type == "property":
            ptype = getattr(node, "property_type", None)
            # Treat the default "string" sentinel as "unset" — the importer
            # leaves it on the PropertyNode constructor default when no
            # side-channel metadata is present.
            if ptype and ptype.lower() != "string":
                qualia_iri = self.datamodel.get_qualia_crm_iri(ptype)
                if qualia_iri is not None:
                    return qualia_iri
            # Fall back to NodeLabel (em yEd convention: label IS the qualia id)
            name = getattr(node, "name", None)
            if name:
                qualia_iri = self.datamodel.get_qualia_crm_iri(name)
                if qualia_iri is not None:
                    return qualia_iri
        return self.datamodel.get_node_primary_iri(cls_name)

    def _serialize_type_specific(self, node: Any, node_type: Optional[str],
                                 node_iri: URIRef, ctx,
                                 graph_id: Optional[str] = None) -> None:
        data = getattr(node, "data", {}) or {}

        if node_type == "narrative":
            # EM Narrative (DP-79) — the PROJECTION side of the two-tier model.
            # Authoring happens on the property graph; here we only restate what
            # it already says, in RDF terms.
            #
            # The chapters are NOT projected as a structure: their order and
            # nesting are an authoring concern, and reifying every block as a
            # resource would put a document tree into a knowledge graph for no
            # query anyone wants to run. What IS projected is the thing worth
            # asking about — WHICH resources this narrative cites — as
            # P67_refers_to, the same reference hinge used everywhere else in
            # EM. That makes "which narratives cite this US" a one-line SPARQL
            # query instead of a text search.
            lang = data.get("lang")
            if lang:
                ctx.add((node_iri, CRM.P72_has_language, Literal(lang)))
            for key, prop in (("version", CRM.P3_has_note),):
                value = data.get(key)
                if value:
                    ctx.add((node_iri, prop, Literal(f"{key}: {value}")))
            # Authorship and endorsement (N4). Both are projected because both
            # are claims ABOUT the text that a reader is entitled to check:
            # who wrote it, and whether a person has vouched for it. The
            # per-block state is not reified — a block is not a resource — but
            # the agents are, so "which narratives has this person endorsed"
            # and "what did this model write" are answerable.
            for author_id in (node.author_refs()
                              if hasattr(node, "author_refs")
                              else _narrative_authors_from_data(data)):
                if graph_id is None:
                    break
                ctx.add((node_iri, PROV.wasAttributedTo,
                         self._node_iri(graph_id, author_id)))
            for validator_id in (_narrative_validators(node, data)):
                if graph_id is None:
                    break
                ctx.add((node_iri, PROV.wasInfluencedBy,
                         self._node_iri(graph_id, validator_id)))
                self.stats["narrative_endorsements"] = self.stats.get(
                    "narrative_endorsements", 0) + 1
            # An unendorsed AI draft says so, in the graph as on the page: the
            # absence of a validator is the state, and stating it means a
            # consumer cannot mistake a draft for something someone stands
            # behind.
            pending = (len(node.pending_validation())
                       if hasattr(node, "pending_validation")
                       else 0)
            if pending:
                ctx.add((node_iri, EM.pendingValidation, Literal(pending)))

            refs = node.referenced_ids() if hasattr(node, "referenced_ids") \
                else _narrative_refs_from_data(data)
            for ref in refs:
                if graph_id is None:
                    break
                ctx.add((node_iri, CRM.P67_refers_to,
                         self._node_iri(graph_id, ref)))
                self.stats["narrative_references"] = self.stats.get(
                    "narrative_references", 0) + 1
            return

        if node_type == "property":
            # rdf:type already emitted by _compute_primary_iri (qualia-specific
            # class takes precedence over PropertyNode default).
            #
            # Value resolution: prefer node.value when set & non-empty;
            # fall back to node.description for legacy graphml where the
            # description data field encodes the value (yEd has no separate
            # "value" socket on annotation-style PropertyNodes).
            raw_value = getattr(node, "value", None)
            if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
                raw_value = getattr(node, "description", None)
            if raw_value is not None and (not isinstance(raw_value, str) or raw_value.strip()):
                # prose qualia (narrative_content) carry their language; a code
                # (inventory_number) or a number never does
                ctx.add((node_iri, CRM.P90_has_value,
                         self._text_literal(node, "value", raw_value)
                         if isinstance(raw_value, str) else Literal(raw_value)))

            # Qualia type identifier — same key resolution as _compute_primary_iri:
            # property_type if non-default, otherwise the NodeLabel (name).
            ptype = getattr(node, "property_type", None)
            if not ptype or ptype.lower() == "string":
                ptype = getattr(node, "name", None)
            if ptype:
                ctx.add((node_iri, EM.hasQualiaType, Literal(ptype)))

        # BUGFIX (2026-08-11, found by the RDF round-trip): the branch tested for
        # "epoch", but EpochNode.node_type is "EpochNode" — so it NEVER fired and
        # no epoch ever carried its bounds or its colour into RDF. A projection of
        # an EM graph without its chronology is missing the thing EM is about, and
        # nothing downstream could have restored it. Both spellings are accepted
        # now; the fix only ADDS triples.
        elif node_type in ("EpochNode", "epoch"):
            start = getattr(node, "start_time", None)
            end = getattr(node, "end_time", None)
            color = getattr(node, "color", None)
            if start is not None:
                ctx.add((node_iri, CRM["P82a_begin_of_the_begin"], Literal(start)))
            if end is not None:
                ctx.add((node_iri, CRM["P82b_end_of_the_end"], Literal(end)))
            if color:
                ctx.add((node_iri, CRM.P90_has_value, Literal(color)))

        elif node_type == "author":
            orcid = data.get("orcid")
            if orcid and orcid != "noorcid":
                ctx.add((node_iri, CRM.P48_has_preferred_identifier, Literal(orcid)))
                self._emit_orcid_verification(node_iri, data, ctx)
            surname = data.get("surname")
            if surname and surname != "nosurname":
                # P1_is_identified_by, not P131: P131 was deprecated in CRM 7.x
                # along with E82 Actor Appellation and is not declared in 7.1.3,
                # so the triple went out on a dead IRI (repaired 2026-09-21).
                ctx.add((node_iri, CRM.P1_is_identified_by, Literal(surname)))

        elif node_type == "author_ai":
            orcid = data.get("orcid")
            if orcid and orcid != "noorcid":
                ctx.add((node_iri, CRM.P48_has_preferred_identifier, Literal(orcid)))
                self._emit_orcid_verification(node_iri, data, ctx)
            model = data.get("model")
            if model:
                ctx.add((node_iri, EM.modelIdentifier, Literal(model)))
            prompt = data.get("prompt_reference")
            if prompt:
                ctx.add((node_iri, EM.promptReference, Literal(prompt)))

        elif node_type == "license":
            ltype = data.get("license_type")
            if ltype:
                ctx.add((node_iri, CRM.P2_has_type, Literal(ltype)))
            url = data.get("url")
            if url:
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    ctx.add((node_iri, RDFS.seeAlso, URIRef(url)))
                else:
                    ctx.add((node_iri, RDFS.seeAlso, Literal(url)))

        elif node_type == "embargo":
            start = data.get("embargo_start")
            end = data.get("embargo_end")
            if start:
                ctx.add((node_iri, CRM["P82a_begin_of_the_begin"], Literal(start)))
            if end:
                ctx.add((node_iri, CRM["P82b_end_of_the_end"], Literal(end)))
            reason = data.get("reason")
            if reason:
                ctx.add((node_iri, RDFS.comment, Literal(reason)))

        elif node_type == "resource":
            url = data.get("url")
            url_type = data.get("url_type")
            if url:
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    ctx.add((node_iri, RDFS.seeAlso, URIRef(url)))
                else:
                    ctx.add((node_iri, RDFS.seeAlso, Literal(url)))
            if url_type:
                ctx.add((node_iri, CRM.P2_has_type, Literal(url_type)))
            # DTC OUTPUT (slice b): a ResourceNode that is a DTC output — carries
            # data.dtc_kind — is the produced digital object (Resource). Beyond
            # its E73/url it is a crmdig:D1_Digital_Object / prov:Entity (the
            # process prov:generated it via dtc_had_output) and its kind projects
            # as crm:P2_has_type. RM/Document referencing it keep their own types.
            dtc_kind = data.get("dtc_kind")
            if dtc_kind:
                ctx.add((node_iri, RDF.type, CRMDIG.D1_Digital_Object))
                ctx.add((node_iri, RDF.type, PROV.Entity))
                ctx.add((node_iri, CRM.P2_has_type, Literal(dtc_kind)))
            # SHELF1 · integrity and the three fences. Emitted only when
            # RECORDED — absent means nobody said, and a default written into a
            # store becomes an assertion that travels. (The sane reading lives
            # in `ResourceNode.effective_scope`, on the consumer's side.)
            checksum = data.get("checksum")
            if checksum:
                ctx.add((node_iri, EM.checksum, Literal(str(checksum))))
            scope = data.get("scope")
            if scope:
                ctx.add((node_iri, EM.resourceScope, Literal(str(scope))))
            residency = data.get("residency")
            if residency:
                ctx.add((node_iri, EM.residency, Literal(str(residency))))

        elif node_type == "resource_file":
            # ONE FILE of a resource (E.D. 2026-09-30): where its bytes are and
            # their digest, with the same two properties the resource uses. The
            # role and the relative path are on the has_file EDGE, not here.
            url = data.get("url")
            if url:
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    ctx.add((node_iri, RDFS.seeAlso, URIRef(url)))
                else:
                    ctx.add((node_iri, RDFS.seeAlso, Literal(url)))
            checksum = data.get("checksum")
            if checksum:
                ctx.add((node_iri, EM.checksum, Literal(str(checksum))))

        elif node_type == "LocationNodeGroup":
            # The kind (toponym / study / functional) is the discriminator of the
            # spatial plane and is REQUIRED by the constructor — a Location
            # without it cannot be rebuilt. It was not projected at all, so a
            # Location came back as a bare Node. The datamodel already declared
            # how ("E53 Place + E55 Type (kind classifier via P2_has_type)"); this
            # emits what that mapping says.
            kind = getattr(node, "kind", None) or data.get("kind")
            if kind:
                ctx.add((node_iri, CRM.P2_has_type, Literal(kind)))
            # propagation is real data too (additive vs substitutive changes what
            # the membership MEANS), and only stated when it is not the default —
            # a triple per node saying "the usual" is noise.
            propagation = getattr(node, "propagation", None) or data.get("propagation")
            if propagation and propagation != "additive":
                ctx.add((node_iri, EM.propagation, Literal(propagation)))

        elif node_type == "geo_position":
            epsg = data.get("epsg")
            if epsg:
                ctx.add((node_iri, CRM.P2_has_type, Literal(f"EPSG:{epsg}")))
            # The shift is the anchor of the scene-local frame, and `rotation`
            # (G1) is its azimuth — clockwise degrees from north, 0 = north up.
            # Projecting the shift without the rotation would describe an
            # orientation the scene does not have, so it travels with it.
            for axis in ("shift_x", "shift_y", "shift_z", "rotation"):
                v = data.get(axis)
                if v is not None:
                    ctx.add((node_iri, EM[axis], Literal(v)))

        elif node_type == "semantic_shape":
            # PROXY-AS-PROPERTY (v1.6.3): the SemanticShape is the PAYLOAD of a
            # geometry property, so the numbers are the whole point of the node
            # and the projection dropped them — a proxy came back from the store
            # as an empty shape with a label. Now they travel.
            #
            # One literal per hull and per sphere rather than one blob: they are
            # separate objects, and a consumer reading "the third hull" should
            # not have to parse a container to get at it. Coordinates are
            # space-separated with fixed precision, for the same reason the 2D
            # selector has fixed precision — this string is what the round-trip
            # compares.
            for part in (getattr(node, "convexshapes", None) or []):
                ctx.add((node_iri, EM.convexShape,
                         Literal(" ".join(f"{float(v):.6f}" for v in part))))
            for sphere in (getattr(node, "spheres", None) or []):
                ctx.add((node_iri, EM.sphere,
                         Literal(" ".join(f"{float(v):.6f}" for v in sphere))))
            shape_type = getattr(node, "type", None)
            if shape_type:
                ctx.add((node_iri, CRM.P2_has_type, Literal(shape_type)))
            # The .glb of a proxy is a proxy_model RESOURCE (connections
            # 1.6.28): it leaves with that ResourceNode (rdfs:seeAlso + P2) and
            # the shape's has_linked_resource edge (crm:P67_refers_to), like an
            # RM's bytes. A LEGACY url still on an in-memory shape (a graph not
            # opened from an em.json, so never migrated) is kept as it always
            # was, with the ResourceNode's own predicate.
            url = getattr(node, "url", None) or (data.get("url") if data else None)
            if url:
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    ctx.add((node_iri, RDFS.seeAlso, URIRef(url)))
                else:
                    ctx.add((node_iri, RDFS.seeAlso, Literal(url)))

        elif node_type == "annotation_region":
            # The geometry travels as ONE selector literal (Media Fragment for a
            # rect, SVG-style point list for a polygon), not as a bag of numbers:
            # a consumer outside EM can resolve `xywh=percent:…` against the
            # image without knowing anything about this datamodel, and the string
            # is derived from the node's own fields rather than stored twice.
            #
            # Since 2026-10-06 the node is the place of ANY reading
            # (geometry_kind). A passage has a selector too (RFC 5147
            # `char=s,e`); the 3D kinds have none — their vertices leave as a
            # GeoSPARQL WKT literal (below) — so an empty selector is emitted
            # as nothing. The kind itself travels as the
            # P2_has_type a region2d uses for its shape_kind: one type per node.
            selector = getattr(node, "selector", None)
            sel = selector() if callable(selector) else ""
            if sel:
                ctx.add((node_iri, EM.hasSelector, Literal(sel)))
            geometry_kind = getattr(node, "geometry_kind", None) or "region2d"
            shape_kind = getattr(node, "shape_kind", None)
            if geometry_kind != "region2d":
                ctx.add((node_iri, CRM.P2_has_type, Literal(geometry_kind)))
            elif shape_kind:
                ctx.add((node_iri, CRM.P2_has_type, Literal(shape_kind)))
            if geometry_kind == "passage":
                self._emit_passage_quote(node_iri, node, ctx)
            if geometry_kind in ("point", "line", "polyline"):
                # node datamodel 1.6.15: the vertices are the node's, and leave
                # as ONE GeoSPARQL literal (the 3D twin of the 2D Media
                # Fragment): <region> geo:hasGeometry <region/geometry>, which
                # geo:asWKT "<CRS IRI> POINT Z / LINESTRING Z (…)". Above the
                # threshold there are no coords: the .glb resource leaves with
                # its has_linked_resource (P67), and the count says what is in it.
                coords = getattr(node, "coords", None) or data.get("coords")
                if coords:
                    from ..geometry.wkt import coords_to_wkt
                    geom = URIRef(str(node_iri) + "/geometry")
                    ctx.add((node_iri, GEO.hasGeometry, geom))
                    ctx.add((geom, RDF.type, GEO.Geometry))
                    ctx.add((geom, GEO.asWKT, Literal(
                        coords_to_wkt(geometry_kind, coords, getattr(node, "crs", None)),
                        datatype=GEO.wktLiteral)))
                vc = getattr(node, "vertex_count", None)
                if vc is not None:
                    ctx.add((node_iri, EM.vertexCount,
                             Literal(int(vc), datatype=XSD.nonNegativeInteger)))
                if getattr(node, "length", None) is not None:
                    self._emit_measure(node_iri, node, ctx)
            # Page 0 is emitted as NOTHING. A plain image has no page, and
            # asserting `onPage 0` for every region would put a fact in the store
            # that nobody stated — and the importer defaults to 0 anyway, so the
            # round-trip is exact either way.
            page = getattr(node, "page", 0)
            if page:
                ctx.add((node_iri, EM.onPage,
                         Literal(int(page), datatype=XSD.nonNegativeInteger)))

        elif node_type == "extractor":
            source = getattr(node, "source", None)
            if source:
                ctx.add((node_iri, CRMINF.J7_is_based_on_evidence_from, Literal(source)))
            self._emit_belief_skeleton(node_iri, ctx)

        elif node_type == "combiner":
            self._emit_belief_skeleton(node_iri, ctx)

        # Same family of gap: DTCAcquisitionNode (crmdig:D12 ⊂ D7) carries the
        # same `dtc_kind` fact and had no branch, so an acquisition's kind was
        # dropped while a process's was kept.
        elif node_type in ("dtc_process", "dtc_acquisition"):
            # DTC substrate profile (ECHOES): the process kind (e.g.
            # transformation) projects as crm:P2_has_type. The rdf:type
            # (crmdig:D7 + prov:Activity) is emitted from em_extension by the
            # generic pass. INPUT and OUTPUT kinds are handled in the `link`
            # branch (both are Resources/LinkNodes).
            kind = data.get("dtc_kind")
            if kind:
                ctx.add((node_iri, CRM.P2_has_type, Literal(kind)))

    def _emit_passage_quote(self, node_iri: URIRef, node: Any, ctx) -> None:
        """The quoted words of a passage, as a W3C TextQuoteSelector.

        The offsets already travel as the RFC 5147 `char=s,e` of
        em:hasSelector — the text twin of the Media Fragment a region uses, one
        string like every other selector. The QUOTE has no such string form:
        the only standard term for it is Web Annotation's, so it is reused
        rather than minted (`em:quote` would say the same thing to nobody).
        It is not a second copy of the geometry: the offsets say where, the
        quote is what survives an edit that moves them.

        The selector is a derived IRI (`<region>/quote`), not a blank node, so
        the projection stays addressable and the importer's node pass — which
        reads only subjects carrying dcterms:identifier — never mistakes it for
        a node. An empty quote is emitted as nothing: the node never invents one.
        """
        text = getattr(node, "text", None)
        if not text:
            return
        quote = URIRef(str(node_iri) + "/quote")
        ctx.add((node_iri, OA.hasSelector, quote))
        ctx.add((quote, RDF.type, OA.TextQuoteSelector))
        ctx.add((quote, OA.exact, Literal(text)))

    def _emit_measure(self, node_iri: URIRef, node: Any, ctx) -> None:
        """The length of a line or polyline as a CIDOC E54 Dimension.

        CIDOC already has the whole shape — P43 has dimension → E54, P90 has
        value, P91 has unit → E58 — and uses it for exactly this: a measured
        extent of a thing. An em: literal would hide a number every CRM reader
        knows how to find. The region is an E36 (⊂ E70 Thing), so P43 is legal
        on it as it stands.

        The unit is a QUDT unit IRI (E58 is a class; a literal would break the
        range of P91). The frame the length was measured in (`crs`, "local"
        for the scene frame) has no CIDOC property on a dimension, so it is
        em:crs. The dimension is `<region>/length`, typed "length" with P2.
        """
        dim = URIRef(str(node_iri) + "/length")
        ctx.add((node_iri, CRM.P43_has_dimension, dim))
        ctx.add((dim, RDF.type, CRM.E54_Dimension))
        ctx.add((dim, CRM.P2_has_type, Literal("length")))
        ctx.add((dim, CRM.P90_has_value,
                 Literal(float(node.length), datatype=XSD.double)))
        unit = getattr(node, "unit", None)
        if unit:
            unit_iri = MEASURE_UNIT_IRI.get(unit) or S3D[f"unit_{_iri_local(unit)}"]
            ctx.add((dim, CRM.P91_has_unit, unit_iri))
        crs = getattr(node, "crs", None)
        if crs:
            ctx.add((dim, EM.crs, Literal(str(crs))))

    def _emit_orcid_verification(self, node_iri: URIRef, data: Dict[str, Any],
                                 ctx) -> None:
        """Say whether the declared ORCID iD was CONFIRMED, and only then.

        Emitted **only for a verified author**, and that asymmetry is the point.
        "Verified" is a positive fact somebody established; "not verified" is the
        absence of one, and absence is what an empty graph already says. Writing
        `verified false` into a store would turn "nobody has checked yet" into an
        assertion that travels — and a reader downstream cannot tell a claim of
        falsity from a silence.

        The predicate is `em:orcidVerified`. A CIDOC-native alternative would be
        an E13 Attribute Assignment reifying the check (who verified, when,
        against which authority), which is the *right* shape once the flow
        records those facts — it does not yet, and reifying an event with no
        actor and no date would be inventing provenance. Flagged
        `confirm_with: Felicetti` in em.ttl.
        """
        if data.get("verified") is True:
            ctx.add((node_iri, EM.orcidVerified,
                     Literal(True, datatype=XSD.boolean)))

    def _emit_belief_skeleton(self, node_iri: URIRef, ctx) -> None:
        """CRMinf belief expansion (I2) for argumentation nodes.

        EM deliberately collapses the CRMinf belief layer: the conclusion of
        an Extractor (I7 Belief Adoption) or Combiner (I5 Inference Making)
        is implicit in the existence of the node it justifies. To make the
        chain CRMinf-complete on export WITHOUT asking users to author
        beliefs explicitly, each argumentation node deterministically emits
        its concluded belief:

            <node> J2_concluded_that <node>/belief .
            <node>/belief a I2_Belief .

        J2 has domain I1_Argumentation — valid for both I5 and I7.

        J4_that and J5_holds_to_be are emitted by the graph-level post-pass
        ``_emit_belief_propositions`` (design approved E.D. 2026-07-11):
        property claims get a minted I17 One-Proposition_Set, reconstruction
        claims link J4 directly to the virtual unit (⊂ I4), confidence_level
        qualia are linked via J5 as I6 Belief Values.
        """
        belief_iri = URIRef(str(node_iri) + "/belief")
        ctx.add((node_iri, CRMINF.J2_concluded_that, belief_iri))
        ctx.add((belief_iri, RDF.type, CRMINF.I2_Belief))

    # ── edge serialization ──────────────────────────────────────────────────

    def _logical_target_class(self, g: S3DGraph, edge: Any, inverted: bool) -> str:
        """Class name of the node the edge points AT once direction is resolved.

        The datamodel names node classes (`StratigraphicUnit`), not node_types:
        `Node.node_type_map` is keyed by node_type and `StratigraphicNode`
        happens to be the node_type of VirtualStratigraphicUnit, so the class
        name is the only discriminator that matches `allowed_connections` and
        `extension_when`. Returns "" when the node cannot be resolved, which
        fails the guard closed — an extension predicate is never emitted on a
        target we could not check.
        """
        node = g.find_node_by_id(edge.edge_source if inverted else edge.edge_target)
        return type(node).__name__ if node is not None else ""

    @staticmethod
    def _logical_source_class(g: S3DGraph, edge: Any, inverted: bool) -> str:
        """Class name of the node the edge starts FROM once direction is
        resolved — the twin of :meth:`_logical_target_class`, failing closed
        the same way."""
        node = g.find_node_by_id(edge.edge_target if inverted else edge.edge_source)
        return type(node).__name__ if node is not None else ""

    def _condition_holds(self, g: S3DGraph, edge: Any, inverted: bool,
                         condition: Optional[Dict[str, List[str]]]) -> bool:
        """``{source_node_class, target_node_class}`` against the logical ends
        of the edge; no condition holds always."""
        if not condition:
            return True
        sources = condition.get("source_node_class")
        if sources and self._logical_source_class(g, edge, inverted) not in sources:
            return False
        targets = condition.get("target_node_class")
        if targets and self._logical_target_class(g, edge, inverted) not in targets:
            return False
        return True

    def _serialize_edge(self, g: S3DGraph, edge: Any, ctx) -> None:
        edge_type = edge.edge_type
        predicate, ext_iri, type_tag, deprecated = self.datamodel.get_edge_mapping(edge_type)

        if deprecated:
            self.stats["edges_skipped_deprecated"] += 1
            return

        # A reverse edge carries the same fact as its canonical, written the
        # other way round. RDF keeps no record of which way the author drew it,
        # so the canonical predicate goes out with subject and object swapped
        # and the graph reads uniformly. Written as-is, `is_before` would find
        # no entry in the datamodel and fall through to the generic
        # P130_shows_features_of below — which does not merely lose the
        # relation, it states a different one.
        edge_type, inverted = self.datamodel.resolve_edge_direction(edge_type)
        if inverted:
            self.stats["edges_canonicalised"] = self.stats.get("edges_canonicalised", 0) + 1

        source_iri = self._node_iri(g.graph_id, edge.edge_target if inverted else edge.edge_source)
        target_iri = self._node_iri(g.graph_id, edge.edge_source if inverted else edge.edge_target)

        if type_tag and type_tag in AP11_SUBPROPS:
            specific = AP11_SUBPROPS[type_tag]
            ctx.add((source_iri, specific, target_iri))
            # Also assert the generic AP11 (so SPARQL on AP11 still works
            # for readers that don't know our subproperties).
            ctx.add((source_iri, CRMARCHAEO.AP11_has_physical_relation_to, target_iri))
            self.stats["edges_emitted"] += 1
            return

        # has_visual_reference co-typing: the target is asserted to be an
        # E36 Visual Item — required for the P138i_has_representation mapping
        # to be range-consistent. Since BUGFIX-CONN2 (2026-08-05) the target
        # is the resource-layer image node (ResourceNode, E73 Information Object)
        # rather than the former E31 Document; E36 is a subclass of E73, so
        # co-typing a ResourceNode as E36 is now clean (it was strained for E31).
        # The co-typing is target-agnostic, so no logic change was needed —
        # only the semantics of what the target IS. See Appendix B.1 of the
        # WP3 coverage analysis and the CIDOC note for Felicetti (confirm E36
        # as the target class, as for USNt).
        if edge_type == "has_visual_reference":
            ctx.add((target_iri, RDF.type, CRM.E36_Visual_Item))

        # A DECLARED derivation whose input is a whole ACQUISITION (connections
        # v1.6.11): the property graph writes one edge type for "this came from
        # that" whether the input is a file or a campaign, but the RDF cannot.
        # crmdig:L10_had_input and prov:used both range over digital OBJECTS,
        # and an acquisition is an EVENT — emitting them here would state
        # something false about a class, which a reasoner then propagates.
        # Activity → activity is prov:wasInformedBy, and that is what goes out.
        if edge_type == "dtc_had_input":
            # the LOGICAL target, which is the drawn source when inverted
            target = g.find_node_by_id(edge.edge_source if inverted else edge.edge_target)
            if getattr(target, "node_type", "").startswith("dtc_"):
                ctx.add((source_iri, PROV.wasInformedBy, target_iri))
                self.stats["edges_emitted"] += 1
                return

        if predicate is not None:
            ctx.add((source_iri, predicate, target_iri))
            # Dual emission (generalised AP11 pattern): also assert the
            # specific em:/extension subproperty when one is declared and
            # resolvable, so expressive SPARQL works without inference
            # while CRM-only readers still see the core predicate.
            if ext_iri is not None and ext_iri != predicate:
                if self._condition_holds(g, edge, inverted,
                                         self.datamodel.get_extension_condition(edge_type)):
                    ctx.add((source_iri, ext_iri, target_iri))
                else:
                    self.stats["edges_extension_skipped_guard"] = (
                        self.stats.get("edges_extension_skipped_guard", 0) + 1)
            # The same edge read from the other side, where the datamodel
            # declares it (is_part_of → <VSF> em:reconstructsFrom <SF>).
            inverse = self.datamodel.get_inverse_extension(edge_type)
            if inverse is not None and self._condition_holds(g, edge, inverted, inverse[1]):
                ctx.add((target_iri, inverse[0], source_iri))
                self.stats["edges_inverse_extension"] = (
                    self.stats.get("edges_inverse_extension", 0) + 1)
            self.stats["edges_emitted"] += 1
        elif self.datamodel.edge_predicate_declared_absent(edge_type):
            # The datamodel states there is no predicate for this edge. Say
            # nothing: the fallback below would put P130_shows_features_of on
            # it, which is not a weaker claim than the wrong one it replaced —
            # it is another wrong one, and a live IRI carries it further than a
            # dead one ever did. The edge is simply not projected until the
            # predicate is decided.
            if ext_iri is not None:
                # ...unless the extension DOES have something true to say. A
                # declared-absent `cidoc` means no CRM-core predicate holds the
                # domain, not that the edge carries no meaning: is_in_activity
                # (CRMem, 2026-09-21) is exactly that case, and em:isInActivity
                # states it precisely. Emitting the extension alone is not a
                # weaker dual emission, it is the whole claim — a CRM-only
                # reader correctly sees nothing rather than something false.
                ctx.add((source_iri, ext_iri, target_iri))
                self.stats["edges_emitted_extension_only"] = (
                    self.stats.get("edges_emitted_extension_only", 0) + 1)
            else:
                self.stats["edges_skipped_unmappable"] = (
                    self.stats.get("edges_skipped_unmappable", 0) + 1)
        else:
            # Fallback: emit as generic P130_shows_features_of so the
            # connection survives the round-trip even if unmapped.
            ctx.add((source_iri, CRM.P130_shows_features_of, target_iri))
            self.stats["edges_unmapped"] += 1


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helpers
# ─────────────────────────────────────────────────────────────────────────────

def export_to_rdf(output_path: str,
                  format: str = "turtle",
                  graph_ids: Optional[List[str]] = None,
                  base_uri: str = DEFAULT_BASE_URI,
                  parent_hdt_iri: Optional[str] = None,
                  mode: str = "round_trip") -> str:
    """One-call helper: export all (or specified) graphs to RDF.

    If parent_hdt_iri is set, every exported EMGraph is bound to it via
    hdto:HP33i_is_proposition_set_of. `mode` is 'round_trip' (default, keeps
    tombstones) or 'publish' (drops them) — see :attr:`RDFExporter.MODES`.
    """
    exporter = RDFExporter(output_path, format=format, base_uri=base_uri,
                           parent_hdt_iri=parent_hdt_iri, mode=mode)
    return exporter.export_graphs(graph_ids)


def export_single_graph_to_rdf(graph: S3DGraph,
                               output_path: str,
                               format: str = "turtle",
                               base_uri: str = DEFAULT_BASE_URI,
                               parent_hdt_iri: Optional[str] = None,
                               mode: str = "round_trip",
                               include_unvalidated: bool = False) -> str:
    """One-call helper for an in-memory graph."""
    exporter = RDFExporter(output_path, format=format, base_uri=base_uri,
                           parent_hdt_iri=parent_hdt_iri, mode=mode,
                           include_unvalidated=include_unvalidated)
    return exporter.export_single_graph(graph)
