"""Two descriptive qualia of the stratigraphic unit, asked for by the DAI record.

iDAI.field's Layer carries `featureForm` (the shape in plan or section) and
`featureBorders` (how sharp the limits are). s3Dgraphy had no quale for either,
so the DAI template left them `none` + blocked on D7/D8. Qualia 1.6.2 adds
`feature_shape` and `boundary_distinctness` (proposed by Cowork for E.D., 28 Sep
2026). What is defended:

* both are registered once, as controlled vocabularies, where they were put
  (spatial / material) — a template's `vocabulary` verdict can name them;
* the mappings claim only what is evident: AAT for the shape, none for the
  boundary (said, not forgotten);
* each carries a rationale and an example, like the qualia shown by the picker;
* the version and the changelog say so;
* TRAD1 knows them in every language, as drafts (never validated by this commit).
"""

import json

import pytest

from s3dgraphy.tools import datamodel_i18n as t

NEW = {"feature_shape": "spatial", "boundary_distinctness": "material"}


@pytest.fixture(scope="module")
def qualia_doc():
    return t._load(t.QUALIA)


def _index(doc):
    out = {}
    for cat in doc["qualia_categories"]:
        for sid, sub in cat["subcategories"].items():
            for q in sub["qualia"]:
                out.setdefault(q["id"], []).append((sid, q))
    return out


@pytest.mark.parametrize("qid,subcategory", NEW.items())
def test_registered_once_where_it_was_put(qualia_doc, qid, subcategory):
    found = _index(qualia_doc).get(qid, [])
    assert [sid for sid, _ in found] == [subcategory]


@pytest.mark.parametrize("qid", NEW)
def test_a_controlled_vocabulary_with_why_and_a_case(qualia_doc, qid):
    (_, q), = _index(qualia_doc)[qid]
    assert q["data_type"] == "controlled_vocabulary"
    assert q["values"] and all(isinstance(v, str) for v in q["values"])
    for key in ("name", "description", "rationale", "example"):
        assert q.get(key), f"{qid} has no {key}"
    assert q["mappings"]["cidoc_crm"] == "E55_Type"


def test_mappings_claim_only_what_is_evident(qualia_doc):
    idx = _index(qualia_doc)
    shape = idx["feature_shape"][0][1]["mappings"]
    border = idx["boundary_distinctness"][0][1]["mappings"]
    assert shape["getty_aat"] == "300056273"       # shape (form attribute)
    assert "getty_aat" not in border                # none evident — and said:
    assert "AAT" in border["mapping_note"]


def test_the_version_and_the_changelog_say_so(qualia_doc):
    meta = qualia_doc["metadata"]
    # 1.6.5 dal 29 ott 2026 (le qualia dubbie, misurate); la voce 1.6.2
    # resta nella storia
    assert meta["version"] == "1.6.5"
    head = meta["changelog"].split(" v1.6.2:", 1)[1].split(" v1.6.1:")[0]
    assert "feature_shape" in head and "boundary_distinctness" in head
    assert "proposte da Cowork per E.D., 28 set 2026, dalla scheda DAI" in head


@pytest.mark.parametrize("qid", NEW)
def test_every_trad1_language_has_a_draft_label(qid):
    doc = json.loads(t.TRANSLATIONS.read_text(encoding="utf-8"))
    label = doc["qualia"][qid]["label"]
    for lang in t.LANGUAGES[1:]:
        assert label.get(lang), f"{qid} has no {lang} label"
        assert label[f"validated_{lang}"] is False
    assert t.qualia_label(qid, "de")
    assert t.check() == 0
