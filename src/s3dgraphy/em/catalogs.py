"""``em.catalogs`` — the datamodel's catalogues, read only (MICRO-SEG09, 21 Nov 2026).

E.D.: «ci sono tutti i data object di s3dgraphy?». The node and edge TYPES
were already there (``em.graph`` returns them, ``reference/types`` has a page
for each); the catalogues of ``JSON_config`` were read only inside the library.
Here they are, as the library reads them — the EM language's own tables, not
the logic of any one tool::

    from s3dgraphy import em
    em.catalogs.versions()                    # the datamodel's versions
    em.catalogs.node_types()["StratigraphicUnit"]["node_type"]   # 'US'
    em.catalogs.edge_types()["is_after"]["reverse"]["name"]
    sorted(em.catalogs.qualia_types())[:3]    # the core qualia, by id
    em.catalogs.state_symbols()["states"]["check.ok"]["glyph"]

Every function answers a COPY (as :class:`~s3dgraphy.em.GraphView` does): what
a script changes in it changes nothing in the datamodel. The qualia, extractor
and document types here are the CORE ones; with the active packages added
they are :data:`em.profiles <s3dgraphy.em.profiles>` (``qualia_types()``,
``extractor_types()``, ``document_types()``). The epochs and groups of a
document are nodes of its graph (``em.graph.nodes(type="EpochNode")``,
``em.graph.chronology()``); the vocabularies are :data:`em.vocab
<s3dgraphy.em.vocab>`; the DTC is its node types and :func:`em.stamp
<s3dgraphy.em.stamp>`.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from typing import Any, Dict, List

__all__ = ["Catalogs", "CATALOGS"]

#: name → (file in ``JSON_config``, what it is). The order is the order of
#: :meth:`Catalogs.names` and of the reference's table.
CATALOGS: Dict[str, tuple] = {
    "node_types": ("node_registry.generated.json", "the node types, by class: node_type, parent class, description"),
    "edge_types": ("s3Dgraphy_connections_datamodel.json", "the edge types, by name: label, reverse, CIDOC mapping, allowed ends"),
    "qualia_types": ("em_qualia_types.json", "the core qualia (property types), by id, with category and subcategory"),
    "property_names": ("em_qualia_types.json", "property names in use that are not a quale"),
    "document_types": ("em_document_types.json", "the core document types, by id, with their category"),
    "extractor_types": ("em_extractor_types.json", "the core extractor types, by id, with their category"),
    "accuracy_levels": ("em_extractor_types.json", "the accuracy levels of an extractor"),
    "visual_rules": ("em_visual_rules.json", "the visual rules of the EM language: node styles, glyphs, document roles, instances"),
    "color_ramps": ("em_color_ramps.json", "the colour ramps (sequential, diverging, qualitative), by type and name"),
    "palette_icons": ("em_palette_icons.json", "the label prefixes of the paradata palette's image nodes"),
    "state_symbols": ("em_state_symbols.json", "the states the EM tools show: families, glyphs, meanings"),
    "alternative_cases": ("alternative_cases.json", "the alternatives of a 3D object: the cases every client passes"),
    "basemap_sources": ("em_basemap_sources.json", "the basemaps (imagery, terrain) a geographic view may show"),
    "translations": ("datamodel_translations.json", "the datamodel's labels in the project's languages"),
}


@lru_cache(maxsize=None)
def _file(name: str) -> Any:
    from ..datamodel import JSON_CONFIG
    return json.loads((JSON_CONFIG / name).read_text(encoding="utf-8"))


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


class Catalogs:
    """The datamodel's catalogues (``em.catalogs``): each a function that
    answers a copy, so the shared tables cannot be changed by a script.

    Example:
        >>> em.catalogs.node_types()["StratigraphicUnit"]["node_type"]
        'US'
        >>> em.catalogs.edge_types()["is_after"]["reverse"]["name"]
        'is_before'
        >>> rules = em.catalogs.visual_rules(); rules.clear()
        >>> "node_styles" in em.catalogs.visual_rules()      # a copy: nothing changed
        True
    """

    def names(self) -> List[str]:
        """The catalogues there are, in order."""
        return list(CATALOGS)

    def describe(self) -> Dict[str, Dict[str, str]]:
        """Each catalogue's file in ``JSON_config`` and what it holds."""
        return {k: {"file": f, "what": w} for k, (f, w) in CATALOGS.items()}

    def versions(self) -> Dict[str, Any]:
        """The datamodel's versions and digest (``s3dgraphy.datamodel.datamodel_fingerprint``)."""
        from ..datamodel import datamodel_fingerprint
        fp = datamodel_fingerprint()
        return _copy({"versions": fp.get("versions") or {}, "digest": fp.get("digest")})

    def node_types(self) -> Dict[str, Dict[str, Any]]:
        """The node types by CLASS (``StratigraphicUnit``, ``EpochNode``… — the
        68 pages of ``reference/types``): its ``node_type`` (``US``; None for
        an abstract class), its parent, its description
        (``node_registry.generated.json``)."""
        out: Dict[str, Dict[str, Any]] = {}
        for cls, v in (_file("node_registry.generated.json").get("node_types") or {}).items():
            if isinstance(v, dict):
                nt = v.get("node_type")
                out[str(cls)] = dict(_copy(v), node_type=None if nt in (None, "None") else nt)
        return out

    def edge_types(self) -> Dict[str, Dict[str, Any]]:
        """The edge types by name (``is_after``…): label, reverse, mapping,
        allowed connections (``s3Dgraphy_connections_datamodel.json``)."""
        return _copy(_file("s3Dgraphy_connections_datamodel.json").get("edge_types") or {})

    def qualia_types(self) -> Dict[str, Dict[str, Any]]:
        """The CORE qualia by id, each with ``category`` and ``subcategory``
        (``em_qualia_types.json``); with the packages': ``em.profiles.qualia_types()``."""
        from ..profiles.core import core_qualia
        return core_qualia()

    def property_names(self) -> Dict[str, Any]:
        """Property names in use that are not a quale (``em_qualia_types.json`` → ``property_names``)."""
        return _copy({k: v for k, v in (_file("em_qualia_types.json").get("property_names") or {}).items()
                      if not str(k).startswith("_")})

    def document_types(self) -> Dict[str, Dict[str, Any]]:
        """The CORE document types by id, each with its ``category`` (``em_document_types.json``)."""
        from ..profiles.core import core_document_types
        return core_document_types()

    def extractor_types(self) -> Dict[str, Dict[str, Any]]:
        """The CORE extractor types by id, each with its ``category`` (``em_extractor_types.json``)."""
        from ..profiles.core import core_extractor_types
        return core_extractor_types()

    def accuracy_levels(self) -> Any:
        """The accuracy levels an extractor declares (``em_extractor_types.json``)."""
        return _copy(_file("em_extractor_types.json").get("accuracy_levels"))

    def visual_rules(self) -> Dict[str, Any]:
        """The visual rules of the EM language (``em_visual_rules.json``): node
        styles, 2D glyphs, document roles and variants, instances, alternatives."""
        return _copy(_file("em_visual_rules.json"))

    def color_ramps(self) -> Dict[str, Any]:
        """``{type: {name: {name, description, colors}}}`` (``em_color_ramps.json``)."""
        return _copy(_file("em_color_ramps.json").get("ramps") or {})

    def palette_icons(self) -> Dict[str, Any]:
        """The label prefixes of the paradata image nodes and their detection
        order (``em_palette_icons.json``)."""
        return _copy(_file("em_palette_icons.json"))

    def state_symbols(self) -> Dict[str, Any]:
        """``{families, states: {"<family>.<state>": {family, glyph, label, meaning}}}`` (``em_state_symbols.json``)."""
        return _copy(_file("em_state_symbols.json"))

    def alternative_cases(self) -> List[Dict[str, Any]]:
        """The cases of the alternatives of a 3D object (``alternative_cases.json``):
        what ``s3dgraphy.resources.alternatives`` answers, which every client's copy passes."""
        return _copy(_file("alternative_cases.json").get("cases") or [])

    def basemap_sources(self) -> Dict[str, Any]:
        """The basemaps a geographic view may show (``em_basemap_sources.json``)."""
        return _copy(_file("em_basemap_sources.json"))

    def translations(self) -> Dict[str, Any]:
        """The datamodel's labels in the project's languages (``datamodel_translations.json``)."""
        return _copy(_file("datamodel_translations.json"))

    def __repr__(self) -> str:
        return f"<em.catalogs: {', '.join(CATALOGS)}>"
