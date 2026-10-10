"""
StudyNode — Study node (HDT-O HC9).

Represents an HC9 Study (HDT-O, ECHOES D7.1): a scholarly activity — research,
analysis or documentation, in any SSH / natural / exact-science domain — about
a Heritage Entity (HC1), explicating a disciplinary focus and the part of the
entity investigated. A study always results in documentary outputs that
contribute to the content of an HDT; in EM terms a study heads an EM
proposition set (HC16 / em:EMGraph).

Canonical HDT-O framing used by s3Dgraphy:

    Project (HC13) ─includes(crm:P9)→ Study (HC9)
    Study   (HC9)  ─took_place_at(crm:P7)→ LocationNodeGroup (E53, the site)
    Study   (HC9)  ─was_about(HP23)→ HeritageEntity (HC1), only if recognised
    Study   (HC9)  ─produced(HP25)→ GraphNode (HC16 / em:EMGraph)

A stratigraphic trench is a study (E.D., 10 Oct 2026): ``study_kind``
``stratigraphic_excavation`` makes it also a crmarchaeo:A9 Archaeological
Excavation in RDF. ``code`` is the short name of the study (GT16), given by the
source or by the user and never derived; the label prefix reads it. The chain is
written and read by :mod:`s3dgraphy.hdto`.

HDT-O view: gated out of the stratigrapher palette (like HDTNode / GraphNode /
HeritageEntityNode); authored in HDT-aware tooling and projected to RDF.
"""
from .base_node import Node


class StudyNode(Node):
    """
    HC9 Study (HDT-O / ECHOES D7.1).

    Attributes:
        disciplinary_focus (str, optional): the disciplinary aspect under which
            the study investigated the entity (HDT-O HP24 → crm:E55 Type).
        project_iri (str, optional): IRI of the HC13 Project this study is part
            of, when authored standalone.
        study_kind (str, optional): one of :data:`STUDY_KINDS`; absent when
            nobody said.
        code (str, optional): the short name of the study (GT16, TM16).
    """
    node_type = "study"

    #: The minimal vocabulary of ``data.study_kind`` (node datamodel 1.6.28).
    STUDY_KINDS = ("stratigraphic_excavation", "survey", "documentation", "other")

    def __init__(self, node_id, name="Unnamed Study", description="",
                 disciplinary_focus=None, project_iri=None,
                 study_kind=None, code=None):
        super().__init__(node_id=node_id, name=name, description=description)
        if study_kind is not None and study_kind not in self.STUDY_KINDS:
            raise ValueError(
                f"StudyNode.study_kind must be one of {self.STUDY_KINDS}, "
                f"got {study_kind!r}")
        self.data = {
            "disciplinary_focus": disciplinary_focus,
            "project_iri": project_iri,
        }
        # Only when said: a study nobody classified has no kind and no code.
        if study_kind is not None:
            self.data["study_kind"] = study_kind
        if code:
            self.data["code"] = code

    def to_dict(self):
        return {
            "id": self.node_id,
            "type": self.node_type,
            "name": self.name,
            "description": self.description,
            "data": self.data,
        }
