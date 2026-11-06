"""Write tests/fixtures/landscape/ — the minimal Landscape Graph (MICRO-LANDSCAPE-
ONTOLOGIA, 6 Nov 2026). SYNTHETIC: invented names and dates, no data of any
real study.

Two files, as a landscape and a study kept elsewhere in the project tree:

* ``paesaggio.em.json`` — a container of kind ``landscape`` with two graphs:
  ``LG``, the Landscape Graph (a rural district — the canvas — with a UT and
  a −UT surveyed in it; two sites — the painting — in the district), and
  ``SCAVO1``, the excavation of the first site, with its own epochs; one
  periodization, «Orizzonti del paesaggio», whose horizon «Alto impero» reads
  the two sites together;
* ``sito2.em.json`` — ``SCAVO2``, the excavation of the second site, another
  file, with epochs of its own.

    PYTHONPATH=src .venv/bin/python scripts/make_landscape_fixture.py
"""
from pathlib import Path

from s3dgraphy import hdto, landscape as L, periodization as P
from s3dgraphy.container import Container, save_container_file
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "landscape"

SITE_1 = "Villa del Colle"
SITE_2 = "Fattoria del Guado"


def _excavation(gid, site, study, epochs, units):
    g = Graph(gid, name=study)
    hdto.declare_hdto(g, study={"name": study, "study_kind": "stratigraphic_excavation"},
                      place={"name": site})
    for eid, name, start, end in epochs:
        g.add_node(EpochNode(eid, name, start, end))
    for uid, eid in units:
        g.add_node(StratigraphicUnit(uid, uid))
        g.add_edge(f"{uid}_has_first_epoch_{eid}", uid, eid, "has_first_epoch")
    return g


def _dated(g, node_id, start, end):
    for side, value in (("start", start), ("end", end)):
        pid = f"{node_id}.t{side}"
        g.add_node(PropertyNode(pid, f"absolute_time_{side}", value=value,
                                property_type=f"absolute_time_{side}"))
        g.add_edge(f"{node_id}_has_property_{pid}", node_id, pid, "has_property")


def build():
    lg = Graph("LG", name="Paesaggio del Colle")
    fundus = L.add_district(lg, "Fundus della villa", district_kind="rural",
                            node_id="DIS1",
                            description="La porzione di campagna che si attribuisce alla villa.")
    _dated(lg, "DIS1", -50, 400)
    ut = L.add_topographic_unit(lg, "UT1", node_id="UT1",
                                description="Spargimento di laterizi e ceramica comune.")
    _dated(lg, "UT1", -30, 200)
    neg = L.add_negative_topographic_unit(lg, "UT0-1", node_id="UT0_1",
                                          description="Campo arato battuto in autunno, visibilità buona: nulla.")
    s1 = hdto.make_site_place(SITE_1)
    s2 = hdto.make_site_place(SITE_2)
    lg.add_node(s1)
    lg.add_node(s2)
    for member in (ut.node_id, neg.node_id, s1.node_id, s2.node_id):
        L.put_in_district(lg, member, fundus.node_id)

    scavo1 = _excavation("SCAVO1", SITE_1, "Scavo della Villa del Colle",
                         [("EP1", "Fase I", -100, 50), ("EP2", "Fase II", 50, 300)],
                         [("US1", "EP1"), ("US2", "EP2")])
    scavo2 = _excavation("SCAVO2", SITE_2, "Scavo della Fattoria del Guado",
                         [("EPA", "Periodo A", 0, 400)], [("US10", "EPA")])

    landscape = Container(graphs={"LG": lg, "SCAVO1": scavo1}, active_graph_id="LG",
                          header={"title": "Paesaggio del Colle (sintetico)",
                                  "kind": "landscape",
                                  "composition": [{"id": "SCAVO1"}, {"id": "SCAVO2"}]})
    pg = P.periodizations_of(landscape, create=True)
    P.add_periodization(pg, "Orizzonti del paesaggio", node_id="PER1", active=True)
    P.add_horizon(pg, "PER1", "Tarda repubblica", -150, -27, color="#c0392b", node_id="H1")
    P.add_horizon(pg, "PER1", "Alto impero", -27, 235, color="#e67e22", node_id="H2")
    P.add_horizon(pg, "PER1", "Tardo antico", 235, 568, color="#27ae60", node_id="H3")

    other = Container(graphs={"SCAVO2": scavo2}, active_graph_id="SCAVO2",
                      header={"title": "Fattoria del Guado (sintetico)", "kind": "site"})
    return landscape, other


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    landscape, other = build()
    save_container_file(landscape, str(OUT / "paesaggio.em.json"), bump=False)
    save_container_file(other, str(OUT / "sito2.em.json"), bump=False)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
