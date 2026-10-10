"""``add_group`` must not throw away what the constructor put in
``attributes`` (#25, pyArchInit).

The same pattern as the two places in ``graph_projector`` fixed on 9
October: ``node.attributes = {...}`` replaces the dict the constructor
filled, instead of updating it. On an ``ActivityNodeGroup`` the only key
the constructor sets today is ``y_pos``, and it is not serialised, so
**nothing observable breaks right now** — the GroupStore round trip comes
out identical either way (measured). What breaks is the next attribute
the class gains: ``LocationNodeGroup`` already carries ``kind`` and
``propagation`` from its constructor, and a group built that way here
would lose them in silence.

So this pins the invariant rather than a symptom: whatever the
constructor puts in ``attributes`` is still there after ``add_group``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from s3dgraphy.nodes.group_node import ActivityNodeGroup
from s3dgraphy.sync.group_store import GroupStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "x.sqlite"
    db.write_bytes(b"")
    return GroupStore(db_path=db, sito="SitoDiProva")


def test_add_group_keeps_what_the_constructor_put_there(store, monkeypatch):
    """Si guarda il nodo **come ``add_group`` lo costruisce**, prima che
    finisca nel file: dopo il giro su disco il difetto non si vede più,
    perché a rileggere è il costruttore a rimettere la chiave. È l'unico
    punto dove l'invariante è osservabile — ed è anche l'unico che conta,
    perché è quello che un chiamante futuro si troverà in mano."""
    dal_costruttore = set(
        ActivityNodeGroup(node_id="x", name="x").attributes)
    assert dal_costruttore, "il costruttore non mette niente: test inutile"

    visti = []
    originale = type(store).add_node

    def spia(self, node):
        visti.append(dict(getattr(node, "attributes", None) or {}))
        return originale(self, node)

    monkeypatch.setattr(type(store), "add_node", spia)
    store.add_group(name="Attività", group_kind="adhoc", member_us_uuids=[])

    assert visti, "add_group non ha aggiunto nessun nodo"
    mancanti = dal_costruttore - set(visti[0])
    assert not mancanti, (
        "add_group ha buttato via quello che il costruttore aveva messo: %s"
        % sorted(mancanti))


def test_add_group_still_writes_its_own_keys(store):
    """L'irrigidimento non deve togliere niente a quello che scriveva."""
    group_uuid = store.add_group(name="Attività", group_kind="adhoc",
                                 description="una nota",
                                 member_us_uuids=["u1", "u2"])

    gruppi = store.list_groups()
    assert len(gruppi) == 1
    g = gruppi[0]
    assert g["group_uuid"] == group_uuid
    assert g["name"] == "Attività"
    assert g["group_kind"] == "adhoc"
    assert g["description"] == "una nota"
    assert g["member_us_uuids"] == ["u1", "u2"]
