"""The PRESENTATION section of an em.json: ways of looking at the graphs.

MICRO-T-COLORI-NEL-FILE (E.D., 18 Nov 2026). The colour schemes of the visual
manager — EM Tools' and EMStudio's «Colori · Proprietà», until today only in a
``.emc`` beside the file — may live INSIDE the em.json, in a section of its own,
apart from the graphs: several schemes, each with a name, and for each graph the
one in use. They are not knowledge, they are a way of looking at it: they touch
no node and no edge, the content digest of the work does not see them
(:func:`s3dgraphy.container.content_digest`), and a reader that does not know
the section ignores it (em.json §3.1)::

    "presentation": {
      "colour_schemes": {
        "<name>": {"metadata": {"property_name": "material", "created": "…",
                                "description": "…",
                                "value_codes": {"white rock": "<uri>"}},
                   "color_mapping": {"white rock": [r, g, b, 1.0], …}}
      },
      "active_colour_scheme": {"<graph id>": "<name>"}
    }

**A scheme IS a .emc** (:mod:`s3dgraphy.color_schemes`): the same two keys, the
same linear floats, the same two special values (``empty property <p> node``,
``no property <p> node``). Taking it out into a ``.emc`` and back is copying a
document, nothing is converted — so it comes back as it went.

**The code of the value** (decision 5). A value of a controlled vocabulary has
an identity, the URI of its term, beside the label written in one language.
``metadata.value_codes`` maps the label a colour is written under to that code;
a unit whose value carries a code takes the colour of the entry with the same
code, whatever its label says (a scheme made on Italian labels colours the
English ones), and falls back to the text otherwise
(:func:`colours_for_values`). Where a node keeps the code of its value is
decided by MICRO-U; this module takes it as it is handed.

Written deterministically: every object with its keys sorted (the container is
saved with ``sort_keys``; :func:`canonical` for the rest).
"""
from __future__ import annotations

import copy
import json
import os
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .color_schemes import emc_read

#: the top-level key of the container
PRESENTATION_KEY = "presentation"
#: the named colour schemes: ``{name: .emc document}``
SCHEMES_KEY = "colour_schemes"
#: which scheme each graph uses: ``{graph id: name}``
ACTIVE_KEY = "active_colour_scheme"
#: in a scheme's ``metadata``: ``{label: code of the term}``
VALUE_CODES_KEY = "value_codes"


def canonical(value: Any) -> Any:
    """A copy with every object's keys sorted (lists keep their order)."""
    if isinstance(value, dict):
        return {k: canonical(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def empty() -> Dict[str, Any]:
    return {SCHEMES_KEY: {}, ACTIVE_KEY: {}}


def _scheme_problem(doc: Any) -> Optional[str]:
    """Why ``doc`` is not a scheme (None: it is one)."""
    if not isinstance(doc, dict):
        return "not an object"
    try:
        emc_read(doc)
    except (ValueError, TypeError) as exc:
        return str(exc)
    for v, c in doc["color_mapping"].items():
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in c):
            return f"not a colour for {v!r}: {c!r}"
    codes = (doc.get("metadata") or {}).get(VALUE_CODES_KEY)
    if codes is not None and not (isinstance(codes, dict)
                                  and all(isinstance(k, str) and isinstance(v, str)
                                          for k, v in codes.items())):
        return f"metadata.{VALUE_CODES_KEY} is not a map of texts"
    return None


def read_presentation(doc: Any) -> Tuple[Dict[str, Any], List[str]]:
    """The section of a container document, normalised: ``({colour_schemes,
    active_colour_scheme}, warnings)``.

    A file without it gives an empty presentation and no warning. What cannot be
    read is left out and said: a scheme that is not a .emc, an active scheme
    that names no scheme of the file."""
    out = empty()
    warnings: List[str] = []
    raw = doc.get(PRESENTATION_KEY) if isinstance(doc, dict) else None
    if raw is None:
        return out, warnings
    if not isinstance(raw, dict):
        return out, [f"{PRESENTATION_KEY}: not an object; ignored"]
    schemes = raw.get(SCHEMES_KEY) or {}
    if not isinstance(schemes, dict):
        warnings.append(f"{PRESENTATION_KEY}.{SCHEMES_KEY}: not an object; ignored")
        schemes = {}
    for name, sch in schemes.items():
        why = _scheme_problem(sch)
        if why or not str(name).strip():
            warnings.append(f"colour scheme {name!r} not readable ({why or 'no name'}); left out")
            continue
        out[SCHEMES_KEY][str(name)] = canonical(copy.deepcopy(sch))
    active = raw.get(ACTIVE_KEY) or {}
    if not isinstance(active, dict):
        warnings.append(f"{PRESENTATION_KEY}.{ACTIVE_KEY}: not an object; ignored")
        active = {}
    for gid, name in active.items():
        if not isinstance(name, str) or name not in out[SCHEMES_KEY]:
            warnings.append(f"graph {gid!r}: active colour scheme {name!r} is not in the file; ignored")
            continue
        out[ACTIVE_KEY][str(gid)] = name
    return out, warnings


def section(pres: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """What the container writes under ``presentation`` (None: nothing — a file
    without schemes stays exactly what it was)."""
    if not pres:
        return None
    schemes = dict(pres.get(SCHEMES_KEY) or {})
    active = {g: n for g, n in (pres.get(ACTIVE_KEY) or {}).items() if n in schemes}
    if not schemes:
        return None
    out: Dict[str, Any] = {SCHEMES_KEY: schemes}
    if active:
        out[ACTIVE_KEY] = active
    return canonical(out)


# ── the schemes ─────────────────────────────────────────────────────────────

def scheme_names(pres: Mapping[str, Any]) -> List[str]:
    return sorted((pres.get(SCHEMES_KEY) or {}).keys())


def unique_name(pres: Mapping[str, Any], wanted: str) -> str:
    """``wanted``, or ``wanted (2)``, ``(3)``… when the file has it already."""
    base = (wanted or "").strip() or "scheme"
    have = pres.get(SCHEMES_KEY) or {}
    if base not in have:
        return base
    n = 2
    while f"{base} ({n})" in have:
        n += 1
    return f"{base} ({n})"


def add_scheme(pres: Dict[str, Any], name: str, emc_doc: Mapping[str, Any], *,
               replace: bool = False) -> str:
    """Keep a .emc document as a scheme of the file. Returns the name it got
    (a new one when ``name`` is taken and ``replace`` is False)."""
    why = _scheme_problem(emc_doc)
    if why:
        raise ValueError(f"not a colour scheme: {why}")
    pres.setdefault(SCHEMES_KEY, {})
    pres.setdefault(ACTIVE_KEY, {})
    got = (name or "").strip() if replace else unique_name(pres, name)
    if not got:
        raise ValueError("a colour scheme needs a name")
    pres[SCHEMES_KEY][got] = canonical(copy.deepcopy(dict(emc_doc)))
    return got


def remove_scheme(pres: Dict[str, Any], name: str) -> bool:
    """Take a scheme out of the file, and out of every graph that used it."""
    schemes = pres.get(SCHEMES_KEY) or {}
    if name not in schemes:
        return False
    del schemes[name]
    active = pres.get(ACTIVE_KEY) or {}
    for gid in [g for g, n in active.items() if n == name]:
        del active[gid]
    return True


def set_active(pres: Dict[str, Any], graph_id: str, name: Optional[str]) -> None:
    """The scheme ``graph_id`` uses (None: none)."""
    pres.setdefault(ACTIVE_KEY, {})
    if name is None:
        pres[ACTIVE_KEY].pop(graph_id, None)
        return
    if name not in (pres.get(SCHEMES_KEY) or {}):
        raise KeyError(f"no colour scheme {name!r} in the file")
    pres[ACTIVE_KEY][graph_id] = name


def active_scheme(pres: Mapping[str, Any], graph_id: Optional[str]
                  ) -> Optional[Tuple[str, Dict[str, Any]]]:
    """``(name, scheme)`` the graph uses, or None."""
    if graph_id is None:
        return None
    name = (pres.get(ACTIVE_KEY) or {}).get(graph_id)
    sch = (pres.get(SCHEMES_KEY) or {}).get(name) if name else None
    return (name, sch) if sch is not None else None


def summary(pres: Mapping[str, Any]) -> Dict[str, int]:
    """What «Pulisci il file» would take away: ``{"schemes": n, "active": m}``
    (``active``: the schemes some graph uses)."""
    schemes = pres.get(SCHEMES_KEY) or {}
    used = {n for n in (pres.get(ACTIVE_KEY) or {}).values() if n in schemes}
    return {"schemes": len(schemes), "active": len(used)}


def clean(pres: Dict[str, Any]) -> Dict[str, Any]:
    """«Pulisci il file»: the section emptied. Returns what it held (a copy),
    so the gesture can be taken back."""
    before = copy.deepcopy(dict(pres))
    pres.clear()
    pres.update(empty())
    return before


def merge(into: Dict[str, Any], other: Mapping[str, Any]) -> Dict[str, str]:
    """Another file's schemes taken in (integrating a project). The same name
    with the same scheme is one scheme; a different one gets a new name. The
    other file's choices for ITS graphs come along, unless this file has
    chosen already. Returns ``{their name: name here}``."""
    renamed: Dict[str, str] = {}
    for name, sch in sorted((other.get(SCHEMES_KEY) or {}).items()):
        mine = (into.get(SCHEMES_KEY) or {}).get(name)
        if mine is not None and canonical(mine) == canonical(sch):
            renamed[name] = name
            continue
        renamed[name] = add_scheme(into, name, sch)
    for gid, name in (other.get(ACTIVE_KEY) or {}).items():
        if name in renamed and gid not in (into.get(ACTIVE_KEY) or {}):
            set_active(into, gid, renamed[name])
    return renamed


# ── the .emc beside the file ────────────────────────────────────────────────

def emc_text(scheme: Mapping[str, Any]) -> str:
    """A scheme as a .emc file: sorted keys, two spaces, UTF-8 as it is.
    Expelling, importing and expelling again gives the same bytes."""
    return json.dumps(canonical(dict(scheme)), indent=2, ensure_ascii=False)


_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def emc_file_name(name: str) -> str:
    """``<name>.emc``, without what a file name cannot hold."""
    stem = _UNSAFE.sub("_", name).strip(" .") or "scheme"
    return f"{stem}.emc"


def expel(pres: Mapping[str, Any], folder: str, names: Optional[Iterable[str]] = None) -> List[str]:
    """«Espelli in una cartella…»: one .emc per scheme. Returns the paths
    written. The schemes stay in the file (taking them out is :func:`remove_scheme`,
    asked after)."""
    os.makedirs(folder, exist_ok=True)
    schemes = pres.get(SCHEMES_KEY) or {}
    out: List[str] = []
    for name in (list(names) if names is not None else scheme_names(pres)):
        path = os.path.join(folder, emc_file_name(name))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(emc_text(schemes[name]))
        out.append(path)
    return out


def import_emc_files(pres: Dict[str, Any], paths: Iterable[str]) -> List[str]:
    """«Importa nel file…»: each .emc becomes a scheme of the file, named after
    its file (``material.emc`` → ``material``). Returns the names given."""
    names: List[str] = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        stem = os.path.basename(p)
        stem = stem[:-4] if stem.lower().endswith(".emc") else os.path.splitext(stem)[0]
        names.append(add_scheme(pres, stem, doc))
    return names


# ── colouring ───────────────────────────────────────────────────────────────

def colours_for_values(scheme: Mapping[str, Any],
                       values: Mapping[str, Optional[str]]) -> Dict[str, str]:
    """``{label found on the units: hex seen}``: each label the colour of the
    scheme's entry with the SAME CODE when it has a code the scheme knows,
    else of the entry with the same text. ``values`` is ``{label: code or
    None}``; a label the scheme does not colour is left out."""
    prop, colours = emc_read(dict(scheme))
    del prop
    codes = (scheme.get("metadata") or {}).get(VALUE_CODES_KEY) or {}
    by_code = {c: colours[label] for label, c in sorted(codes.items()) if label in colours}
    out: Dict[str, str] = {}
    for label, code in values.items():
        if code and code in by_code:
            out[label] = by_code[code]
        elif label in colours:
            out[label] = colours[label]
    return out


def scheme_property(scheme: Mapping[str, Any]) -> str:
    return emc_read(dict(scheme))[0]


__all__ = [
    "PRESENTATION_KEY", "SCHEMES_KEY", "ACTIVE_KEY", "VALUE_CODES_KEY",
    "canonical", "empty", "read_presentation", "section", "scheme_names", "unique_name",
    "add_scheme", "remove_scheme", "set_active", "active_scheme", "summary", "clean", "merge",
    "emc_text", "emc_file_name", "expel", "import_emc_files", "colours_for_values",
    "scheme_property",
]
