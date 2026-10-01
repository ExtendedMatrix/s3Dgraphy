"""VLONG dev28, parte B3 — il modo d'accesso lo timbra il relay.

E.D. (1 ott 2026, decisione 13): le firme di un'op che passa dal relay del
server portano il modo che il relay legge dal token di chi la spedisce, come
l'autore; il client non lo dichiara più. Senza relay resta quello dell'identità
locale: ``orcid``, ``node_password`` o, dalla dev28, ``declared``.
"""

import pytest

from s3dgraphy import api
from s3dgraphy.crdt import (AUTH_CORRECTED, AUTH_KEPT, AUTH_STAMPED,
                            apply_op_to_section, make_op, stamp_auth)
from s3dgraphy.editorial import AUTH_MODES, normalize_auth

ORCID = "0000-0002-1825-0097"
TS = "2026-11-01T09:00:00Z"
FIELD = {"mode": "node_password", "attested_by": "fcn-prova"}


def _add(**extra):
    return make_op("add_node", ts=TS, author=ORCID,
                   node={"id": "us1", "node_type": "US", "name": "US 1",
                         "data": {"lang": "it"}}, **extra)


def test_declared_is_a_mode_and_is_attested_by_nobody():
    assert "declared" in AUTH_MODES
    assert normalize_auth("declared") == {"mode": "declared"}
    with pytest.raises(ValueError, match="attested by nobody"):
        normalize_auth({"mode": "declared", "attested_by": "fcn"})


def test_a_client_declaring_orcid_from_a_node_password_token_is_corrected():
    op, outcome = stamp_auth(_add(auth="orcid"), FIELD)
    assert outcome == AUTH_CORRECTED
    assert op["auth"] == FIELD
    section = {"nodes": [], "edges": []}
    assert apply_op_to_section(section, op).applied
    data = section["nodes"][0]["data"]
    assert data["created_auth"] == FIELD and data["modified_auth"] == FIELD


def test_an_op_without_a_mode_takes_the_token_s():
    op, outcome = stamp_auth(_add(), {"mode": "orcid"})
    assert outcome == AUTH_STAMPED and op["auth"] == {"mode": "orcid"}


def test_saying_what_the_token_says_is_kept():
    op, outcome = stamp_auth(_add(auth=dict(FIELD)), FIELD)
    assert outcome == AUTH_KEPT and op["auth"] == FIELD


def test_the_op_given_is_not_touched():
    original = _add(auth="orcid")
    stamp_auth(original, FIELD)
    assert original["auth"] == "orcid"


def test_every_place_an_op_can_carry_a_mode_is_overwritten():
    # a payload bringing its own *_auth
    op = make_op("add_node", ts=TS, author=ORCID,
                 node={"id": "us2", "node_type": "US", "name": "US 2",
                       "data": {"lang": "it", "validated_auth": {"mode": "orcid"},
                                "created_auth": {"mode": "orcid"}}})
    out, outcome = stamp_auth(op, FIELD)
    assert outcome == AUTH_CORRECTED
    assert out["node"]["data"]["validated_auth"] == FIELD
    assert out["node"]["data"]["created_auth"] == FIELD
    # a signature written field by field
    sign = make_op("update_field", ts=TS, author=ORCID, node_id="us1",
                   field="data.validated_auth", value={"mode": "orcid"})
    out, outcome = stamp_auth(sign, FIELD)
    assert outcome == AUTH_CORRECTED and out["value"] == FIELD and out["auth"] == FIELD
    # any other field is left as it is
    rename = make_op("update_field", ts=TS, author=ORCID, node_id="us1",
                     field="name", value="US 1 bis")
    out, outcome = stamp_auth(rename, FIELD)
    assert outcome == AUTH_STAMPED and out["value"] == "US 1 bis"


def test_a_token_that_says_nothing_removes_the_declaration():
    out, outcome = stamp_auth(_add(auth="orcid"), None)
    assert outcome == AUTH_CORRECTED and "auth" not in out
    out, outcome = stamp_auth(_add(), None)
    assert outcome == AUTH_STAMPED and "auth" not in out


def test_an_invalid_declaration_is_corrected_not_refused():
    out, outcome = stamp_auth(_add(auth="password"), {"mode": "orcid"})
    assert outcome == AUTH_CORRECTED and out["auth"] == {"mode": "orcid"}
    assert apply_op_to_section({"nodes": [], "edges": []}, out).applied


def test_THE_COUNTEREXAMPLE_a_token_mode_the_relay_cannot_read():
    with pytest.raises(ValueError):
        stamp_auth(_add(), {"mode": "password"})


def test_without_a_relay_the_local_identity_signs_declared():
    section = {"nodes": [], "edges": []}
    assert apply_op_to_section(section, _add(auth="declared")).applied
    assert section["nodes"][0]["data"]["created_auth"] == {"mode": "declared"}


def test_the_api_door():
    op, outcome = api.stamp_auth(_add(auth="orcid"), FIELD)
    assert outcome == "corrected" and op["auth"] == FIELD
