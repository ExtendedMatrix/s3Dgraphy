"""Write the «types» reference (our ``bpy.types``) from s3Dgraphy's datamodels.

One page per NODE type and per EDGE type, from
``s3Dgraphy_node_datamodel.json``, ``s3Dgraphy_connections_datamodel.json``,
``node_registry.generated.json`` (the class tree) and
``datamodel_translations.json`` (the Italian labels). Stdlib only; run from
anywhere::

    python docs-api/_tools/gen_types.py

Output: ``docs-api/reference/types/`` (committed, so Read the Docs needs
nothing but the library). Every page says the em API and datamodel versions it
was made from.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CFG = ROOT / "src" / "s3dgraphy" / "JSON_config"
OUT = HERE.parent / "reference" / "types"


def load(name):
    return json.loads((CFG / name).read_text(encoding="utf-8"))


def api_version() -> str:
    text = (ROOT / "src" / "s3dgraphy" / "em" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'^API_VERSION\s*=\s*"([^"]+)"', text, re.M).group(1)


def esc(text) -> str:
    """Inline-safe text for RST (no markup survives, no line breaks)."""
    s = " ".join(str(text or "").split())
    for ch in "\\*`|_":
        s = s.replace(ch, "\\" + ch)
    return s


def first_sentence(text, limit=400) -> str:
    s = " ".join(str(text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    s = m.group(1) if m else s
    return s if len(s) <= limit else s[: limit - 1] + "…"


def title(text: str, ch: str = "=") -> str:
    return f"{text}\n{ch * max(len(text), 3)}\n"


def collect_details(tree):
    """class name → its hand-authored entry (description, mapping, properties)."""
    found = {}

    def walk(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict) and "class" in v:
                    found.setdefault(v["class"], v)
                    # the key of a subtype is its node_type (US, USVs…)
                    found.setdefault("@" + k, v)
                if isinstance(v, dict):
                    walk(v)
    walk(tree)
    return found


def cidoc_of(entry) -> str:
    m = (entry or {}).get("mapping") or {}
    if isinstance(m, str):
        return m
    parts = [m.get("cidoc"), m.get("extension_mapping")]
    return " · ".join(p for p in parts if isinstance(p, str) and p)


def tr(entries, key, field, lang):
    v = ((entries.get(key) or {}).get(field) or {})
    return v.get(lang) if isinstance(v, dict) else None


def main() -> int:
    nodes = load("s3Dgraphy_node_datamodel.json")
    conns = load("s3Dgraphy_connections_datamodel.json")
    registry = load("node_registry.generated.json")["node_types"]
    trans = load("datamodel_translations.json")
    entries, edge_tr = trans.get("entries", {}), trans.get("edge_types", {})
    details = collect_details(nodes)
    edges = {k: v for k, v in conns["edge_types"].items() if isinstance(v, dict) and "name" in v}
    api = api_version()
    nv, cv = nodes.get("s3Dgraphy_data_model_version"), conns.get("s3Dgraphy_connections_model_version")
    stamp = (f".. note::\n\n   Generated from the datamodels (nodes {nv}, connections {cv}) "
             f"for em API {api} by ``docs-api/_tools/gen_types.py``.\n")

    def ancestors(cls):
        chain, seen = [], set()
        while cls and cls not in seen:
            seen.add(cls)
            chain.append(cls)
            cls = (registry.get(cls) or {}).get("parent")
        return chain

    def edges_for(cls, side):
        chain = set(ancestors(cls))
        out = []
        for name, e in sorted(edges.items()):
            allowed = (e.get("allowed_connections") or {}).get(side) or []
            if any(a in chain for a in allowed):
                out.append(name)
        return out

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "nodes").mkdir(parents=True)
    (OUT / "edges").mkdir(parents=True)

    node_rows = []
    for cls in sorted(registry):
        reg = registry[cls]
        ntype = reg.get("node_type")
        det = details.get(cls) or (details.get("@" + ntype) if ntype else None) or {}
        label_en = tr(entries, cls, "label", "en") or det.get("label") or cls
        label_it = tr(entries, cls, "label", "it") or ""
        desc_en = tr(entries, cls, "description", "en") or det.get("description") or reg.get("description") or ""
        desc_it = tr(entries, cls, "description", "it") or ""
        cidoc = cidoc_of(det)
        out_e, in_e = edges_for(cls, "source"), edges_for(cls, "target")
        lines = [f".. _type-{cls}:\n", title(f"{cls}"), stamp]
        lines.append(f"*{esc(first_sentence(desc_en))}*\n")
        lines.append(".. list-table::\n   :widths: 25 75\n")
        rows = [("Class", f"``{cls}``"),
                ("node_type", f"``{ntype}``" if ntype else "— (abstract: no node has it)"),
                ("Parent", f":ref:`{reg['parent']} <type-{reg['parent']}>`" if reg.get("parent") in registry else esc(reg.get("parent") or "—")),
                ("Label (en)", esc(label_en)), ("Label (it)", esc(label_it) or "—"),
                ("CIDOC", f"``{cidoc}``" if cidoc else "—")]
        for k, v in rows:
            lines.append(f"   * - {k}\n     - {v}")
        lines.append("")
        if desc_en:
            lines.append(title("Description", "-") + "\n" + esc(desc_en) + "\n")
        if desc_it:
            lines.append(f"*Italiano*: {esc(desc_it)}\n")
        props = det.get("properties") if isinstance(det.get("properties"), dict) else {}
        props = {k: v for k, v in props.items() if not k.startswith("_")}
        if props:
            lines.append(title("Fields", "-"))
            lines.append(".. list-table::\n   :header-rows: 1\n   :widths: 25 75\n\n   * - Field\n     - Mapping / note")
            for k, v in props.items():
                if isinstance(v, dict):
                    note = v.get("description") or v.get("rdf") or v.get("value") or ""
                    if isinstance(note, dict):
                        note = ", ".join(f"{a}: {b}" for a, b in note.items() if isinstance(b, str))
                    dep = f" (deprecated {v['deprecated']})" if v.get("deprecated") else ""
                    note = first_sentence(note, 300) + dep
                else:
                    note = str(v)
                lines.append(f"   * - ``{k}``\n     - {esc(note) or '—'}")
            lines.append("")
        lines.append(title("Edges", "-"))
        fmt = lambda names: ", ".join(f":ref:`{n} <edge-{n}>`" for n in names) or "—"
        lines.append(f"**Outgoing** (this node is the source): {fmt(out_e)}\n")
        lines.append(f"**Incoming** (this node is the target): {fmt(in_e)}\n")
        if ntype:
            lines.append(title("From em", "-"))
            lines.append(".. code-block:: python\n")
            lines.append(f"   for n in em.graph.nodes(type={ntype!r}):   # read")
            lines.append("       print(n.id, n.name, n.description)\n")
            lines.append(f"   with em.write(\"Add a {ntype}\") as tx:        # create: one step of undo")
            lines.append(f"       nid = tx.add_node({ntype!r}, \"name\", description=\"…\")\n")
        (OUT / "nodes" / f"{cls}.rst").write_text("\n".join(lines) + "\n", encoding="utf-8")
        node_rows.append((cls, ntype, label_en, label_it))

    edge_rows = []
    for name, e in sorted(edges.items()):
        ac = e.get("allowed_connections") or {}
        rev = (e.get("reverse") or {}).get("name") or "—"
        label_it = (edge_tr.get(name, {}).get("label") or {}).get("it") if isinstance(edge_tr.get(name, {}).get("label"), dict) else None
        cidoc = cidoc_of(e)
        lines = [f".. _edge-{name}:\n", title(name), stamp, f"*{esc(first_sentence(e.get('description')))}*\n",
                 ".. list-table::\n   :widths: 25 75\n"]
        src = ", ".join(f":ref:`{c} <type-{c}>`" if c in registry else esc(c) for c in ac.get("source") or []) or "—"
        tgt = ", ".join(f":ref:`{c} <type-{c}>`" if c in registry else esc(c) for c in ac.get("target") or []) or "—"
        for k, v in [("Label (en)", esc(e.get("label"))), ("Label (it)", esc(label_it) or "—"),
                     ("Reverse", f"``{rev}``" if rev != "—" else rev), ("Source", src), ("Target", tgt),
                     ("CIDOC", f"``{cidoc}``" if cidoc else "—")]:
            lines.append(f"   * - {k}\n     - {v}")
        lines.append("")
        if e.get("description"):
            lines.append(title("Description", "-") + "\n" + esc(e["description"]) + "\n")
        lines.append(title("From em", "-"))
        lines.append(".. code-block:: python\n")
        lines.append(f"   em.graph.edges(type={name!r})                  # read")
        lines.append(f"   with em.write(\"Link\") as tx:")
        lines.append(f"       tx.add_edge(source, {name!r}, target)    # the contract checks the pair\n")
        (OUT / "edges" / f"{name}.rst").write_text("\n".join(lines) + "\n", encoding="utf-8")
        edge_rows.append((name, e.get("label") or "", label_it or "", rev))

    idx = [".. _types:\n", title("Types — nodes and edges"), stamp,
           "The types of the EM language: what ``em.graph`` returns as "
           ":class:`~s3dgraphy.em.NodeView` and :class:`~s3dgraphy.em.EdgeView`, and "
           "what ``tx.add_node`` / ``tx.add_edge`` accept. The edges a node may have are "
           "checked by the contract at every write.\n",
           title("Node types", "-"),
           ".. list-table::\n   :header-rows: 1\n   :widths: 30 15 30 25\n\n   * - Class\n     - node_type\n     - Label\n     - Etichetta (it)"]
    for cls, nt, le, li in node_rows:
        idx.append(f"   * - :ref:`{cls} <type-{cls}>`\n     - {('``' + nt + '``') if nt else '—'}\n     - {esc(le)}\n     - {esc(li) or '—'}")
    idx += ["", title("Edge types", "-"),
            ".. list-table::\n   :header-rows: 1\n   :widths: 30 25 25 20\n\n   * - Edge\n     - Label\n     - Etichetta (it)\n     - Reverse"]
    for n, le, li, rv in edge_rows:
        idx.append(f"   * - :ref:`{n} <edge-{n}>`\n     - {esc(le)}\n     - {esc(li) or '—'}\n     - {('``' + rv + '``') if rv != '—' else rv}")
    idx += ["", ".. toctree::\n   :hidden:\n   :glob:\n\n   nodes/*\n   edges/*\n"]
    (OUT / "index.rst").write_text("\n".join(idx) + "\n", encoding="utf-8")
    print(f"types: {len(node_rows)} node pages, {len(edge_rows)} edge pages → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
