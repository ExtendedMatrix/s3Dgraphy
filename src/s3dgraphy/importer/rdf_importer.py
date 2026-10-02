"""
RDF importer for s3Dgraphy graphs — the return leg of the triplestore.

``RDFExporter`` projects a property graph into CIDOC-CRM + HDT-O + EM; this
module reads that projection back. Together they make the triplestore a place
you can go INTO and come OUT of, which is what the CHANGELOG means by calling
it a persistent source of truth: a store you can only write to is an archive,
not a source.

**Same single source of truth, read by the same code.** The three datamodels
(``s3Dgraphy_node_datamodel.json``, ``s3Dgraphy_connections_datamodel.json``,
``em_qualia_types.json``) are loaded through the exporter's own ``_Datamodel``
class, and every map here is the INVERSE of a map built there. Nothing about
the EM language is written twice: if a class, an edge or a qualia term changes
in the JSON, both directions change with it.

How the three inversions are resolved — the interesting part, because none of
them is a plain dictionary flip:

* **IRI → node class.** An exported node carries several ``rdf:type``: its own
  em: class plus the CRM superclasses the exporter emits for CRM-only readers.
  Reading, we take the **most specific** class — the one that is a Python
  subclass of every other candidate — and the redundant superclasses fall away
  on their own. No namespace heuristic, no ordering assumption.

  Since 2026-08-11 the map is **bijective**: the six classes that used to share
  E1/E78/E53 have distinct ``em_extension.uri``, so 50 classes give 50 distinct
  IRIs. The evidence-based tie-break that used to separate the E53 pair is
  retained for legacy TTL only (see ``CLASS_EVIDENCE``).

* **predicate → edge_type.** The core CRM predicates are heavily many-to-one
  (nine of them carry two or more EM edges; ``P138i_has_representation`` carries
  four). Three things disambiguate, in order: the em: subproperty for the AP11
  physical family, the ``extension_mapping`` predicate where the datamodel
  declares one, and — the general answer — the **declared endpoints**
  (``allowed_connections``) matched against the classes of the two nodes the
  triple actually joins. That last one is why this does not need a hand-written
  table: the datamodel already says which edge can join which classes.

* **CIDOC class → property_type.** This inverse is genuinely ambiguous (27
  qualia share ``E54_Dimension``, 29 share ``E55_Type``), so it is NOT used as
  the primary route. The exporter states the qualia id explicitly in
  ``em:hasQualiaType``, and that is what is read. The class inverse remains as a
  fallback for third-party RDF, and where it is ambiguous it records a warning
  instead of picking one.

Named graphs: each ``<base>/graph/<graph_id>`` subject typed ``em:EMGraph``
becomes one s3Dgraphy ``Graph``. The graph id is recovered from that IRI rather
than from the RDF context, because a Turtle document has no contexts — so the
same reader handles TTL and TriG without a second code path.

Author:  Emanuele Demetrescu
Version: 1.6.0 — initial RDF import pipeline
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:
    from rdflib import ConjunctiveGraph, Literal, URIRef
    from rdflib.namespace import DCTERMS, PROV, RDF, RDFS
except ImportError as _e:  # pragma: no cover
    raise ImportError(
        "RDFImporter requires rdflib. Install with: pip install rdflib"
    ) from _e

from ..graph import Graph as S3DGraph
from ..nodes.base_node import Node
from ..exporter.rdf_exporter import (
    AP11_SUBPROPS,
    CRM,
    CRMARCHAEO,
    CRMINF,
    DEFAULT_BASE_URI,
    EM,
    HDTO,
    MEASURE_UNIT_IRI,
    OA,
    S3D,
    _Datamodel,
)


# ─────────────────────────────────────────────────────────────────────────────
# Format detection
# ─────────────────────────────────────────────────────────────────────────────

#: file extension → rdflib parser name. Mirrors RDFExporter.SUPPORTED_FORMATS
#: from the other side: whatever the exporter can write, this can read.
EXT_FORMATS: Dict[str, str] = {
    "ttl": "turtle",
    "turtle": "turtle",
    "nt": "nt",
    "ntriples": "nt",
    "nq": "nquads",
    "nquads": "nquads",
    "trig": "trig",
    "jsonld": "json-ld",
    "json": "json-ld",
    "rdf": "xml",
    "xml": "xml",
    "owl": "xml",
}

#: The formats that carry named graphs. For the others the graph identity is
#: recovered from the EMGraph IRI (see the module docstring).
QUAD_FORMATS = {"trig", "nquads", "json-ld"}


def _format_for(source: Any, fmt: Optional[str]) -> str:
    """Resolve the rdflib parser name from an explicit `fmt` or the extension."""
    if fmt:
        key = str(fmt).strip().lower()
        return EXT_FORMATS.get(key, key)
    if isinstance(source, (str, Path)):
        text = str(source)
        # a path, not a serialised document: extensions only mean something here
        if "\n" not in text and len(text) < 4096:
            ext = Path(text).suffix.lstrip(".").lower()
            if ext in EXT_FORMATS:
                return EXT_FORMATS[ext]
    return "turtle"


def _resolve_prefixed_name(name: Optional[str]) -> Optional[URIRef]:
    """The exporter's own prefixed-name resolver, re-exported under a local name.

    Imported once here rather than inside the loops that use it: the same
    function on both sides means a CIDOC code spelled "E53 Place" resolves to the
    same IRI going out and coming back.
    """
    from ..exporter.rdf_exporter import _resolve_prefixed
    return _resolve_prefixed(name)


def _looks_like_path(source: Any) -> bool:
    """Is this a file path rather than a serialised document?

    Asked before touching the filesystem: ``Path(text).exists()`` on a 4 kB
    Turtle document raises ``OSError: File name too long``, so the cheap
    structural test comes first — a path has no newline and is short.
    """
    if isinstance(source, Path):
        return source.exists()
    if not isinstance(source, str):
        return False
    if "\n" in source or len(source) > 1024:
        return False
    try:
        return Path(source).exists()
    except OSError:  # pragma: no cover — defensive
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Exporter artefacts that are NOT graph content
# ─────────────────────────────────────────────────────────────────────────────

#: Predicates the exporter mints from node CONTENT rather than from an edge —
#: the CRMinf belief skeleton, the narrative authorship/endorsement projection.
#: Re-reading them as edges would invent connections the property graph never
#: had, so they are skipped by name, and the skip is declared rather than
#: discovered as a surprise later.
ARTEFACT_PREDICATES: Set[URIRef] = {
    CRMINF.J2_concluded_that,
    CRMINF.J4_that,
    CRMINF.J5_holds_to_be,
    CRMINF.J30_has_domain,
    CRMINF.J31_has_range,
    CRMINF.J32_has_property_type,
    CRMINF.J7_is_based_on_evidence_from,
    PROV.wasAttributedTo,
    PROV.wasInfluencedBy,
    HDTO.HP33i_is_proposition_set_of,
    # the declaration of an inherited property: read back onto the
    # has_property edge by _mark_inherited_properties, never an edge of its own
    EM.inheritsQualia,
    # the AI marker and the verification of a node: read back into its data
    # (_ai_data), never edges of their own
    EM.aiAssistedBy,
    EM.aiPromptRef,
    EM.validatedBy,
}

#: Predicates the exporter emits as the GENERIC companion of a more specific
#: one, so they can never identify an edge on their own.
#:
#: ``AP11_has_physical_relation_to`` is written beside every ``em:cuts`` /
#: ``em:abuts`` / … triple, for readers that do not know the subproperties. But
#: ``generic_connection`` declares AP11 as its own ``extension_mapping`` in the
#: datamodel, so without this a physical relation came back as BOTH its real
#: type and a spurious ``generic_connection`` — the AP11 companion read as if it
#: were a signature. Excluded here, ``generic_connection`` falls back to its core
#: ``P130_shows_features_of``, which belongs to it alone.
GENERIC_COMPANION_PREDICATES: Set[URIRef] = {
    CRMARCHAEO.AP11_has_physical_relation_to,
}

#: LEGACY FALLBACK ONLY (2026-08-11).
#:
#: Three CIDOC classes used to be shared by two s3Dgraphy classes each — E1 by
#: Node/UnknownNode, E78 by GroupNode/ParadataNodeGroup, E53 by
#: LocationNodeGroup/GeoPositionNode — because none of the six declared an
#: ``em_extension.uri``. The E53 pair was the hard one: unrelated in the class
#: hierarchy, so it could only be read by looking for a triple the exporter
#: writes for one and not the other. That inference is an INDIZIO, and it breaks
#: precisely where it matters — a graph georeferenced without a transform has no
#: ``em:shift_*`` to find, and its GeoPosition would come back as a Location.
#:
#: All six now have distinct URIs in the datamodel (and in ``em.ttl``), so
#: ``IRI → class`` is bijective and this never fires on RDF written by the
#: current exporter. It is kept for TTL produced BEFORE that change, where the
#: shift triples are still the only evidence there is. Measured: 50 classes,
#: 50 distinct primary IRIs, 0 collisions.
CLASS_EVIDENCE: Dict[str, Tuple[URIRef, ...]] = {
    "GeoPositionNode": (EM.shift_x, EM.shift_y, EM.shift_z, EM.rotation),
}

#: Node types whose ``P67_refers_to`` triples are a projection of their own
#: content (a narrative's citations live in ``data.chapters``, not in edges).
#: For any other source class P67 is a real edge, so the rule is narrow.
P67_CONTENT_SOURCES = {"narrative"}


# ─────────────────────────────────────────────────────────────────────────────
# The inverse of the three datamodels
# ─────────────────────────────────────────────────────────────────────────────

class _InverseDatamodel:
    """Every lookup the exporter does forwards, done backwards.

    Built from the exporter's own ``_Datamodel`` — the same reader over the same
    three JSON files — so the two directions cannot drift apart.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        self.dm = _Datamodel(config_dir=config_dir)

        #: class name → class object, for the specificity test and for
        #: ``allowed_connections`` matching. Taken from the live node registry
        #: (``Node.node_type_map``, populated by ``__init_subclass__``) plus the
        #: abstract bases those classes inherit from, which the datamodel names
        #: in ``allowed_connections`` even though they are never instantiated.
        self.class_by_name: Dict[str, type] = {"Node": Node}
        for cls in Node.node_type_map.values():
            self.class_by_name[cls.__name__] = cls
            for base in cls.__mro__:
                if issubclass(base, Node):
                    self.class_by_name.setdefault(base.__name__, base)

        #: class name → node_type string (what the constructor dispatch needs).
        self.node_type_by_class: Dict[str, str] = {
            cls.__name__: ntype for ntype, cls in Node.node_type_map.items()
        }

        #: primary IRI → [class names]. Many-to-one for the handful of classes
        #: that declare no ``em_extension.uri`` and fall back to a shared
        #: ``mapping.cidoc`` — see ``resolve_node_class``.
        self.classes_by_iri: Dict[str, List[str]] = {}
        for name in self.dm._node_class_index:
            iri = self.dm.get_node_primary_iri(name)
            if iri is not None:
                self.classes_by_iri.setdefault(str(iri), []).append(name)
        # em_visual_rules 1.6.24 · an acquisition whose KIND declares its own
        # class (a capture: D2 / D11 / E65, dtc_kinds.acquisition.<kind>.mapping)
        # is written with that class instead of D12: read it back as the same
        # DTCAcquisitionNode. The kind itself comes back from P2_has_type.
        # Its superclasses are the kind's, not the class's: they are redundant
        # for THAT node (E65's crm:E7_Activity is ActivityNodeGroup's primary).
        # Kept apart from `classes_by_iri`, which stays the bijective index of
        # the CLASSES' own primary IRIs.
        from ..utils.utils import get_dtc_kind_mappings
        #: kind class IRI → [class names] (always DTCAcquisitionNode today).
        self.kind_classes_by_iri: Dict[str, List[str]] = {}
        #: kind class IRI → the superclass IRIs that kind declares.
        self.kind_superclasses_by_iri: Dict[str, Set[str]] = {}
        for mapping in get_dtc_kind_mappings("acquisition").values():
            iri = _resolve_prefixed_name(mapping.get("cidoc"))
            if iri is not None:
                names = self.kind_classes_by_iri.setdefault(str(iri), [])
                if "DTCAcquisitionNode" not in names:
                    names.append("DTCAcquisitionNode")
                self.kind_superclasses_by_iri.setdefault(str(iri), set()).update(
                    str(sc) for sc in (_resolve_prefixed_name(x)
                                       for x in mapping.get("subclass_of") or [])
                    if sc is not None)

        #: LEGACY index: CIDOC class IRI → [class names] built from
        #: ``mapping.cidoc``, i.e. what each class projected as BEFORE it was
        #: given an ``em_extension.uri``. Consulted only when the primary index
        #: finds nothing, which is exactly the case of a TTL written by an older
        #: release. Datamodel-driven like everything else — ``mapping.cidoc`` is
        #: still there and still says what the CIDOC reading is.
        self.legacy_classes_by_iri: Dict[str, List[str]] = {}
        for name, entry in self.dm._node_class_index.items():
            cidoc = (entry.get("mapping") or {}).get("cidoc")
            iri = _resolve_prefixed_name(cidoc)
            if iri is not None:
                self.legacy_classes_by_iri.setdefault(str(iri), []).append(name)

        #: every IRI that appears as somebody's declared superclass. These are
        #: the redundant types the exporter adds for CRM-only readers.
        self.superclass_iris: Set[str] = set()
        for name in self.dm._node_class_index:
            for sc in self.dm.get_node_superclasses(name):
                self.superclass_iris.add(str(sc))

        #: signature IRI → [edge_type]. The signature is the most specific
        #: predicate the exporter emits for that edge: the AP11 subproperty, or
        #: the extension predicate, or the core CRM one.
        self.edges_by_signature: Dict[str, List[str]] = {}
        #: core predicate IRI → [edge_type] (the always-emitted generic triple)
        self.edges_by_core: Dict[str, List[str]] = {}
        #: edge_type → its core predicate IRI, for the dual-emission cover
        self.core_of_edge: Dict[str, str] = {}
        self._build_edge_inverse()

        #: CIDOC class IRI → [qualia id]. Kept for third-party RDF; ambiguous
        #: by nature, so never used to guess (see ``resolve_property_type``).
        self.qualia_by_iri: Dict[str, List[str]] = {}
        for qid, crm in self.dm._qualia_class_index.items():
            iri = _resolve_prefixed_name(crm)
            if iri is not None:
                self.qualia_by_iri.setdefault(str(iri), []).append(qid)

        #: type_tag ← em: subproperty, inverse of AP11_SUBPROPS. Two edge types
        #: share ``em:bondedTo`` and two share ``em:physicallyEquals``, so the
        #: tag alone cannot name the edge — ``allowed_connections`` and the
        #: canonical choice below finish the job.
        self.tag_by_subprop: Dict[str, str] = {}
        for tag, iri in AP11_SUBPROPS.items():
            self.tag_by_subprop.setdefault(str(iri), tag)

    def _build_edge_inverse(self) -> None:
        edges = self.dm.connections_datamodel.get("edge_types", {})
        for edge_type in edges:
            pred, ext, tag, deprecated = self.dm.get_edge_mapping(edge_type)
            if deprecated:
                # written as canonical by the exporter (has_timebranch →
                # is_in_timebranch); nothing in RDF can point back at the alias
                continue
            if tag:
                sig = AP11_SUBPROPS.get(tag)
            elif ext is not None and ext not in GENERIC_COMPANION_PREDICATES:
                sig = ext
            else:
                sig = pred
            if sig is not None and sig not in GENERIC_COMPANION_PREDICATES:
                self.edges_by_signature.setdefault(str(sig), []).append(edge_type)
            # A CONDITIONAL extension is not always emitted, so the core
            # predicate is the most specific thing on the wire whenever the
            # condition does not hold — i.e. the core is ALSO a signature for
            # this edge. `is_part_of` (2026-09-25) is the first such case:
            # AP21i goes out only when the container is a US, because that is
            # the only target class that maps to A2. Without this, every other
            # containment — a fragment inside a VSF, a unit inside a USD —
            # would leave on P46i alone, find `is_part_of` missing from the
            # signature index, and be declined by the strict pass. Measured:
            # the Templumare round trip lost its is_part_of edges.
            if (self.dm.get_extension_condition(edge_type) is not None
                    and pred is not None
                    and str(pred) not in GENERIC_COMPANION_PREDICATES):
                self.edges_by_signature.setdefault(str(pred), []).append(edge_type)
            if pred is not None:
                self.edges_by_core.setdefault(str(pred), []).append(edge_type)
                self.core_of_edge[edge_type] = str(pred)

        #: predicates that restate an edge FROM THE OTHER SIDE (connections
        #: `mapping.inverse_extension`: is_part_of → <VSF> em:reconstructsFrom
        #: <SF>). The edge comes back from its core predicate; these are skipped.
        self.inverse_extension_predicates: Set[str] = {
            str(p) for p in self.dm.inverse_extension_predicates()}

    # ── node class ──────────────────────────────────────────────────────────

    def resolve_node_class(self, type_iris: Sequence[str],
                           has_pred=None) -> Tuple[Optional[str], Optional[str]]:
        """(class_name, ambiguity_note) for a node's set of ``rdf:type`` IRIs.

        The exported node is multi-typed: its own class plus the CRM
        superclasses. We collect every type that names a class we know, drop the
        ones that are only somebody's superclass, and keep the **most specific**
        — the candidate that is a Python subclass of all the others. That test
        is exact and needs no assumption about namespaces or emission order.

        `has_pred(URIRef) -> bool` lets the caller answer "does this node carry
        that triple?", which is how the one pair the hierarchy cannot separate
        (``GeoPositionNode`` / ``LocationNodeGroup``) is decided — see
        ``CLASS_EVIDENCE``.
        """
        candidates: List[str] = []
        for iri in type_iris:
            for name in (self.classes_by_iri.get(iri, [])
                         + self.kind_classes_by_iri.get(iri, [])):
                if name not in candidates:
                    candidates.append(name)
        if not candidates:
            # LEGACY: a document written before the distinct URIs types its nodes
            # with the bare CIDOC class, which is now nobody's primary IRI. Fall
            # back to what that class used to mean — and from here the old
            # ambiguities are back, which is what CLASS_EVIDENCE is still for.
            for iri in type_iris:
                for name in self.legacy_classes_by_iri.get(iri, []):
                    if name not in candidates:
                        candidates.append(name)
        if not candidates:
            return None, None

        # A type that ANOTHER CANDIDATE declares as its superclass is the
        # redundant CRM one the exporter adds for CRM-only readers.
        #
        # The test is scoped to this node's own candidates, not to the datamodel
        # as a whole. It used to ask «is this IRI anybody's superclass?», which
        # held while every shared CIDOC class had been vacated in favour of an
        # em: URI. Since 2026-09-21 it no longer does: crm:E73_Information_Object
        # is the superclass em:NodeGroup, em:GCPSet and em:RegistrationTransform
        # declare AND still ResourceNode's own primary IRI, so the global test
        # dropped every candidate, fell through to `or candidates`, and returned
        # whichever came first — a GroupNode came back as a ResourceNode.
        redundant = {
            str(sc)
            for n in candidates
            for sc in self.dm.get_node_superclasses(n)
        }
        for iri in type_iris:
            redundant |= self.kind_superclasses_by_iri.get(iri, set())
        specific = [
            n for n in candidates
            if str(self.dm.get_node_primary_iri(n)) not in redundant
        ] or candidates

        # Evidence — LEGACY path only. With the distinct URIs of 2026-08-11 a
        # node resolves to exactly one candidate and this is skipped entirely;
        # it still reads a pre-change TTL, where the shift triples are the only
        # thing telling a GeoPosition from a Location.
        if has_pred is not None and len(specific) > 1:
            for name in specific:
                preds = CLASS_EVIDENCE.get(name)
                if preds and any(has_pred(p) for p in preds):
                    return name, None

        best = specific[0]
        for name in specific[1:]:
            a = self.class_by_name.get(name)
            b = self.class_by_name.get(best)
            if a is not None and b is not None and issubclass(a, b):
                best = name

        # `Node` is the base class, never a type: a node that resolves to it is
        # one the projection could not type more precisely.
        siblings = [
            n for n in specific
            if n != best and n != "Node"
            and not (
                self.class_by_name.get(best) is not None
                and self.class_by_name.get(n) is not None
                and issubclass(self.class_by_name[best], self.class_by_name[n])
            )
        ]
        note = None
        if siblings:
            note = (f"class IRI is shared by {sorted([best] + siblings)}; "
                    f"read as '{best}'")
        return best, note

    # ── edge type ───────────────────────────────────────────────────────────

    def symmetric_spellings(self, candidates: Sequence[str]) -> Optional[str]:
        """The canonical name when these candidates are SPELLINGS OF ONE relation.

        `bonded_to` / `is_bonded_to` and `equals` / `is_physically_equal_to` are
        not a lossy collision: the datamodel declares all four **symmetric**, and
        gives each pair a ``type_tag`` that resolves to the SAME ``em:``
        subproperty. Two names for a relation that has no direction collapse to
        one predicate because that is what they mean — inventing two
        subproperties to keep them apart would assert a direction the relation
        does not have.

        So the test is structural, not a hand-kept list of names: every candidate
        belongs to the AP11 physical family AND they all resolve to one
        subproperty. When that holds, this is a canonicalisation like
        ``has_timebranch → is_in_timebranch``, and it is silent.

        The canonical member is the one the datamodel declares canonical: the
        others name it in `spelling_of` (connections 1.6.20). Only for a family
        without that declaration does the older rule apply — the spelling
        WITHOUT the directional `is_…` prefix. Returns None when the candidates
        are not such a family, so every other ambiguity still warns.
        """
        if len(candidates) < 2:
            return None
        edges = self.dm.connections_datamodel.get("edge_types", {})
        subprops: Set[str] = set()
        for name in candidates:
            mapping = (edges.get(name) or {}).get("mapping") or {}
            tag = mapping.get("type_tag")
            iri = AP11_SUBPROPS.get(tag) if tag else None
            if iri is None:
                return None          # not the physical family: not this case
            subprops.add(str(iri))
        if len(subprops) != 1:
            return None              # different relations, genuinely ambiguous
        # the canonical spelling is the one the datamodel DECLARES: every other
        # member carries `spelling_of` naming it (connections 1.6.20)
        declared = {(edges.get(n) or {}).get("spelling_of") or n
                    for n in candidates}
        if len(declared) == 1:
            return declared.pop()
        # a family the datamodel has not (yet) declared: the older rule — no
        # directional prefix, shortest wins the tie
        return sorted(candidates, key=lambda n: (n.startswith("is_"), len(n), n))[0]

    def emits_inverted(self, edge_type: str) -> bool:
        """Does this edge type's mapping put the edge TARGET in the subject?

        `is_after` does: the EM arrow runs from the more recent unit to the
        more ancient one, while P120/AP28 name the earlier entity first. The
        exporter swaps the ends on the way out, so the reader has to swap them
        back or the sequence comes home reversed — which is exactly what the
        round-trip caught.
        """
        edges = self.dm.connections_datamodel.get("edge_types") or {}
        mapping = (edges.get(edge_type) or {}).get("mapping") or {}
        return mapping.get("rdf_subject") == "target"

    def candidates_for_predicate(self, pred: str) -> List[str]:
        """Edge types whose most specific emitted predicate is `pred`."""
        return list(self.edges_by_signature.get(pred, []))

    def core_candidates_for_predicate(self, pred: str) -> List[str]:
        """Edge types whose generic CRM predicate is `pred`."""
        return list(self.edges_by_core.get(pred, []))

    def _accepts(self, declared: Sequence[str], class_name: Optional[str]) -> bool:
        """Does a declared endpoint list accept a node of this class?

        ``Node`` in the list means "anything"; a base class means the class and
        every subclass of it. Resolved with ``issubclass`` on the live classes,
        so the hierarchy comes from the code the datamodel is generated from.
        """
        if not declared:
            return True
        if class_name is None:
            return True
        cls = self.class_by_name.get(class_name)
        if cls is None:
            return True
        for name in declared:
            if name == "Node":
                return True
            base = self.class_by_name.get(name)
            if base is not None and issubclass(cls, base):
                return True
        return False

    def narrow_by_endpoints(self, candidates: Sequence[str],
                            source_class: Optional[str],
                            target_class: Optional[str]) -> List[str]:
        """Keep the candidates the datamodel allows between these two classes.

        This is the general answer to the many-to-one CRM predicates: the
        datamodel already declares, per edge type, which classes may sit at each
        end. `has_license` and `has_embargo` share `P104_is_subject_to` and are
        told apart by their target (LicenseNode vs EmbargoNode) — not by a table
        written here.
        """
        edges = self.dm.connections_datamodel.get("edge_types", {})
        out: List[str] = []
        for edge_type in candidates:
            allowed = (edges.get(edge_type) or {}).get("allowed_connections") or {}
            if (self._accepts(allowed.get("target") or [], target_class)
                    and self._accepts(allowed.get("source") or [], source_class)):
                out.append(edge_type)
        # Prefer the candidates with the TIGHTEST declared target: a rule that
        # names `Node` accepts everything and would otherwise win ties against
        # the rule that names the actual class.
        if len(out) > 1:
            tight = [e for e in out
                     if "Node" not in ((edges.get(e) or {})
                                       .get("allowed_connections") or {}).get("target", [])]
            if tight:
                out = tight
        return out

    # ── property type ───────────────────────────────────────────────────────

    def resolve_property_type(self, type_iris: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
        """Fallback qualia resolution from the CIDOC class, with honesty.

        Only reached when ``em:hasQualiaType`` is absent (third-party RDF). The
        inverse is one-to-many for the big classes — 27 qualia share
        ``E54_Dimension`` — so a unique answer is returned when there is one and
        a warning otherwise. Guessing "height" for every dimension would be a
        fabricated measurement.
        """
        for iri in type_iris:
            ids = self.qualia_by_iri.get(iri) or []
            if len(ids) == 1:
                return ids[0], None
            if len(ids) > 1:
                return None, (f"{iri} maps to {len(ids)} qualia types "
                              f"({', '.join(sorted(ids)[:4])}…); property_type "
                              f"left unset — no em:hasQualiaType to read")
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Importer
# ─────────────────────────────────────────────────────────────────────────────

class RDFImporter:
    """Rebuild s3Dgraphy graphs from RDF produced by ``RDFExporter``.

    Usage::

        importer = RDFImporter()
        graphs = importer.parse("site.ttl")          # one Graph per em:EMGraph
        graphs = importer.parse(ttl_text, fmt="turtle")
        importer.parse("site.ttl", into_graph=existing)   # import INTO a graph

    ``self.warnings`` collects every ambiguity and everything unrecognised, in
    the same spirit as ``BaseImporter``: an importer that cannot read something
    says so rather than dropping it quietly.
    """

    def __init__(self,
                 base_uri: str = DEFAULT_BASE_URI,
                 config_dir: Optional[Path] = None):
        self.base_uri = base_uri.rstrip("/") + "/"
        self.inverse = _InverseDatamodel(config_dir=config_dir)
        self.warnings: List[str] = []
        self.stats: Dict[str, int] = {
            "graphs": 0, "nodes": 0, "edges": 0,
            "nodes_unmapped": 0, "edges_unmapped": 0,
            "artefacts_skipped": 0,
        }

    # ── public entry point ──────────────────────────────────────────────────

    def parse(self,
              source: Any,
              fmt: Optional[str] = None,
              into_graph: Optional[S3DGraph] = None,
              multigraph: Optional[Any] = None) -> List[S3DGraph]:
        """Parse RDF from a path, a string or bytes; return the rebuilt graphs.

        Args:
            source: file path, or a serialised RDF document (str/bytes).
            fmt: rdflib format name or an extension ('ttl', 'trig', 'jsonld',
                 …). Autodetected from the path suffix when omitted.
            into_graph: import into this Graph instead of making new ones. The
                graph keeps its own ``graph_id``; only its content grows.
            multigraph: a MultiGraphManager to register the rebuilt graphs in.

        Returns:
            The list of graphs built (or the single ``into_graph``).
        """
        store = ConjunctiveGraph()
        parse_format = _format_for(source, fmt)
        if isinstance(source, (bytes, bytearray)):
            store.parse(data=source.decode("utf-8"), format=parse_format)
        elif _looks_like_path(source):
            store.parse(str(source), format=parse_format)
        else:
            store.parse(data=str(source), format=parse_format)

        typed = {str(s) for s in store.subjects(RDF.type, EM.EMGraph)}
        # The graph-SELF node (`<graph>/node/<id>_graphroot`, a GraphNode) is
        # typed em:EMGraph too, because it IS the graph as a node. It is a node
        # of the graph that contains it, not a second graph (dev29 A4, measured
        # on San Pietro: import_rdf returned 2 graphs, the second holding only
        # an auto geo position).
        graph_iris = sorted(i for i in typed
                            if not any(i.startswith(o.rstrip("/") + "/node/")
                                       for o in typed if o != i))
        if not graph_iris:
            self.warnings.append(
                "no em:EMGraph subject found — nothing identifies a graph in "
                "this RDF; expected <base>/graph/<id> typed em:EMGraph")
            return []

        out: List[S3DGraph] = []
        for graph_iri in graph_iris:
            graph_id = self._graph_id_from_iri(graph_iri)
            fresh = into_graph is None
            target = into_graph if not fresh else S3DGraph(graph_id=graph_id)
            self._rebuild_graph(store, graph_iri, target, prune_auto_geo=fresh)
            self.stats["graphs"] += 1
            if into_graph is None:
                out.append(target)
                if multigraph is not None:
                    multigraph.graphs[target.graph_id] = target
        return out if into_graph is None else [into_graph]

    # ── SPARQL source (stretch) ─────────────────────────────────────────────

    #: The CONSTRUCT that lifts a whole named graph out of a store. Written as a
    #: CONSTRUCT rather than a DESCRIBE because DESCRIBE is implementation-defined
    #: (each store decides how much of the neighbourhood to return) and this needs
    #: exactly the graph's own triples, no more and no less.
    CONSTRUCT_GRAPH = (
        "CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}"
    )
    CONSTRUCT_ALL = "CONSTRUCT {{ ?s ?p ?o }} WHERE {{ ?s ?p ?o }}"

    def sparql_query(self, graph_iri: Optional[str] = None) -> str:
        """The CONSTRUCT this importer would send. Public so it is testable
        without a live endpoint — and so a caller can run it by hand."""
        if graph_iri:
            return self.CONSTRUCT_GRAPH.format(graph_iri=graph_iri)
        return self.CONSTRUCT_ALL.format()

    def from_sparql(self,
                    endpoint: str,
                    graph_iri: Optional[str] = None,
                    timeout: int = 60,
                    multigraph: Optional[Any] = None) -> List[S3DGraph]:
        """Pull a graph out of a SPARQL endpoint and rebuild it.

        A ``CONSTRUCT`` asking for Turtle, then straight into :meth:`parse` — the
        store is just another source of the same document, so there is no second
        reconstruction path.

        **Declared limit: this has NOT been exercised against a live store.** The
        query construction is unit-tested (``sparql_query``) and the parse leg is
        the same one every other test covers, but the HTTP conversation with a
        real Virtuoso/Oxigraph — content negotiation, auth, paging on a large
        CONSTRUCT — is untested. Treat it as a wired seam, not a verified path.
        """
        import urllib.parse
        import urllib.request

        query = self.sparql_query(graph_iri)
        url = f"{endpoint}?{urllib.parse.urlencode({'query': query})}"
        request = urllib.request.Request(
            url, headers={"Accept": "text/turtle"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
        return self.parse(body, fmt="turtle", multigraph=multigraph)

    # ── graph identity ──────────────────────────────────────────────────────

    def _graph_id_from_iri(self, graph_iri: str) -> str:
        """`<base>/graph/<id>` → `<id>`; anything else → its last segment.

        Read from the IRI and not from the RDF context on purpose: a Turtle
        document has no contexts, so keying on the IRI is the one rule that
        works for TTL and TriG alike.
        """
        marker = "graph/"
        if marker in graph_iri:
            return graph_iri.rsplit(marker, 1)[-1].strip("/")
        return graph_iri.rstrip("/").rsplit("/", 1)[-1] or "imported_graph"

    # ── graph rebuild ───────────────────────────────────────────────────────

    def _rebuild_graph(self, store: ConjunctiveGraph, graph_iri: str,
                       g: S3DGraph, prune_auto_geo: bool = False) -> None:
        gref = URIRef(graph_iri)

        name = self._one_literal(store, gref, RDFS.label)
        if name:
            g.name = {"default": name} if not isinstance(g.name, str) else name
        desc = self._one_literal(store, gref, DCTERMS.description)
        if desc:
            g.description = ({"default": desc}
                             if not isinstance(g.description, str) else desc)

        if not isinstance(getattr(g, "data", None), dict):
            g.data = {}

        # graph-scope metadata (default author, license, embargo)
        authors = [self._node_id_from_iri(str(o))
                   for o in store.objects(gref, CRM.P94_has_created)]
        authors = [a for a in authors if a]
        if authors:
            g.data["authors"] = authors
        license_val = self._one_literal(store, gref, CRM.P104_is_subject_to)
        if license_val:
            g.data["license"] = license_val
        embargo = self._one_literal(store, gref, EM.embargoUntil)
        if embargo:
            g.data["embargo"] = embargo
        # the study's working language (language.py): read now, because a node's
        # tag equal to it is not the node's own declaration — see _language_data
        self._study_lang = self._one_literal(store, gref, DCTERMS.language)

        # HDT anchor: the HC2 twin this proposition set belongs to
        for o in store.objects(gref, HDTO.HP33i_is_proposition_set_of):
            g.data["parent_hdt_iri"] = str(o)
            break

        node_prefix = graph_iri.rstrip("/") + "/node/"
        node_iris = self._collect_node_iris(store, node_prefix)

        # nodes first: the edge resolution needs their classes
        class_of: Dict[str, Optional[str]] = {}
        id_of: Dict[str, str] = {}
        for iri in node_iris:
            node_id, class_name = self._rebuild_node(store, iri, g)
            if node_id is None:
                continue
            id_of[iri] = node_id
            class_of[iri] = class_name

        # ``Graph.__init__`` creates a ``geo_<graph_id>`` position node as a
        # convenience. When the RDF carries its own — and it usually does, under
        # whatever id the graph had when the node was first made — the graph
        # would end up with two, one of them content and one an artefact of
        # having constructed a Graph object. The imported one is the content, so
        # the auto-created one steps aside. Only for graphs WE made: in an
        # ``into_graph`` import the caller's own geo node is theirs to keep.
        if prune_auto_geo:
            imported = set(id_of.values())
            auto_id = f"geo_{g.graph_id}"
            has_imported_geo = any(
                type(n).__name__ == "GeoPositionNode" and n.node_id in imported
                for n in g.nodes)
            if has_imported_geo and auto_id not in imported:
                g.nodes = [n for n in g.nodes if n.node_id != auto_id]

        # …and written where language.py reads it: the graph-self node, or the
        # legacy graph.data spelling when the graph has none
        if self._study_lang:
            from ..language import STUDY_LANG_KEY
            root = next((n for n in g.nodes
                         if getattr(n, "node_type", "") == "graph"), None)
            if root is not None:
                if not isinstance(getattr(root, "data", None), dict):
                    root.data = {}
                root.data[STUDY_LANG_KEY] = self._study_lang
            else:
                g.data[STUDY_LANG_KEY] = self._study_lang

        self._rebuild_edges(store, node_prefix, id_of, class_of, g)
        self._rebuild_has_property_from_i17(store, node_prefix, id_of, g)
        self._mark_inherited_properties(store, id_of, g)

    @staticmethod
    def _mark_inherited_properties(store: ConjunctiveGraph,
                                   id_of: Dict[str, str],
                                   g: S3DGraph) -> None:
        """Put ``attributes["inherited"]`` back on the has_property edges the
        exporter declared with ``em:inheritsQualia`` (ownership.py). The
        has_property itself was already rebuilt from em:hasQualia / the I17."""
        declared = set()
        for s, o in store.subject_objects(EM.inheritsQualia):
            src, tgt = id_of.get(str(s)), id_of.get(str(o))
            if src and tgt:
                declared.add((src, tgt))
        if not declared:
            return
        for e in g.edges:
            if (e.edge_type == "has_property"
                    and (e.edge_source, e.edge_target) in declared):
                e.attributes["inherited"] = True

    @staticmethod
    def _collect_node_iris(store: ConjunctiveGraph, node_prefix: str) -> List[str]:
        """The subjects that ARE nodes of this graph.

        ``dcterms:identifier`` is the marker: the exporter writes it for every
        node and for nothing else, so the derived subjects it also mints
        (``<arg>/belief``, ``<prop>/proposition``, the ``s3d:qualia_*`` type
        placeholders) are excluded without having to enumerate them.
        """
        out: List[str] = []
        for s in store.subjects(DCTERMS.identifier, None):
            text = str(s)
            if text.startswith(node_prefix):
                out.append(text)
        return sorted(set(out))

    def _node_id_from_iri(self, iri: str) -> Optional[str]:
        if "/node/" not in iri:
            return None
        return iri.rsplit("/node/", 1)[-1]

    # ── node rebuild ────────────────────────────────────────────────────────

    def _rebuild_node(self, store: ConjunctiveGraph, iri: str,
                      g: S3DGraph) -> Tuple[Optional[str], Optional[str]]:
        ref = URIRef(iri)

        # The IDENTIFIER, not the IRI tail: the exporter slugifies spaces when
        # minting IRIs but writes the original id in dcterms:identifier, so this
        # is the lossless side of the pair.
        node_id = self._one_literal(store, ref, DCTERMS.identifier)
        if not node_id:
            return None, None

        type_iris = [str(o) for o in store.objects(ref, RDF.type)]

        # A property node states its qualia id explicitly — the one route that
        # is not ambiguous (the class inverse is one-to-many by nature).
        qualia_type = self._one_literal(store, ref, EM.hasQualiaType)
        class_name: Optional[str]
        if qualia_type is not None:
            class_name = "PropertyNode"
        else:
            class_name, note = self.inverse.resolve_node_class(
                type_iris, has_pred=lambda p: (ref, p, None) in store)
            if note:
                self.warnings.append(f"node '{node_id}': {note}")

        if class_name is None:
            self.stats["nodes_unmapped"] += 1
            self.warnings.append(
                f"node '{node_id}': no known class for rdf:type "
                f"{sorted(type_iris)} — kept as base Node")
            class_name = "Node"

        node_type = self.inverse.node_type_by_class.get(class_name)
        payload: Dict[str, Any] = {"id": node_id}

        label = self._one_literal(store, ref, RDFS.label)
        if label:
            payload["name"] = label
        desc = self._original_literal(store, ref, DCTERMS.description,
                                      "description")
        if desc:
            payload["description"] = desc

        data = self._type_specific_data(store, ref, node_type, type_iris,
                                        qualia_type, node_id)
        # AUDIT1 · the editorial stamps are read for EVERY node type, next to
        # where they are written (`_serialize_editorial`) — one generic pass, not
        # a line in each branch.
        data.update(self._editorial_data(store, ref))
        data.update(self._ai_data(store, ref))
        data.update(self._definition_data(store, ref, class_name, node_id))
        data.update(self._language_data(store, ref, class_name, qualia_type))
        if data:
            payload["data"] = data

        node = self._instantiate(node_type, class_name, payload)
        if node is None:
            return None, None
        # a forced export wrote «⚠︎» before the touched text; the marker came
        # back through _ai_data, so the mark comes off the text
        from ..ai_validation import unflag_node
        unflag_node(node)
        g.add_node(node, overwrite=True)
        self.stats["nodes"] += 1
        return node_id, class_name

    def _language_data(self, store: ConjunctiveGraph, ref: URIRef,
                       class_name: Optional[str],
                       qualia_type: Optional[str]) -> Dict[str, Any]:
        """The inverse of ``RDFExporter._text_literal``: ``data.lang`` back from
        the tag of a text the datamodel marks as natural language
        (``_Datamodel.is_natural_language``, the same answer the exporter asked).

        Only when the tag DIFFERS from the study's working language: a tag equal
        to it is the cascade's second step, not something the node declared, and
        writing it back would return an em.json with data.lang everywhere. An
        untagged literal says nothing and is read as it always was."""
        from ..language import NODE_LANG_KEY, same_language
        # le traduzioni (2b): the exporter writes WHICH language is the
        # original whenever the node declares one — equal to the study's too —
        # so the declaration comes back exactly where it was.
        declared = self._one_literal(store, ref, EM.originalLanguage)
        if declared:
            return {NODE_LANG_KEY: declared}
        klass = self.inverse.class_by_name.get(class_name or "")
        if klass is None:
            return {}
        study = getattr(self, "_study_lang", None)
        probes = [("description", DCTERMS.description, klass)]
        if qualia_type is not None:
            # is_natural_language reads a PropertyNode's quale off the instance
            probe = type("_Probe", (), {"node_type": "property",
                                        "property_type": qualia_type,
                                        "name": None})()
            probes.append(("value", CRM.P90_has_value, probe))
        for prop, predicate, subject in probes:
            if not self.inverse.dm.is_natural_language(subject, prop):
                continue
            # an RDF written before em:originalLanguage: the original's tag, and
            # never a translation's (they share the predicate)
            field = "description" if prop == "description" else "data.value"
            o = self._original_literal(store, ref, predicate, field, raw=True)
            lang = getattr(o, "language", None) if isinstance(o, Literal) else None
            if lang and not same_language(lang, study):
                return {NODE_LANG_KEY: lang}
        return {}

    @staticmethod
    def _translation_literals(store: ConjunctiveGraph, ref: URIRef,
                              field: str) -> Set[Tuple[str, Optional[str]]]:
        """``(text, lang)`` of every translation of ``field`` of ``ref`` — the
        literals the exporter added on the original's predicate. A translation
        is recognised by what it says of itself (prov:wasDerivedFrom → the
        node, em:translatedField), not by its class."""
        out: Set[Tuple[str, Optional[str]]] = set()
        for t in store.subjects(PROV.wasDerivedFrom, ref):
            if not any(str(f) == field
                       for f in store.objects(t, EM.translatedField)):
                continue
            for lit in store.objects(t, CRM.P190_has_symbolic_content):
                if isinstance(lit, Literal):
                    out.add((str(lit), lit.language))
        return out

    def _original_literal(self, store: ConjunctiveGraph, ref: URIRef,
                          pred: URIRef, field: str, *, raw: bool = False):
        """THE original among the literals of ``pred`` (le traduzioni): the one
        that is not a translation's. With several left (a third-party RDF),
        the one tagged with em:originalLanguage wins, then a stable order —
        never whichever the store yields first. ``raw`` returns the Literal,
        otherwise its text (None when there is none)."""
        lits = sorted((o for o in store.objects(ref, pred)
                       if isinstance(o, Literal)),
                      key=lambda o: (o.language or "", str(o)))
        if not lits:
            return None
        if len(lits) > 1:
            taken = self._translation_literals(store, ref, field)
            rest = [o for o in lits if (str(o), o.language) not in taken]
            lits = rest or lits
            original = self._one_literal(store, ref, EM.originalLanguage)
            if original:
                from ..language import same_language
                lits = ([o for o in lits if same_language(o.language, original)]
                        or lits)
        return lits[0] if raw else str(lits[0])

    def _definition_data(self, store: ConjunctiveGraph, ref: URIRef,
                         class_name: Optional[str],
                         node_id: str) -> Dict[str, Any]:
        """The inverse of ``RDFExporter._serialize_definition``, reading the SAME
        datamodel entry (``properties.definition.rdf``) — so the projection is
        still decided in one place. A concept comes back as ``{concept}``: the
        label was never written on it, and resolves at reading. A label comes
        back only when ``rdf.label_only`` names a property (by default it names
        none, and a label-only definition does not survive RDF — by design)."""
        klass = self.inverse.class_by_name.get(class_name or "")
        if klass is None:
            return {}
        rule = self.inverse.dm.get_node_element_rule(klass, "definition")
        if not rule:
            return {}
        rdf = rule.get("rdf") or {}
        predicate = _resolve_prefixed_name(rdf.get("with_concept"))
        if predicate is not None:
            concepts = sorted(str(o) for o in store.objects(ref, predicate)
                              if isinstance(o, URIRef)
                              and (o, DCTERMS.identifier, None) not in store)
            if len(concepts) > 1:
                self.warnings.append(
                    f"node '{node_id}': {len(concepts)} definition concepts "
                    f"{concepts} — kept the first")
            if concepts:
                return {"definition": {"concept": concepts[0]}}
        predicate = _resolve_prefixed_name(rdf.get("label_only"))
        if predicate is not None:
            label = self._one_literal(store, ref, predicate)
            if label:
                return {"definition": {"label": label}}
        return {}

    def _instantiate(self, node_type: Optional[str], class_name: str,
                     payload: Dict[str, Any]) -> Optional[Node]:
        """Build the node through the emjson importer's constructor dispatch.

        Reused rather than rewritten: "given a node_type and a payload, make the
        node" is one problem, already solved there by signature inspection, and
        a second implementation would be a second set of constructor quirks to
        keep in step.
        """
        from .emjson_importer import _instantiate as _emjson_instantiate

        local_warnings: List[str] = []
        if node_type is None:
            # a class the registry does not expose as a node_type (an abstract
            # base, or `Node` itself): construct it directly
            cls = self.inverse.class_by_name.get(class_name, Node)
            try:
                node = cls(payload["id"], payload.get("name", payload["id"]),
                           payload.get("description", ""))
            except Exception as exc:  # pragma: no cover — defensive
                self.warnings.append(
                    f"node '{payload['id']}': constructor failed for "
                    f"{class_name} ({exc}); kept as base Node")
                node = Node(payload["id"], payload.get("name", payload["id"]),
                            payload.get("description", ""))
            data = payload.get("data") or {}
            if data:
                if not isinstance(getattr(node, "data", None), dict):
                    node.data = {}
                node.data.update(data)
            return node

        node = _emjson_instantiate(node_type, payload, local_warnings)
        self.warnings.extend(local_warnings)
        return node

    def _editorial_data(self, store: ConjunctiveGraph,
                        ref: URIRef) -> Dict[str, Any]:
        """The inverse of ``_serialize_editorial`` — the last-hand stamps.

        Read from the em: predicates, not from ``prov:wasAttributedTo``: the
        exporter writes both, and the PROV one cannot say whether the agent it
        names is the creator or the last editor. An agent that came back as an
        ORCID IRI is returned to its bare canonical form, which is what the
        property graph stores.
        """
        from ..editorial import normalize_instant, normalize_orcid

        out: Dict[str, Any] = {}
        for key, pred in (("created_by", EM.createdBy),
                          ("modified_by", EM.lastEditedBy)):
            value = self._one_object_text(store, ref, pred)
            if value:
                out[key] = normalize_orcid(value) or value
        # P4.1 · the tombstone comes back as a tombstone
        removed_at = self._one_literal(store, ref, EM.removedAt)
        if removed_at:
            mark = {"ts": normalize_instant(removed_at)}
            removed_by = self._one_object_text(store, ref, EM.removedBy)
            if removed_by:
                mark["by"] = normalize_orcid(removed_by) or removed_by
            out["removed"] = mark
        for key, pred in (("created_at", PROV.generatedAtTime),
                          ("modified_at", EM.modifiedAt)):
            value = self._one_literal(store, ref, pred)
            if value:
                # rdflib rewrites `…Z` as `…+00:00` on the way through: the same
                # instant, spelled differently. Canonicalised here so a graph
                # does not come home with every stamp reworded.
                out[key] = normalize_instant(value)
        for key, pred in (("created_auth", EM.createdVia),
                          ("modified_auth", EM.modifiedVia)):
            how = self._auth(store, ref, pred)
            if how:
                out[key] = how
        return out

    def _addresses(self, store: ConjunctiveGraph, ref: URIRef) -> List[Dict[str, Any]]:
        """The inverse of ``RDFExporter._emit_addresses``: ``data.addresses`` in
        the order of their number, ``[]`` when the resource keeps no list."""
        from ..editorial import normalize_instant
        found = []
        for addr in store.objects(ref, EM.hasAddress):
            tail = str(addr).rsplit("/address/", 1)[-1]
            loc = self._one_literal(store, addr, EM.locator)
            if not loc:
                continue
            entry: Dict[str, Any] = {"locator": str(loc)}
            res = self._one_literal(store, addr, EM.residency)
            if res:
                entry["residency"] = str(res)
            at = self._one_literal(store, addr, EM.checkedAt)
            if at:
                entry["checked_at"] = normalize_instant(at)
            for o in store.objects(addr, EM.reachable):
                entry["ok"] = str(o).lower() in ("true", "1")
            found.append((int(tail) if tail.isdigit() else 10 ** 6, str(loc), entry))
        return [e for _i, _l, e in sorted(found, key=lambda t: (t[0], t[1]))]

    def _ai_data(self, store: ConjunctiveGraph, ref: URIRef) -> Dict[str, Any]:
        """The inverse of ``RDFExporter._serialize_ai``: ``ai_assisted``,
        ``validated_by``, ``validated_at``. A node reference is given back as
        the id its own ``dcterms:identifier`` states."""
        from ..editorial import normalize_instant

        def node_id_of(pred):
            for o in store.objects(ref, pred):
                ident = self._one_literal(store, o, DCTERMS.identifier) \
                    if isinstance(o, URIRef) else None
                return ident or str(o).rsplit("/", 1)[-1]
            return None

        out: Dict[str, Any] = {}
        marker: Dict[str, Any] = {}
        by = node_id_of(EM.aiAssistedBy)
        if by:
            marker["by"] = by
        model = self._one_literal(store, ref, EM.aiModel)
        if model:
            marker["model"] = model
        prompt = node_id_of(EM.aiPromptRef)
        if prompt:
            marker["prompt_ref"] = prompt
        fields = sorted(str(o) for o in store.objects(ref, EM.aiAssistedField)
                        if str(o) != "*")
        if fields:
            marker["fields"] = fields
        if marker or (ref, EM.aiAssistedField, None) in store:
            out["ai_assisted"] = marker
        validator = node_id_of(EM.validatedBy)
        if validator:
            out["validated_by"] = validator
        at = self._one_literal(store, ref, EM.validatedAt)
        if at:
            out["validated_at"] = normalize_instant(at)
        how = self._auth(store, ref, EM.validatedVia)
        if how:
            out["validated_auth"] = how
        return out

    def _auth(self, store: ConjunctiveGraph, ref: URIRef, predicate) -> Optional[Dict[str, str]]:
        """The inverse of ``RDFExporter._emit_auth``: ``{mode, attested_by?}``."""
        for o in store.objects(ref, predicate):
            mode = self._one_literal(store, o, EM.authMode)
            if not mode:
                continue
            out = {"mode": str(mode)}
            node = self._one_literal(store, o, EM.attestedBy)
            if node:
                out["attested_by"] = str(node)
            return out
        return None

    def _type_specific_data(self, store: ConjunctiveGraph, ref: URIRef,
                            node_type: Optional[str], type_iris: Sequence[str],
                            qualia_type: Optional[str],
                            node_id: str) -> Dict[str, Any]:
        """The inverse of ``_serialize_type_specific``, per node type."""
        data: Dict[str, Any] = {}

        if node_type == "property":
            ptype = qualia_type
            if ptype is None:
                ptype, note = self.inverse.resolve_property_type(type_iris)
                if note:
                    self.warnings.append(f"node '{node_id}': {note}")
            if ptype:
                data["property_type"] = ptype
            value = self._original_literal(store, ref, CRM.P90_has_value,
                                           "data.value")
            if value is not None:
                data["value"] = value
            return data

        if node_type == "translation":
            # the inverse of RDFExporter._serialize_translation
            text = self._one_literal(store, ref, CRM.P190_has_symbolic_content)
            if text is not None:
                data["text"] = text
            lang = self._one_literal(store, ref, CRM.P72_has_language)
            if lang:
                data["lang"] = lang
            for key, pred in (("from_lang", EM.sourceLanguage),
                              ("field", EM.translatedField),
                              ("method", EM.translationMethod),
                              ("source_digest", EM.sourceDigest)):
                value = self._one_literal(store, ref, pred)
                if value:
                    data[key] = value
            flag = self._one_literal(store, ref, EM.reviewRequested)
            if flag is not None and flag.strip().lower() in ("true", "1"):
                data["review_requested"] = True
            return data

        # The real value is "EpochNode" (the class name); "epoch" is accepted too
        # because that is the string the exporter tested for until the round-trip
        # showed it never matched — see the BUGFIX note there.
        if node_type in ("EpochNode", "epoch"):
            start = self._one_literal(store, ref, CRM["P82a_begin_of_the_begin"])
            end = self._one_literal(store, ref, CRM["P82b_end_of_the_end"])
            if start is not None:
                data["start_time"] = _as_number(start)
            if end is not None:
                data["end_time"] = _as_number(end)
            # P90 on an epoch is the lane colour (the exporter's own choice)
            color = self._one_literal(store, ref, CRM.P90_has_value)
            if color:
                data["color"] = color
            return data

        if node_type in ("author", "author_ai"):
            orcid = self._one_literal(store, ref, CRM.P48_has_preferred_identifier)
            if orcid:
                data["orcid"] = orcid
            # P1_is_identified_by since 2026-09-21; P131 is read as a fallback
            # so TTL written before the repair still comes back whole (P131 was
            # deprecated in CRM 7.x with E82 Actor Appellation and is not
            # declared in 7.1.3, so nothing new is ever written on it).
            surname = (self._one_literal(store, ref, CRM.P1_is_identified_by)
                       or self._one_literal(store, ref, CRM.P131_is_identified_by))
            if surname:
                data["surname"] = surname
            model = self._one_literal(store, ref, EM.modelIdentifier)
            if model:
                data["model"] = model
            prompt = self._one_literal(store, ref, EM.promptReference)
            if prompt:
                data["prompt_reference"] = prompt
            # The identity claim comes back as a claim: only the literal `true`
            # verifies. Everything else — absent, "false", anything odd — reads
            # as claimed, which is the safe side of a question about who someone
            # is. (The exporter only writes the triple when it is true, so the
            # absent case is the ordinary one.)
            verified = self._one_literal(store, ref, EM.orcidVerified)
            data["verified"] = str(verified).lower() == "true" if verified else False
            return data

        if node_type == "license":
            ltype = self._one_literal(store, ref, CRM.P2_has_type)
            if ltype:
                data["license_type"] = ltype
            url = self._one_object_text(store, ref, RDFS.seeAlso)
            if url:
                data["url"] = url
            return data

        if node_type == "embargo":
            start = self._one_literal(store, ref, CRM["P82a_begin_of_the_begin"])
            end = self._one_literal(store, ref, CRM["P82b_end_of_the_end"])
            if start:
                data["embargo_start"] = start
            if end:
                data["embargo_end"] = end
            reason = self._one_literal(store, ref, RDFS.comment)
            if reason:
                data["reason"] = reason
            return data

        if node_type == "resource_file":
            # one file of a resource: where its bytes are and their digest, the
            # two things the exporter projects (role and path live on has_file)
            url = self._one_object_text(store, ref, RDFS.seeAlso)
            if url:
                data["url"] = url
            checksum = self._one_literal(store, ref, EM.checksum)
            if checksum:
                data["checksum"] = str(checksum)
            return data

        if node_type == "resource":
            # dev27 (A4): several addresses — address 0 is data.url, and with
            # them every locator is also an rdfs:seeAlso, so the url is read
            # from the list and not from whichever seeAlso the store yields first
            listed = self._addresses(store, ref)
            url = listed[0]["locator"] if listed else \
                self._one_object_text(store, ref, RDFS.seeAlso)
            if url:
                data["url"] = url
            if listed:
                data["addresses"] = listed
            at = self._one_literal(store, ref, EM.checksumAt)
            if at:
                from ..editorial import normalize_instant
                data["checksum_at"] = normalize_instant(at)
            # SHELF1 · integrity and the three fences, read only when PRESENT:
            # a resource that says nothing must come back saying nothing.
            for key, pred in (("checksum", EM.checksum),
                              ("scope", EM.resourceScope),
                              ("residency", EM.residency),
                              # dev29 (A4): how the bytes are packed and what
                              # the digest covers
                              ("packaging", EM.packaging),
                              ("tier", EM.tier),
                              ("digest_covers", EM.digestCovers),
                              ("content_digest", EM.contentDigest)):
                value = self._one_literal(store, ref, pred)
                if value:
                    data[key] = str(value)
            # dev30 (D4): em:membersDigest is the digest of a set by itself —
            # the same value em:checksum carries with em:digestCovers "members";
            # a producer that writes only the new term is read the same way
            members = self._one_literal(store, ref, EM.membersDigest)
            if members:
                data.setdefault("checksum", str(members))
                data.setdefault("digest_covers", "members")
            # dev27: the languages of the content (dcterms:language, one per
            # tag) → data.lang, a string for one and a sorted list for more —
            # the canonical form language.set_content_languages writes
            langs = sorted({str(o) for o in store.objects(ref, DCTERMS.language)
                            if isinstance(o, Literal)})
            if langs:
                data["lang"] = langs[0] if len(langs) == 1 else langs
            # A resource can carry TWO `crm:P2_has_type` literals: its
            # `url_type` and, when it is a DTC product, its `dtc_kind`. They are
            # told apart by what each one IS rather than by order: `url_type` is
            # a CONSTRUCTOR DEFAULT ("External link"), derived from the url and
            # not authored, while `dtc_kind` is authored data and the D1/prov
            # co-typing says it is there. So the default value is recognised and
            # left to the constructor, and what remains is the kind.
            ptypes = [str(o) for o in store.objects(ref, CRM.P2_has_type)
                      if isinstance(o, Literal)]
            is_dtc = any(t.endswith("D1_Digital_Object") for t in type_iris)
            default_url_type = "External link"
            authored = [p for p in ptypes if p != default_url_type]
            if is_dtc:
                if len(authored) == 1:
                    data["dtc_kind"] = authored[0]
                    data["resource_type"] = authored[0]
                elif len(authored) > 1:
                    self.warnings.append(
                        f"node '{node_id}': {len(ptypes)} crm:P2_has_type values "
                        f"{sorted(ptypes)} on a DTC resource — cannot tell "
                        f"url_type from dtc_kind; read '{sorted(authored)[0]}' "
                        f"as dtc_kind")
                    data["dtc_kind"] = sorted(authored)[0]
                    data["resource_type"] = sorted(authored)[0]
                # a plain default-only P2 means no authored kind: leave it out
            elif authored:
                data["url_type"] = authored[0]
            return data

        if node_type == "geo_position":
            epsg = self._one_literal(store, ref, CRM.P2_has_type)
            if epsg and epsg.upper().startswith("EPSG:"):
                data["epsg"] = _as_number(epsg.split(":", 1)[1])
            for axis in ("shift_x", "shift_y", "shift_z", "rotation"):
                v = self._one_literal(store, ref, EM[axis])
                if v is not None:
                    data[axis] = _as_number(v)
            return data

        if node_type == "semantic_shape":
            # The inverse of the payload projection. Note `type`: the
            # SemanticShape constructor validates it against its own enum, so a
            # value it would refuse is dropped with a warning rather than
            # crashing the import of the whole graph.
            convex = [self._floats(o) for o in store.objects(ref, EM.convexShape)]
            spheres = [self._floats(o) for o in store.objects(ref, EM.sphere)]
            if convex:
                data["convexshapes"] = sorted(convex)
            if spheres:
                data["spheres"] = sorted(spheres)
            url = self._one_object_text(store, ref, RDFS.seeAlso)
            if url:
                data["url"] = url
            shape_type = self._one_literal(store, ref, CRM.P2_has_type)
            if shape_type:
                if shape_type in ("proxy", "generic"):
                    data["type"] = shape_type
                else:
                    self.warnings.append(
                        f"node '{node_id}': semantic shape type "
                        f"'{shape_type}' is not one the class accepts; ignored")
            return data

        if node_type == "annotation_region":
            # The geometry comes back by PARSING the selector — the exact inverse
            # of `AnnotationRegionNode.selector()`, which is what makes the region
            # survive as a region and not as a string nobody can read. The
            # constructor is strict (it refuses coordinates outside [0,1]), so a
            # malformed selector must not reach it: warn and leave the geometry
            # out, and the node degrades to a base Node rather than crashing the
            # import of a whole graph.
            from ..nodes.annotation_region_node import (
                AnnotationRegionError, AnnotationRegionNode,
            )
            kind = self._one_literal(store, ref, CRM.P2_has_type)
            if kind in ("passage", "point", "line", "polyline", "volume"):
                data["geometry_kind"] = str(kind)
            selector = self._one_literal(store, ref, EM.hasSelector)
            if data.get("geometry_kind") == "volume":
                # node datamodel 1.6.16: no selector and no vertices — its
                # hulls and spheres are the SemanticShape it points at, which
                # comes back as a node of its own with its edge.
                pass
            elif data.get("geometry_kind") in ("point", "line", "polyline"):
                # No selector for a 3D kind: its vertices come back from the
                # GeoSPARQL WKT of <region>/geometry (node datamodel 1.6.15).
                data.update(self._wkt_coords(store, ref, node_id))
            elif selector:
                try:
                    data.update(AnnotationRegionNode.parse_selector(str(selector)))
                except AnnotationRegionError as exc:
                    self.warnings.append(
                        f"node '{node_id}': region selector not readable ({exc})")
            else:
                self.warnings.append(
                    f"node '{node_id}': an annotation region with no "
                    f"em:hasSelector has no geometry")
            if data.get("geometry_kind") == "passage":
                # The quote: the oa:TextQuoteSelector the exporter hangs off
                # the region (the offsets came back from char= above).
                for sel in store.objects(ref, OA.hasSelector):
                    if (sel, RDF.type, OA.TextQuoteSelector) in store:
                        exact = self._one_literal(store, sel, OA.exact)
                        if exact is not None:
                            data["text"] = exact
                            break
            if data.get("geometry_kind") in ("point", "line", "polyline"):
                vc = self._one_literal(store, ref, EM.vertexCount)
                if vc is not None:
                    data["vertex_count"] = int(vc)
                data.update(self._measure_data(store, ref, node_id))
            page = self._one_literal(store, ref, EM.onPage)
            if page is not None:
                data["page"] = _as_number(page)
            # `resource_id` is the node's own copy of the is_on_resource edge, so
            # a region is readable alone. The edge itself is rebuilt later, from
            # the same triple; reading it here too is what stops the rebuilt node
            # from coming back half — the alternative would be a region that
            # knows its geometry but not which picture it is on.
            on = self._one_object_text(store, ref, EM.isOnResource)
            if on:
                resource_id = self._node_id_from_iri(on)
                if resource_id:
                    data["resource_id"] = resource_id
            return data

        if node_type == "LocationNodeGroup":
            # kind is REQUIRED by the constructor (it raises on anything outside
            # the enum), so a Location whose kind did not survive the projection
            # degraded to a base Node. Read from the P2_has_type the datamodel's
            # own mapping declares.
            kind = self._one_literal(store, ref, CRM.P2_has_type)
            if kind:
                data["kind"] = kind
            propagation = self._one_literal(store, ref, EM.propagation)
            if propagation:
                data["propagation"] = propagation
            return data

        if node_type == "extractor":
            source = self._one_literal(store, ref, CRMINF.J7_is_based_on_evidence_from)
            if source:
                data["source"] = source
            return data

        if node_type in ("dtc_process", "dtc_acquisition"):
            kind = self._one_literal(store, ref, CRM.P2_has_type)
            if kind:
                data["dtc_kind"] = kind
            # dev29 (A4): what the step declares comes back as it left
            technique = self._one_literal(store, ref, EM.technique)
            if technique:
                data["technique"] = technique
            for key, pred in (("parameters", EM.parameters),
                              ("software", EM.software)):
                raw = self._one_literal(store, ref, pred)
                if raw:
                    try:
                        data[key] = json.loads(raw)
                    except ValueError:
                        self.warnings.append(
                            f"{key} of '{ref}' is not JSON — kept as text")
                        data[key] = raw
            # dev30 (D1): the origin of a retrieval comes back among the
            # event's facts, where bucket_acquisition writes them
            origin = self._one_literal(store, ref, EM.retrievedFrom)
            if origin and node_type == "dtc_acquisition":
                data["retrieved_from"] = str(origin)
            software = data.get("software")
            if isinstance(software, list) and software \
                    and isinstance(software[0], dict) and software[0].get("name"):
                # the card the interfaces read, filled as declare_derivation does
                data.setdefault("tool", dict(software[0]))
            return data

        if node_type == "narrative":
            lang = self._one_literal(store, ref, CRM.P72_has_language)
            if lang:
                data["lang"] = lang
            return data

        return data

    # ── edge rebuild ────────────────────────────────────────────────────────

    def _rebuild_edges(self, store: ConjunctiveGraph, node_prefix: str,
                       id_of: Dict[str, str], class_of: Dict[str, Optional[str]],
                       g: S3DGraph) -> None:
        """Turn node-to-node triples back into edges, once each.

        The exporter emits a PAIR of triples per edge where it can — the
        specific em:/extension predicate for expressive SPARQL and the generic
        CRM one for CRM-only readers (and AP11 subproperty + AP11 generic for
        the physical family). Reading naively would therefore produce two edges
        where the author drew one. So the specific triples are resolved first
        and the core predicate they imply is marked as already accounted for;
        only the leftover core triples are resolved on their own.
        """
        # (source_iri, target_iri) → {predicate}
        pairs: Dict[Tuple[str, str], Set[str]] = {}
        for s, p, o in store:
            if not isinstance(s, URIRef) or not isinstance(o, URIRef):
                continue
            s_text, o_text = str(s), str(o)
            if s_text not in id_of or o_text not in id_of:
                continue
            if (p in ARTEFACT_PREDICATES
                    or str(p) in self.inverse.inverse_extension_predicates):
                self.stats["artefacts_skipped"] += 1
                continue
            if p == RDF.type:
                continue
            pairs.setdefault((s_text, o_text), set()).add(str(p))

        counter = 0
        for (s_text, o_text), preds in sorted(pairs.items()):
            src_class = class_of.get(s_text)
            tgt_class = class_of.get(o_text)
            src_id, tgt_id = id_of[s_text], id_of[o_text]

            # prov:wasDerivedFrom from a translation restates has_translation
            # (crm:P73, from the other side): the edge comes back from P73
            if src_class == "TranslationNode" and str(PROV.wasDerivedFrom) in preds:
                preds = preds - {str(PROV.wasDerivedFrom)}
                self.stats["artefacts_skipped"] += 1
                if not preds:
                    continue

            # P67 from a narrative is a projection of its chapters, not an edge
            src_type = self.inverse.node_type_by_class.get(src_class or "")
            if src_type in P67_CONTENT_SOURCES:
                preds = {p for p in preds if p != str(CRM.P67_refers_to)}
                if not preds:
                    self.stats["artefacts_skipped"] += 1
                    continue

            resolved: List[str] = []
            covered_cores: Set[str] = set()

            # 1) the specific predicates name the edge almost by themselves
            for pred in sorted(preds):
                cands = self.inverse.candidates_for_predicate(pred)
                if not cands:
                    continue
                pick = self._pick(cands, src_class, tgt_class, pred,
                                  src_id, tgt_id, strict=True)
                if pick is None:
                    continue
                resolved.append(pick)
                core = self.inverse.core_of_edge.get(pick)
                if core:
                    covered_cores.add(core)
                # the AP11 family also emits the generic AP11 triple; a
                # specific em: subproperty therefore accounts for it too
                covered_cores.add(str(CRMARCHAEO.AP11_has_physical_relation_to))

            # 1b) the exporter writes dtc_had_input to an EVENT (a whole
            #     acquisition consumed as one input) as prov:wasInformedBy,
            #     because L10/prov:used range over digital objects; it comes
            #     back as the one edge it always was (dev29 A4: 4 edges of San
            #     Pietro were «matches no edge type»)
            informed = str(PROV.wasInformedBy)
            if informed in preds and _is_dtc_class(src_class) \
                    and _is_dtc_class(tgt_class):
                resolved.append("dtc_had_input")
                covered_cores.add(informed)

            # 2) leftover core predicates — a triple the specific pass did not
            #    already account for
            for pred in sorted(preds):
                if pred in covered_cores:
                    continue
                if self.inverse.candidates_for_predicate(pred):
                    continue  # handled above (or deliberately unresolvable)
                cands = self.inverse.core_candidates_for_predicate(pred)
                if not cands:
                    self.stats["edges_unmapped"] += 1
                    self.warnings.append(
                        f"predicate {pred} between '{src_id}' and '{tgt_id}' "
                        f"matches no edge type — connection not imported")
                    continue
                pick = self._pick(cands, src_class, tgt_class, pred,
                                  src_id, tgt_id)
                if pick is not None:
                    resolved.append(pick)

            for edge_type in dict.fromkeys(resolved):
                counter += 1
                if self.inverse.emits_inverted(edge_type):
                    a, b = tgt_id, src_id
                else:
                    a, b = src_id, tgt_id
                g.add_edge(f"rdf_e{counter}", a, b, edge_type)
                self.stats["edges"] += 1

    def _rebuild_has_property_from_i17(self, store: ConjunctiveGraph,
                                       node_prefix: str,
                                       id_of: Dict[str, str],
                                       g: S3DGraph) -> None:
        """Recover the `has_property` edges from the I17 propositions.

        `has_property` is one of the two edges whose triples the edge pass
        deliberately ignores: `crm:P43_has_dimension` / `em:hasQualia` carry it,
        and they are read there — but the SUBJECT side of a proposition
        (`J30_has_domain`) is in `ARTEFACT_PREDICATES`, because on its own it is
        part of the belief skeleton and not a connection anyone drew.

        Since the propositions became one-per-pair, though, they are the only
        place that records EVERY unit claiming a property. A property with three
        parents projects three I17, each naming its own unit; without this pass
        two of those three attributions would be read as belief furniture and
        dropped. So the I17 set is consulted for exactly this: `<i17>
        J30_has_domain <unit>` where the I17's IRI names the property gives back
        `unit --has_property--> property`.

        Idempotent against the edge pass: an edge already rebuilt from the
        P43/em:hasQualia triples is not added twice.
        """
        existing = {(e.edge_source, e.edge_target, e.edge_type) for e in g.edges}
        counter = 0
        i17_type = CRMINF["I17_One-Proposition_Set"]
        for i17 in store.subjects(RDF.type, i17_type):
            text = str(i17)
            if "/proposition" not in text:
                continue
            prop_iri = text.rsplit("/proposition", 1)[0]
            if not prop_iri.startswith(node_prefix):
                continue
            prop_id = id_of.get(prop_iri)
            if prop_id is None:
                continue
            for unit in store.objects(i17, CRMINF.J30_has_domain):
                unit_id = id_of.get(str(unit))
                if unit_id is None:
                    continue
                key = (unit_id, prop_id, "has_property")
                if key in existing:
                    continue
                existing.add(key)
                counter += 1
                g.add_edge(f"rdf_i17_{counter}", unit_id, prop_id, "has_property")
                self.stats["edges"] += 1

    def _pick(self, candidates: List[str], src_class: Optional[str],
              tgt_class: Optional[str], pred: str,
              src_id: str, tgt_id: str,
              strict: bool = False) -> Optional[str]:
        """One edge type out of the candidates, or None.

        `strict` is set on the SPECIFIC pass, and it is what stops a triple from
        being counted twice. One predicate can be the *signature* of one edge and
        the *generic companion* of another: ``P46i_forms_part_of`` identifies
        ``heritage_part_of`` and is also emitted beside every ``is_part_of``. When
        the only candidate is one the datamodel does not allow between these two
        classes, the triple is the companion, not the edge — so it is declined
        rather than forced.

        Forcing it was not a silent error, which is how it was found: the graph's
        own ``add_edge`` refuses a disallowed connection and rewrites it as
        ``generic_connection``, so 28 ``is_part_of`` edges came back as
        ``is_part_of`` PLUS 28 spurious generic ones.
        """
        narrowed = self.inverse.narrow_by_endpoints(candidates, src_class, tgt_class)
        if len(narrowed) == 1:
            return narrowed[0]
        if strict and not narrowed:
            return None
        if len(candidates) == 1:
            return candidates[0]
        pool = narrowed or candidates
        if not pool:
            return None
        # SYMMETRIC SPELLINGS — not an ambiguity at all. Two names for one
        # directionless relation collapse onto one predicate BY DESIGN (the
        # datamodel declares them symmetric and gives them the same em:
        # subproperty), so canonicalising is the correct reading and warning
        # about it reported a non-problem. Silent, exactly like
        # `has_timebranch → is_in_timebranch`.
        canonical = self.inverse.symmetric_spellings(pool)
        if canonical is not None:
            return canonical
        # Everything else that the endpoints could not separate IS an ambiguity:
        # a choice is made and recorded, never silently.
        pick = sorted(pool)[0]
        self.warnings.append(
            f"predicate {pred} between '{src_id}' and '{tgt_id}' is ambiguous "
            f"between {sorted(pool)}; read as '{pick}'")
        return pick

    # ── literal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _floats(value: Any) -> List[float]:
        """A space-separated coordinate literal → the numbers it holds.

        Sorting the resulting lists (see the caller) is what keeps the round-trip
        stable: RDF is a SET, so the order two hulls come back in is not the
        order they went out in, and a proxy whose hulls swapped places would
        re-export to different literals — not a difference in the geometry, but
        enough to break isomorphism-of-the-second-projection.
        """
        out: List[float] = []
        for chunk in str(value).replace(",", " ").split():
            try:
                out.append(float(chunk))
            except ValueError:
                continue
        return out

    def _wkt_coords(self, store: ConjunctiveGraph, ref: URIRef,
                    node_id: str) -> Dict[str, Any]:
        """coords / crs from ``geo:hasGeometry → geo:asWKT`` — the inverse of
        the exporter's 3D-reading branch (see geometry/wkt.py). Absent when the
        vertices are a .glb resource (above the threshold)."""
        from ..exporter.rdf_exporter import GEO
        from ..geometry.wkt import WktError, wkt_to_coords
        for geom in store.objects(ref, GEO.hasGeometry):
            wkt = self._one_literal(store, geom, GEO.asWKT)
            if wkt is None:
                continue
            try:
                crs, _shape, coords = wkt_to_coords(wkt)
            except WktError as exc:
                self.warnings.append(f"node '{node_id}': geometry not readable ({exc})")
                return {}
            return {"coords": coords, "crs": crs}
        return {}

    def _measure_data(self, store: ConjunctiveGraph, ref: URIRef,
                      node_id: str) -> Dict[str, Any]:
        """length / unit / crs from the region's E54 Dimension typed "length".

        The inverse of `RDFExporter._emit_measure`: a QUDT unit IRI comes back
        as the short unit it was written from, a minted `s3d:unit_<u>` as
        `<u>`; any other unit IRI is kept whole rather than guessed at.
        """
        unit_of = {str(iri): short for short, iri in MEASURE_UNIT_IRI.items()}
        for dim in store.objects(ref, CRM.P43_has_dimension):
            if self._one_literal(store, dim, CRM.P2_has_type) != "length":
                continue
            value = self._one_literal(store, dim, CRM.P90_has_value)
            if value is None:
                continue
            try:
                out: Dict[str, Any] = {"length": float(value)}
            except ValueError:
                self.warnings.append(
                    f"node '{node_id}': measured length {value!r} is not a number")
                return {}
            unit = self._one_object_text(store, dim, CRM.P91_has_unit)
            if unit:
                if unit in unit_of:
                    unit = unit_of[unit]
                elif unit.startswith(str(S3D) + "unit_"):
                    unit = unit[len(str(S3D) + "unit_"):]
                out["unit"] = unit
            crs = self._one_literal(store, dim, EM.crs)
            if crs:
                out["crs"] = crs
            return out
        return {}

    @staticmethod
    def _one_literal(store: ConjunctiveGraph, ref: URIRef,
                     pred: URIRef) -> Optional[str]:
        for o in store.objects(ref, pred):
            if isinstance(o, Literal):
                return str(o)
        return None

    @staticmethod
    def _one_object_text(store: ConjunctiveGraph, ref: URIRef,
                         pred: URIRef) -> Optional[str]:
        """A value that may have been emitted as a URIRef or as a Literal."""
        for o in store.objects(ref, pred):
            return str(o)
        return None


def _is_dtc_class(class_name: Optional[str]) -> bool:
    """A DTC event class (process, acquisition, or the DTCNode parent)."""
    return bool(class_name) and class_name in ("DTCProcessNode",
                                               "DTCAcquisitionNode", "DTCNode")


def _as_number(text: Any) -> Any:
    """Numbers come back as numbers when they went out as numbers.

    Epoch bounds and shift axes are numeric in the property graph; a Literal
    read back as ``"476"`` would make an epoch's start a string and break every
    chronological comparison downstream.
    """
    if text is None or isinstance(text, (int, float)):
        return text
    s = str(text).strip()
    if not s:
        return text
    try:
        if re.fullmatch(r"[+-]?\d+", s):
            return int(s)
        return float(s)
    except ValueError:
        return text


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helpers
# ─────────────────────────────────────────────────────────────────────────────

def import_rdf(source: Any,
               fmt: Optional[str] = None,
               base_uri: str = DEFAULT_BASE_URI,
               into_graph: Optional[S3DGraph] = None) -> Tuple[List[S3DGraph], List[str]]:
    """One-call helper: (graphs, warnings)."""
    importer = RDFImporter(base_uri=base_uri)
    graphs = importer.parse(source, fmt=fmt, into_graph=into_graph)
    return graphs, importer.warnings
