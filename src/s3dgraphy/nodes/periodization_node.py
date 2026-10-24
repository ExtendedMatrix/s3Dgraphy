"""
PeriodizationNode and HorizonNode — the shared measures of time of a project.

E.D., 24 Oct 2026: an HORIZON is a node of the multigraph, at the level of the
CONTAINER (not of one graph), so it works with the mechanisms that already
exist. A project may hold SEVERAL sets of horizons (periodizations) and the user
chooses which one to read the graphs with. «Inside» includes the overlap: a unit
is in an horizon when its interval intersects it. The colours are layout, but
they travel with the graph in the em.json.

Epochs are creations, horizons are shared measures (decisioni/landscape-graph-
semantica §5): each graph has its own epochs, local by construction; the
horizons stand above every graph of the container and are compared with the
ABSOLUTE intervals :meth:`Graph.chronology` computes.

    Periodization (E32 Authority Document)
        ↑ is_in_periodization (P71i is listed in)
    Horizon (crmgeo:SP10 Declarative Time-Span)

Both live in the container member ``graphs.periodizations``
(``data.em_collection: "Periodizations"``), read and written by
:mod:`s3dgraphy.periodization`.
"""
from .base_node import Node


class PeriodizationNode(Node):
    """A set of horizons — one way of cutting time into named spans.

    Attributes:
        description (str): what the periodization is for, whose it is.
        source (str, optional): where it comes from (``"EM-tools CronoFilter"``,
            a PeriodO collection, a publication).
    """
    node_type = "periodization"

    def __init__(self, node_id, name="Periodization", description="",
                 source=None):
        super().__init__(node_id=node_id, name=name, description=description)
        self.data = {}
        if source:
            self.data["source"] = source


class HorizonNode(Node):
    """One span of a periodization: label, start, end, colour, order.

    ``start_time`` / ``end_time`` are years (negative = BC), like an epoch's.
    ``order`` is the place in its periodization (0 first); ``enabled`` says
    whether the horizon is in use (EM-tools' CronoFilter flag, same name so the
    one em.json is read the same way by both).
    """
    node_type = "horizon"

    def __init__(self, node_id, name="Horizon", start_time=None, end_time=None,
                 color="#888888", order=0, enabled=True, description=""):
        super().__init__(node_id=node_id, name=name, description=description)
        self.start_time = float(start_time) if start_time is not None else None
        self.end_time = float(end_time) if end_time is not None else None
        self.color = color
        self.data = {"order": int(order or 0), "enabled": bool(enabled)}

    @property
    def order(self):
        return int(self.data.get("order") or 0)

    @property
    def enabled(self):
        return bool(self.data.get("enabled", True))
