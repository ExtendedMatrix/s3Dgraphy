# 3dgraphy/nodes/stratigraphic_node.py

import re
from typing import Any, Optional, Tuple

from .base_node import Node

#: The node element that says what GENRE of US a unit is (datamodel 1.6.12,
#: ``StratigraphicUnit.properties.stratigraphic_kind``); em.json carries it as
#: ``data.stratigraphic_kind``. Absent = an ordinary US, and nothing is written.
STRATIGRAPHIC_KIND = "stratigraphic_kind"

#: A masonry unit. USM is a RECORDING PRACTICE, not a category of the EM
#: language (E.D., 30 Sep 2026): a USM is a US whose kind is masonry, and its
#: name keeps saying USM.
MASONRY = "masonry"

#: The node_type some writers produced for a masonry unit before 1.6.12. Not a
#: type of the datamodel: it opens as a US + masonry (emjson_importer).
LEGACY_USM_NODE_TYPE = "USM"

#: A coating unit — plaster, floor, revetment (1.6.13, E.D. 30 Sep 2026). Two
#: codes, the same thing in two languages: USR (rivestimento) and USS (surface,
#: its English translation). Like the USM, a recording practice: a US whose
#: kind is coating, and its name keeps saying USR / USS.
COATING = "coating"

#: The node element that keeps the CODE a unit came in with, when it is not the
#: default code of its kind (USS for a coating, WSU for a masonry…), so that the
#: way back to pyArchInit gives the same code (datamodel 1.6.13,
#: ``StratigraphicUnit.properties.source_code``; em.json ``data.source_code``).
SOURCE_CODE = "source_code"

#: Type strings that name a unit of a given kind. USM and pyArchInit's localized
#: codes for it (sync/rapporti.UNITA_TIPO_CANONICAL): WSU en/ar, MSE de,
#: UEM es/ca/pt, USZ ro, ΤΣΜ el. The coating has no localized code in pyArchInit
#: (its UNIT_TYPE_ABBREV localizes only US and USM): USR and USS.
KIND_TYPE_CODES = {
    MASONRY: ("USM", "WSU", "MSE", "UEM", "USZ", "ΤΣΜ"),
    COATING: ("USR", "USS"),
}

#: The code a kind goes back with when the unit did not come in with another.
KIND_DEFAULT_CODE = {MASONRY: "USM", COATING: "USR"}

#: code → kind, from the table above.
KIND_OF_CODE = {code: kind for kind, codes in KIND_TYPE_CODES.items()
                for code in codes}

#: How a unit's kind is recognised from its NAME — the only thing that tells it
#: apart in a yEd file, because the EM palette draws a USM or a USR exactly as a
#: US (the palette's own US template is labelled USM01). A separator is allowed,
#: a digit is required: "USM101", "USR 3", "USS-15"; not "USMA" nor a bare "USM".
_KIND_NAME = re.compile(
    r"^(?P<code>" + "|".join(KIND_OF_CODE) + r")[\s._-]*\d")


def kind_of_name(name: Any) -> Tuple[Optional[str], Optional[str]]:
    """``(kind, code)`` a unit's name reads as (``("coating", "USS")`` for
    USS12), or ``(None, None)`` for any other name."""
    if not isinstance(name, str):
        return None, None
    m = _KIND_NAME.match(name.strip())
    if not m:
        return None, None
    return KIND_OF_CODE[m.group("code")], m.group("code")


def is_masonry_name(name: Any) -> bool:
    """True when ``name`` reads as a masonry unit's (USM101, WSU 4, MSE-2…)."""
    return kind_of_name(name)[0] == MASONRY


def is_coating_name(name: Any) -> bool:
    """True when ``name`` reads as a coating unit's (USR101, USS 3…)."""
    return kind_of_name(name)[0] == COATING


def is_masonry(node: Any) -> bool:
    """True for a US whose ``stratigraphic_kind`` is masonry."""
    return (getattr(node, "node_type", None) == "US"
            and getattr(node, STRATIGRAPHIC_KIND, None) == MASONRY)


def is_coating(node: Any) -> bool:
    """True for a US whose ``stratigraphic_kind`` is coating."""
    return (getattr(node, "node_type", None) == "US"
            and getattr(node, STRATIGRAPHIC_KIND, None) == COATING)


def set_kind(node: Any, kind: str, code: Optional[str] = None) -> Any:
    """Give a US its kind, and keep ``code`` when it is not the kind's default
    one. A node that is not a US, or states ANOTHER kind, is left alone; one
    that states the same kind only learns the code, if it has none (the
    pyArchInit projector builds the node from the canonical code, USR, and then
    tells it the row's own, USS)."""
    if getattr(node, "node_type", None) != "US":
        return node
    stated = getattr(node, STRATIGRAPHIC_KIND, None)
    if stated and stated != kind:
        return node
    setattr(node, STRATIGRAPHIC_KIND, kind)
    if code and code != KIND_DEFAULT_CODE.get(kind) \
            and not getattr(node, SOURCE_CODE, None):
        setattr(node, SOURCE_CODE, code)
    return node


def unit_code(node: Any) -> Optional[str]:
    """The code a US of a kind goes back to pyArchInit with: the one it came in
    with, or its kind's default (USM, USR). ``None`` for a US without a kind."""
    kind = getattr(node, STRATIGRAPHIC_KIND, None) \
        if getattr(node, "node_type", None) == "US" else None
    if kind not in KIND_DEFAULT_CODE:
        return None
    code = getattr(node, SOURCE_CODE, None)
    if code and KIND_OF_CODE.get(code) == kind:
        return code
    return KIND_DEFAULT_CODE[kind]


def definition_parts(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """``(concept_uri, label)`` of a unit's DEFINITION, or ``(None, None)``.

    The definition is an element of the node (datamodel 1.6.9,
    ``StratigraphicNode.properties.definition``) whose value is a CONCEPT:
    ``{concept: <uri>, label: <str>}`` (stratigraph-templates SPEC §1.5). Also
    read, because data written by hand will carry them: a bare string that is an
    IRI (a concept without its label) and a bare string that is not (a label
    without its concept). Nothing is invented for the second: it stays a label.
    """
    if isinstance(value, dict):
        concept = value.get("concept")
        label = value.get("label")
        concept = concept.strip() if isinstance(concept, str) and concept.strip() else None
        label = label.strip() if isinstance(label, str) and label.strip() else None
        return concept, label
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.startswith(("http://", "https://", "urn:")):
            return text, None
        return None, text
    return None, None


class StratigraphicNode(Node):
    """
    Base class for all stratigraphic units within the graph structure.
    Inherits from Node and provides additional functionality specific to stratigraphy.

    ``definition`` is the DEFINIZIONE of the unit sheet (strato di crollo,
    riempimento, taglio…): an element of the node like ``name`` and
    ``description``, not a qualia. Its value is a controlled-vocabulary concept
    ``{concept, label}`` (see :func:`definition_parts`); em.json carries it as
    ``data.definition``, which is also the field a CRDT ``update_field``
    addresses.
    """
    node_type = "StratigraphicNode"

    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = None
        self.label = None
        self.detailed_description = None  # To avoid conflict with `description`
        self.definition = None


class StratigraphicUnit(StratigraphicNode):
    """A US. ``stratigraphic_kind`` says its genre when it has one —
    ``"masonry"`` (a USM) or ``"coating"`` (a USR / USS) — and is ``None`` for
    an ordinary US. A node element like ``definition``: em.json carries it as
    ``data.stratigraphic_kind``. ``source_code`` keeps the code it came in with
    when that is not its kind's default (USS, WSU…)."""
    node_type = "US"

    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "white rectangle"
        self.label = "US (or SU)"
        self.detailed_description = "Stratigraphic Unit (SU) or negative stratigraphic unit."
        self.stratigraphic_kind = None
        self.source_code = None

class VirtualStratigraphicUnit(StratigraphicNode):
    """Abstract parent of the virtual stratigraphic units (USV/s, USV/n).

    Introduced 2026-07-12 (datamodel curation, EMStudio ADR-001): the
    connections datamodel references ``VirtualStratigraphicUnit`` in
    ``allowed_connections`` but no such class existed — the concrete USV
    classes descended from ``StratigraphicNode`` directly, so class-based
    rule matching had to special-case the name. No ``node_type``: the class
    is abstract, only its subclasses are instantiated.
    """


class StructuralVirtualStratigraphicUnit(VirtualStratigraphicUnit):
    node_type = "USVs"

    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "black parallelogram"
        self.label = "USV/s"
        self.detailed_description = "Structural Virtual Stratigraphic Unit (USV/s)."


class SeriesOfStratigraphicUnit(StratigraphicNode):
    node_type = "serSU"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "white ellipse"
        self.label = "US series"
        self.detailed_description = "Series of Stratigraphic Units (SU)."


class SeriesOfNonStructuralVirtualStratigraphicUnit(StratigraphicNode):
    node_type = "serUSVn"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "black ellipse green border"
        self.label = "USVn series"
        self.detailed_description = "Series of non-structural Virtual Stratigraphic Units."


class SeriesOfStructuralVirtualStratigraphicUnit(StratigraphicNode):
    node_type = "serUSVs"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "black ellipse blue border"
        self.label = "USVs series"
        self.detailed_description = "Series of Structural Virtual Stratigraphic Units."


class SeriesOfDocumentaryStratigraphicUnit(StratigraphicNode):
    node_type = "serUSD"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "white ellipse with orange border"
        self.label = "USD series"
        self.detailed_description = "Series of Documentary Stratigraphic Units (USD)."


class NonStructuralVirtualStratigraphicUnit(VirtualStratigraphicUnit):
    node_type = "USVn"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "black hexagon"
        self.label = "USV/n"
        self.detailed_description = "Non-structural Virtual Stratigraphic Unit (USV/n)."


class SpecialFindUnit(StratigraphicNode):
    node_type = "SF"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "white octagon"
        self.label = "Special Find"
        self.detailed_description = "Not in situ element that needs repositioning."


class VirtualSpecialFindUnit(StratigraphicNode):
    node_type= "VSF"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "black octagon"
        self.label = "Virtual Special Find"
        self.detailed_description = "Hypothetical reconstruction of a fragmented Special Find."


class ReusedSpecialFind(StratigraphicNode):
    """Reused Special Find (RSF) — re-used architectural / decorative
    element (spolia) in archaeological reconstructions.

    Typological cousin of :class:`SpecialFindUnit` (SF) and
    :class:`VirtualSpecialFindUnit` (VSF): all three render as octagons.
    RSF is distinguished by its **red** border (``#9B3333``) and a white
    fill, marking the element as physically present *and* re-deployed
    out of its original construction context.

    Originating Development Project: DP-26 (spolia project, last DP
    before the EM 1.5 cut). Visual stencil shipped in the palette
    template at ``templates/em_palette_template.graphml``.
    """
    node_type = "RSF"

    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "white octagon red border"
        self.label = "Reused Special Find"
        self.detailed_description = (
            "Re-used architectural or decorative element (spolia) in "
            "archaeological reconstructions. A physical find observed "
            "in situ but originally produced for a different context.")


class DocumentaryStratigraphicUnit(StratigraphicNode):
    node_type = "USD"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "white round rectangle"
        self.label = "USD"
        self.detailed_description = "Documentary Stratigraphic Unit."


class TransformationStratigraphicUnit(StratigraphicNode):
    node_type = "TSU"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "dotted white rectangle"
        self.label = "TSU"
        self.detailed_description = "Transformation Unit."


class WorkingUnit(StratigraphicNode):
    node_type = "UL"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "white rectangle with orange border"
        self.label = "UL"
        self.detailed_description = "Working Unit. Traces of stone working, toolmarks, reworkings on architectural surfaces."


class NegativeStratigraphicUnit(StratigraphicNode):
    """Negative Stratigraphic Unit, displayed ``US-`` (US negativa).

    Describes a *lacuna* produced by a REMOVAL: a pit cut, an erosion
    surface, a demolition void. What defines it is the destructive act —
    matter that was there and is not any more — which is what separates
    it from :class:`NeutralStratigraphicUnit`, the void that was never
    filled because it was never meant to be.

    Equally observable on the ground as a positive unit, hence the
    ``real`` family alongside :class:`StratigraphicUnit` and
    :class:`DocumentaryStratigraphicUnit`.

    .. note:: ``node_type`` is ``USN``, which is what it has always been in
       this library and what pyArchInit vendors — and it reads as the
       Italian *US Negativa*. POL5 briefly moved it to ``USNeg`` to give
       ``USN`` to the neutral unit; POL6 undid that (E.D.), because a token
       whose spelling says "negativa" cannot mean "neutra" without costing
       every reader a translation table, and because it put s3dgraphy and
       pyArchInit in disagreement about one three-letter word. The neutral
       unit is ``USNt``.
    """
    node_type = "USN"

    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "grey rectangle, solid border"
        self.label = "US-"
        self.detailed_description = (
            "Negative Stratigraphic Unit (US-) — a lacuna left by a "
            "removal: a pit cut, an erosion surface, a demolition void.")


class NeutralStratigraphicUnit(StratigraphicNode):
    """Neutral Stratigraphic Unit (``USNt``, Unità Stratigrafica Neutra).

    A void that is part of the design, not the product of a destruction:
    the *risparmi* of masonry — a window or door opening, the empty
    volume of a room. The wall was built around it, so nothing was ever
    removed and nothing is missing.

    This is the distinction E.D. asked for in POL5, and it is a real one
    on site: a demolition void (:class:`NegativeStratigraphicUnit`, ``USN``,
    shown ``US-``) is evidence of an ACT, while a *risparmio* is evidence of
    an INTENTION. Reading one as the other inverts the sequence — the void
    would be dated to a removal that never happened.

    ``real`` family: a risparmio is directly observable, and it is drawn
    with the outline at the four corners only (see ``em_visual_rules``),
    because the excavation observes its extent and not a surface.

    .. note:: The token is ``USNt`` since POL6 (2026-08-04). It was briefly
       ``USN``, but that spelling belongs to the *negativa* here and in
       pyArchInit; ``USNt`` is new, free of collisions, and still reads as
       the abbreviation of "US Neutra".

    .. warning:: STRATIGRAPHIC RELATIONS (E.D.): a neutral unit takes
       ``is_after`` / ``is_before`` and **nothing else**. It is a void: it
       cannot cut, fill, abut or be bonded to anything. The rule is data,
       not code — ``s3Dgraphy_connections_datamodel.json`` →
       ``node_type_restrictions.USNt``.

    .. todo:: CIDOC: ``USNt`` (risparmio) — probabile
       ``A3_Stratigraphic_Interface`` con genesi COSTRUTTIVA
       (``A4_Stratigraphic_Genesis``), distinta dalla negativa che nasce da
       una A5 distruttiva. NON è detto sia una classe nuova: E.D. coordina
       con Achille Felicetti / CRMarchaeo. Il datamodel porta un
       placeholder A3 marcato TENTATIVO.
    """
    node_type = "USNt"

    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "grey outline at the four corners only"
        self.label = "USNt"
        self.detailed_description = (
            "Neutral Stratigraphic Unit (USNt) — a void by design, not by "
            "removal: a window or door opening, a niche, the volume of a "
            "room. Only is_after/is_before relations.")


class ContinuityNode(StratigraphicNode):
    node_type = "BR"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "black rhombus"
        self.label = "continuity node"
        self.detailed_description = "End of life of a US/USV."


class StratigraphicEventNode(StratigraphicNode):
    node_type = "SE"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "to be defined"
        self.label = "stratigraphic event node"
        self.detailed_description = "A stratigraphic event is the process or event that leads to the formation or alteration of a stratigraphic unit. It is distinct from the unit itself, which represents the result or outcome of the event. The event can be thought of as a precursor and can be paired with its resulting unit to provide a more detailed temporal range. This allows for the documentation of both the initial moment of action (e.g., the start of construction, a collapse, or an incision) and the final state (the resulting unit that persists over time)."


class UnknownNode(StratigraphicNode):
    node_type = "unknown"
    def __init__(self, node_id, name, description=""):
        super().__init__(node_id, name, description)
        self.symbol = "question mark"
        self.label = "Unknown node"
        self.detailed_description = "Fallback node for unrecognized types."
