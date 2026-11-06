"""The units of the Landscape Graph — MICRO-LANDSCAPE-ONTOLOGIA (6 Nov 2026).

«The Extended Matrix is the graph of what touches. The Landscape Graph is the
graph of what does not touch, and absolute time is the only measure those
things have in common» (brain ``decisioni/landscape-graph-semantica``, D-LG2).

One observed and one interpreted for each scale, with the same temporal
grammar as the units of the EM (D-LG4)::

    scale        observed              interpreted
    contact      US, USN, SF, RSF      USV/s, USV/n, VSF, serVSF
    distance     UT, UT0 (−UT)         SV, district

The SITE is not here: it is a place, the ``LocationNodeGroup`` of level
``sito`` the studies took place at (nodes 1.6.39), and the VIRTUAL SITE (SV) is
the same node with ``data.virtual`` (``em:VirtualSite``). What is here is what
the datamodel did not have:

* :class:`TopographicUnitNode` (UT) — what a survey finds on the ground: a
  scatter of sherds, a structure cropping out. Observed, in secondary
  deposition, so not a stratigraphic unit (no physical relation).
* :class:`NegativeTopographicUnitNode` (UT0, displayed «−UT») — the area
  walked where nothing was found, with the conditions of the observation. It
  makes silence informative: without it an empty district cannot tell «there
  was nothing» from «nobody looked».
* :class:`DistrictNode` — the portion of territory that acts as a TRAY for
  what stands on it («funge da vassoio», 2017): urban (the Forum of Pompeii) or
  rural (a villa rustica with its fundus). Declared: its border is an
  interpretation of pertinence, argued by its paradata. A UNIT, not a group:
  it has a geometry, a time and paradata.

All three are spatiotemporal entities (node datamodel ``spatiotemporal_
entities``): start/end, epochs, ``is_after`` / ``has_same_time``, paradata.
They share no physical relation with anything: two things that cannot touch
are two graphs, and between the units of a landscape only the sequence, the
contemporaneity, the instance chain and pertinence (``is_in_district``) pass.
"""
from typing import Any, Dict, Optional

from .base_node import Node

#: The two kinds of district (E.D., roadmap §14, 24 Oct 2026).
DISTRICT_KINDS = ("urban", "rural")


class LandscapeUnitNode(Node):
    """The common parent of the units of the Landscape Graph — what an edge
    of the datamodel names to admit all of them. Not a type of its own: it
    declares no ``node_type``, so it is never registered nor serialised."""

    def __init__(self, node_id: str, name: str = "", description: str = "",
                 data: Optional[Dict[str, Any]] = None):
        super().__init__(node_id=node_id, name=name, description=description)
        self.data = dict(data or {})

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.node_id, "type": self.node_type, "name": self.name,
                "description": self.description, "data": dict(self.data)}


class TopographicUnitNode(LandscapeUnitNode):
    """UT — a topographic unit: what a survey observes on the ground."""
    node_type = "UT"


class NegativeTopographicUnitNode(LandscapeUnitNode):
    """UT0 (−UT) — an area surveyed where nothing was found. The conclusion
    drawn from it («no settlement here») belongs to its paradata, not to the
    unit."""
    node_type = "UT0"


class DistrictNode(LandscapeUnitNode):
    """A district — the declared portion of territory that holds sites,
    virtual sites and topographic units. ``data.district_kind``: ``urban`` or
    ``rural`` (absent = not said)."""
    node_type = "district"

    def __init__(self, node_id: str, name: str = "", description: str = "",
                 district_kind: Optional[str] = None,
                 data: Optional[Dict[str, Any]] = None):
        super().__init__(node_id=node_id, name=name, description=description,
                         data=data)
        if district_kind is not None:
            if district_kind not in DISTRICT_KINDS:
                raise ValueError(f"district_kind must be one of {DISTRICT_KINDS}, "
                                 f"got {district_kind!r}")
            self.data["district_kind"] = district_kind

    @property
    def district_kind(self) -> Optional[str]:
        return self.data.get("district_kind")
