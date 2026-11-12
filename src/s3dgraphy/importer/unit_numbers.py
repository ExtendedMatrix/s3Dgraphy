"""THE NUMBER OF A UNIT is read from its NAME (15 Nov 2026; E.D., 12 Nov 2026).

In EM the identifier of a unit is its ``name`` (``P1_is_identified_by``). The
number is NOT copied into another key: no ``data.us``, in the data or in the
datamodel. The name the pyArchInit importer builds from its
``node_name_template`` (``{area}.{settore}.{unita_tipo}{us}`` → ``1.1.US1``,
``1.US2``, ``1.USM12``, ``1.SF300``) already holds code and number, and the
area in front makes it unique (in pyArchInit the key is site + area + number).
No room is migrated: order and the «no number» sign are display only.

ONE RULE, used by the importer to CLASSIFY a row (from its columns: the number
is ``us``, the code ``unita_tipo``) and by any reader that has only the name
(:func:`number_of_name`, a pure reader):

* the code names a stratigraphic unit of the datamodel (its subtypes, the voids,
  and the genre codes USM/USR/USS and their localised forms) and the number is
  a unit number → ``numbered``;
* the code names something that is not a unit (pyArchInit's paradata codes:
  DOC, Combinar, Extractor, property; CON for continuity) → ``not_unit``, with
  the class it names: the unit is not invented;
* anything else (an unknown code, no code, a number that is not one) →
  ``ambiguous``, with the reason. Not guessed: said.

The importer writes nothing on the node from this: it counts the verdicts in
its ``numbering_report`` and says the non-units and the ambiguous rows in its
warnings.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

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
