"""SF, RSF, VSF as E.D. defined them (MICRO special find e fine dell'unità,
part 1, 23 Oct 2026).

* SF — movable, found erratic or in a layer and taken out during the
  excavation, defined IN POSITIVE (documented where it was found); how it lay
  (in situ, redeposited, fallen in position) is an attribute, not a class.
* RSF — «Repositioned Special Find»: fixed, immovable, intentionally put back
  into a stable unit or a new functional placement; reuse is one case.
* VSF — two roles: the VSF that holds the fragments, the VSF that completes
  what was restored.

The identifiers stay: class ``ReusedSpecialFind``, URIs
``em:ReusedSpecialFind`` and ``em:DisplacedSpecialFind``.
"""

import json
from pathlib import Path

from s3dgraphy.nodes.stratigraphic_node import (ReusedSpecialFind,
                                                SpecialFindUnit,
                                                VirtualSpecialFindUnit)

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"
LANGS = ["en", "it", "el", "he", "es", "pl", "ro", "fr", "de"]


def _subtypes():
    dm = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    return dm["stratigraphic_nodes"]["StratigraphicNode"]["subtypes"]


def test_the_sf_is_defined_in_positive_and_movable():
    sf = _subtypes()["SF"]
    # the old negative definition is quoted only to be refused
    assert "whose ORIGINAL position is unknown" not in sf["description"]
    assert "not an object «whose original position is unknown»" in sf["description"]
    assert "WHERE IT WAS FOUND" in sf["description"]
    assert "MOVABLE" in sf["description"]
    # how it lay is an attribute, and a collapse in position is an SF
    assert "ATTRIBUTE" in sf["description"]
    assert "collapse found in position is an SF" in sf["description"]
    # REPOSITIONED no longer qualifies an SF
    assert "REPOSITIONED no longer qualifies an SF" in sf["scope_note"]
    # the URI is historical and kept
    assert sf["em_extension"]["uri"] == "em:DisplacedSpecialFind"


def test_the_rsf_is_repositioned_immovable_and_keeps_its_identifiers():
    rsf = _subtypes()["RSF"]
    assert rsf["label"] == "Repositioned Special Find"
    assert rsf["class"] == "ReusedSpecialFind"
    assert rsf["em_extension"]["uri"] == "em:ReusedSpecialFind"
    assert "IMMOVABLE" in rsf["description"]
    assert "INTENTIONALLY" in rsf["description"]
    assert "street furniture" in rsf["description"]
    assert "anastylosis" in rsf["description"]
    assert ReusedSpecialFind("r", "RSF1").label == "Repositioned Special Find"


def test_the_vsf_has_two_roles_and_the_boolean():
    vsf = _subtypes()["VSF"]["description"]
    assert "HOLDS the fragments" in vsf
    assert "COMPLETES what was restored" in vsf
    assert "boolean" in vsf


def test_the_python_classes_say_the_same():
    assert "where it was found" in SpecialFindUnit("s", "SF1").detailed_description
    assert "completes what was restored" in VirtualSpecialFindUnit("v", "VSF1").detailed_description


def test_the_new_texts_are_in_the_nine_languages():
    tr = json.loads((CONFIG / "datamodel_translations.json").read_text(encoding="utf-8"))
    sub = _subtypes()
    for cls, abbr in (("SpecialFindUnit", "SF"), ("VirtualSpecialFindUnit", "VSF"),
                      ("ReusedSpecialFind", "RSF")):
        entry = tr["entries"][cls]["description"]
        assert entry["en"] == sub[abbr]["description"]
        assert all(entry.get(lang) for lang in LANGS), cls
    label = tr["entries"]["ReusedSpecialFind"]["label"]
    assert label["en"] == "Repositioned Special Find"
    assert label["it"] == "Reperto speciale riposizionato"


def test_em_ttl_says_it_too():
    ttl = (CONFIG / "em.ttl").read_text(encoding="utf-8")
    assert 'rdfs:label "Repositioned Special Find (RSF)"@en' in ttl
    assert 'rdfs:label "Special Find (SF)"@en' in ttl
    assert "em:DisplacedSpecialFind" in ttl and "em:ReusedSpecialFind" in ttl
