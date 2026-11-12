"""THE NUMBER OF A UNIT that came in from another tool (15 Nov 2026).

An importer that does not mint the unit's id leaves it without a number a
reader can find: the pyArchInit importer names a unit by its
``node_name_template`` (``{area}.{settore}.{unita_tipo}{us}`` → ``1.1.US1``,
``1.USM12``, ``1.SF300``) and gives it the row's UUID as id. Measured on the
StratiField test room: 45 real units with nothing a «go to US…» could find.

WHERE THE NUMBER GOES. The node datamodel has no element for a unit's number:
the identifier is the ``name`` (``P1_is_identified_by``). The one key the
library already reads it from is ``attributes['us']`` (em.json ``data.us``),
the pyArchInit column itself: the sync projector writes it, the ``rapporti``
writer reads it before falling back to the name. The importers write THAT key,
beside ``unita_tipo`` (the code the number goes with: US, USM, SF, USVs…), and
leave the name as it came.

ONE RULE, used by the importer (from the row: the number is the ``us`` column,
the code ``unita_tipo``) and by anything that has only the name — a room
imported before this, to be put in order (:func:`number_of_name`):

* the code names a stratigraphic unit of the datamodel (its subtypes, the voids,
  and the genre codes USM/USR/USS and their localised forms) and the number is
  a unit number → ``numbered``;
* the code names something that is not a unit (pyArchInit's paradata codes:
  DOC, Combinar, Extractor, property; CON for continuity) → ``not_unit``, with
  the class it names: no number is given, the unit is not invented;
* anything else (an unknown code, no code, a number that is not one) →
  ``ambiguous``, with the reason. Not guessed: said.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

#: The key a unit's number is written under (em.json ``data.us``), and the key
#: of the code it goes with. The same keys sync/graph_projector.py writes.
NUMBER_KEY = "us"
CODE_KEY = "unita_tipo"

#: pyArchInit's codes for what is NOT a unit: the paradata rows of us_table
#: (the same table as sync/yed_import_pipeline._CLASSIFIED_KIND_TO_UNITA_TIPO:
#: DOC, Combinar, Extractor, property) and CON, the continuity row of the demo
#: database. Code → the class it names.
NOT_UNIT_CODES: Dict[str, str] = {
    "DOC": "DocumentNode",
    "Combinar": "CombinerNode",
    "Extractor": "ExtractorNode",
    "property": "PropertyNode",
    "CON": "ContinuityNode",
}

#: What a unit number is (the rule StratiField's tools.unit_number applies):
#: it begins with a digit, no spaces — «3018», «12a», «1001.2», «3014-bis».
UNIT_NUMBER = re.compile(r"\d+(?:[./-]?[0-9A-Za-z]+)*")

#: A name's LAST dot-separated component as code + number: ``US1``, ``USM-12``,
#: ``SF 300``, ``USVs102``. What stands before it (``1.``, ``1.1.``) is the
#: location the template put in front (area, settore).
_CODE_NUMBER = re.compile(r"^(?P<code>[^\W\d_]+)[\s_-]*(?P<number>\d[0-9A-Za-z]*)$",
                          re.UNICODE)


def _datamodel_path() -> Path:
    return (Path(__file__).resolve().parent.parent / "JSON_config"
            / "s3Dgraphy_node_datamodel.json")


@lru_cache(maxsize=1)
def unit_codes() -> Dict[str, str]:
    """Code → class, for every code that names a stratigraphic UNIT: the
    concrete subtypes of StratigraphicNode in the datamodel (not ContinuityNode
    nor StratigraphicEventNode, which are not units), and the genre codes
    (USM, USR, USS, WSU…), which are a US with a kind."""
    from ..nodes.stratigraphic_node import KIND_OF_CODE

    data = json.loads(_datamodel_path().read_text(encoding="utf-8"))
    strat = (((data.get("stratigraphic_nodes") or {}).get("StratigraphicNode")
              or {}).get("subtypes") or {})
    out = {key: str(v.get("class") or "") for key, v in strat.items()
           if isinstance(v, dict) and v.get("class")
           and not str(v["class"]).endswith("Node")}
    for code in KIND_OF_CODE:
        out.setdefault(code, "StratigraphicUnit")
    return out


def _known(code: str, table: Dict[str, str]) -> Optional[str]:
    """The code as the table spells it: exact, else the ONE that differs only
    by case (``usm`` → ``USM``); None when none or more than one."""
    if code in table:
        return code
    low = [k for k in table if k.lower() == code.lower()]
    return low[0] if len(low) == 1 else None


def number_of(code: Any, number: Any) -> Dict[str, Any]:
    """The verdict for a code and a number (a pyArchInit row's ``unita_tipo``
    and ``us``): ``{"status": "numbered", "number", "code"}``,
    ``{"status": "not_unit", "code", "class"}`` or
    ``{"status": "ambiguous", "reason"}``."""
    code = str(code if code is not None else "").strip()
    number = str(number if number is not None else "").strip()
    if not code:
        return {"status": "ambiguous", "reason": "no unit code"}
    other = _known(code, NOT_UNIT_CODES)
    if other is not None:
        return {"status": "not_unit", "code": other,
                "class": NOT_UNIT_CODES[other]}
    unit = _known(code, unit_codes())
    if unit is None:
        return {"status": "ambiguous",
                "reason": f"'{code}' is not a code of the datamodel"}
    if not UNIT_NUMBER.fullmatch(number):
        return {"status": "ambiguous",
                "reason": f"'{number}' is not a unit number"}
    return {"status": "numbered", "number": number, "code": unit}


def number_of_name(name: Any) -> Dict[str, Any]:
    """The verdict for a NAME alone (``1.1.US1``, ``1.USM12``, ``1.SF300``):
    the last dot-separated component read as code + number, the components
    before it left as the location they are. Same answers as :func:`number_of`,
    with ``"ambiguous"`` for a name that does not end in a code and a number."""
    text = str(name if name is not None else "").strip()
    last = text.rsplit(".", 1)[-1].strip()
    m = _CODE_NUMBER.match(last)
    if not m:
        return {"status": "ambiguous",
                "reason": f"'{text}' does not end in a code and a number"}
    return number_of(m.group("code"), m.group("number"))


def write_number(node: Any, verdict: Dict[str, Any]) -> bool:
    """Put a ``numbered`` verdict on the node (``attributes``: em.json
    ``data.us`` and ``data.unita_tipo``); the name is not touched. False, and
    nothing written, for any other verdict."""
    if verdict.get("status") != "numbered":
        return False
    attrs = getattr(node, "attributes", None)
    if not isinstance(attrs, dict):
        attrs = {}
        node.attributes = attrs
    attrs[NUMBER_KEY] = verdict["number"]
    attrs[CODE_KEY] = verdict["code"]
    return True


def new_report() -> Dict[str, Any]:
    """The numbering part of an import report."""
    return {"numbered": 0, "not_unit": [], "ambiguous": []}


def record(report: Dict[str, Any], label: str, verdict: Dict[str, Any]) -> None:
    status = verdict.get("status")
    if status == "numbered":
        report["numbered"] += 1
    elif status == "not_unit":
        report["not_unit"].append({"name": label, "code": verdict["code"],
                                   "class": verdict["class"]})
    else:
        report["ambiguous"].append({"name": label,
                                    "reason": verdict.get("reason", "")})


def plan_for_document(document: Dict[str, Any],
                      stratigraphic_types: Iterable[str]) -> Dict[str, Any]:
    """A DRY RUN over an em.json container (a room already imported): for every
    stratigraphic node with no number (no ``data.us``, an id not minted as
    ``US<n>``), the verdict of its name. Writes nothing; returns
    ``{"plan": [{graph, node, name, number, code}], "report": …}`` — the plan
    is what an ``update_field`` op per unit (``data.us``, ``data.unita_tipo``)
    would write, if E.D. decides to."""
    kinds = set(stratigraphic_types)
    plan, report = [], new_report()
    for gid, section in (document.get("graphs") or {}).items():
        for node in section.get("nodes") or []:
            if str(node.get("node_type") or "") not in kinds:
                continue
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            if data.get("removed") or str(data.get(NUMBER_KEY) or "").strip():
                continue
            nid = str(node.get("id") or "")
            if nid.startswith("US") and UNIT_NUMBER.fullmatch(nid[2:]):
                continue
            name = str(node.get("name") or "")
            if name.upper().startswith("US ") and UNIT_NUMBER.fullmatch(
                    name[3:].split(" — ")[0].strip()):
                continue
            verdict = number_of_name(name)
            record(report, name, verdict)
            if verdict["status"] == "numbered":
                plan.append({"graph": gid, "node": nid, "name": name,
                             "number": verdict["number"], "code": verdict["code"]})
    return {"plan": plan, "report": report}
