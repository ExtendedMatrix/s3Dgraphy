"""A .blend read as a FOLDER, and checked against the graph — one function,
two faces (MICRO-BLEND-OFFICINA-1, E.D.'s decision of 30 Oct 2026: «Blender
come officina, EMStudio come regia»).

The .blend is a workshop and a cache; the stamped files outside it are what
holds. Blender (EM Tools) and EMStudio (through Blender headless) read the
same .blend and say the same thing about it, because both hand what Blender
measured to the functions here:

* :func:`normalize` — the raw dump of a .blend (objects, collections, images,
  libraries, as EM Tools' ``sync_manager.blend_inventory.collect`` writes it)
  turned into the INVENTORY: each object with its kind (proxy, USV, SF,
  alternative, model, document), its graph properties, its triangles and the
  FILE its mesh lives in (a linked library, recursively); each texture packed,
  external or missing; each library with its relative path, its parent and
  whether it is there.
* :func:`tree`, :func:`filter_objects`, :func:`chase` — the folder view: the
  tree of collections / objects / libraries, the filters (graph: model,
  epoch, unit, document; collection; name; kind; state of the master) and
  «Go to the linked file», which follows a mesh to the .blend that holds it.
* :func:`check` — «Check against the graph»: per object and resource one of
  five states (``✔ ↑ ↓ ✗ ○``), with textures, the versions born from the
  current master, the epochs, the libraries followed; the source is the DISK
  (stamps, fingerprints) or the ROOM (fingerprints from the server; offline =
  the last state known, said).
* :func:`save_rule` — who may save a .blend now (point 1 of the MICRO,
  measured on Blender 5.2): never two sessions saving the same file.

No ``bpy`` here: what Blender measured comes in as plain data, so the same
answer is computed in a test, in EM Tools and in EMStudio's bridge.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional

#: the five states of «Check against the graph», with their signs
STATES: Dict[str, str] = {
    "aligned": "✔",        # the .blend holds what the graph cites
    "changed_here": "↑",   # changed in Blender since its bytes were stamped
    "newer_outside": "↓",  # the graph (or the disk, or the room) has newer bytes
    "missing": "✗",        # cited and not here (object, texture, library)
    "only_here": "○",      # in the .blend only, not stamped: work in progress
}
#: the order a list is read in: what needs a hand first
STATE_ORDER = ("missing", "newer_outside", "changed_here", "only_here", "aligned")

#: the properties of the graph on an object (the pass on GreatTemple_2026_v2,
#: 208 objects, 30 Oct 2026); everything else (graswald, b4w, CAPObj,
#: snapShot, cycles…) belongs to older add-ons and is ignored
GRAPH_PROPS = (
    "em_rm_node_id", "EM_ep_belong_ob", "em_belong_id", "em_doc_node_id", "USV",
    "em_asset_id", "em_version_id", "em_level", "em_asset_sha256", "em_resource_id",
    "em_mesh_fp", "em_only_here", "tileset_path",
)
GRAPH_PROP_PREFIXES = ("em_alternative_",)

#: object types that are content (cameras, lights, empties are not listed as
#: models; they stay in the tree)
CONTENT_TYPES = ("MESH", "CURVE", "SURFACE", "META", "FONT", "POINTCLOUD", "VOLUME")

#: the kinds of the filter, in its order
KINDS = ("proxy", "usv", "sf", "alternative", "model", "document", "tileset", "other")

_SF_RE = re.compile(r"(^|[._])(V?SF)\d", re.I)
_USV_RE = re.compile(r"(^|[._])USV", re.I)


def is_graph_prop(key: str) -> bool:
    return key in GRAPH_PROPS or any(key.startswith(p) for p in GRAPH_PROP_PREFIXES)


def unit_name(object_name: str) -> str:
    """The node name a proxy's object name stands for: the graph code before
    the first dot is a prefix (``GT16.SU001`` → ``SU001``), EM Tools' rule
    (``addon_prefix_helpers.get_base_name``)."""
    name = str(object_name or "")
    head, dot, tail = name.partition(".")
    if dot and tail and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,15}", head) and not tail.isdigit():
        return tail
    return name


def _norm(path: str) -> str:
    return os.path.normpath(str(path or "")).replace("\\", "/") if path else ""


def _rel(path: str, start: str) -> str:
    if not path or not start:
        return path or ""
    try:
        return os.path.relpath(path, start).replace("\\", "/")
    except ValueError:  # another drive on Windows
        return path


def _strings(value: Any) -> List[str]:
    """The names a graph property carries: a string, a list of strings or of
    groups ({epoch: …}, {name: …}), as Blender's ID properties dump them."""
    out: List[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        for k in ("epoch", "name", "id", "node", "value"):
            if value.get(k):
                return [str(value[k])]
        return [str(v) for v in value.values() if isinstance(v, str) and v]
    if isinstance(value, (list, tuple)):
        for v in value:
            out += _strings(v)
        return out
    return []


def object_kind(obj: Dict[str, Any]) -> str:
    """The kind of an object for the filter, read off its properties, its
    collections and its name — never guessed beyond them."""
    props = obj.get("props") or {}
    cols = {c.lower() for c in obj.get("collections") or []}
    name = str(obj.get("name") or "")
    if any(k.startswith("em_alternative_") for k in props):
        return "alternative"
    if props.get("tileset_path"):
        return "tileset"
    if "USV" in props or _USV_RE.search(unit_name(name)):
        return "usv"
    if "sf" in cols or "vsf" in cols or _SF_RE.search(unit_name(name)):
        return "sf"
    if "proxy" in cols or props.get("em_belong_id"):
        return "proxy"
    if props.get("em_doc_node_id"):
        return "document"
    if props.get("em_rm_node_id") or props.get("em_asset_id"):
        return "model"
    return "other"


# ── the inventory ────────────────────────────────────────────────────────────

def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """The raw dump of a .blend → the inventory.

    ``raw``: ``{blend, objects: [{name, type, collections, props, triangles,
    vertices, library, data_library, mesh, fingerprint}], collections:
    [{name, children, objects, library}], images: [{name, filepath, abspath,
    packed, exists, library, source}], libraries: [{name, filepath, abspath,
    exists, parent}], scene_collection?: [names of the top collections]}``.
    Library fields are the library's NAME (``bpy.data.libraries`` key)."""
    blend = _norm(raw.get("blend") or "")
    here = os.path.dirname(blend) if blend else ""
    libs: Dict[str, Dict[str, Any]] = {}
    for lb in raw.get("libraries") or []:
        ab = _norm(lb.get("abspath") or "")
        libs[str(lb.get("name"))] = {
            "name": str(lb.get("name") or ""), "filepath": str(lb.get("filepath") or ""),
            "path": ab, "rel": _rel(ab, here), "exists": bool(lb.get("exists")),
            "parent": lb.get("parent") or None, "objects": [], "meshes": 0,
        }
    for lb in libs.values():
        depth, seen, p = 0, set(), lb["parent"]
        while p and p in libs and p not in seen:
            seen.add(p)
            depth += 1
            p = libs[p]["parent"]
        lb["depth"] = depth
        lb["indirect"] = depth > 0
        # a library whose parent is missing is missing too, as far as this
        # .blend can tell
        lb["missing"] = not lb["exists"]

    def chain_of(libname: Optional[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        while libname and libname in libs and libname not in seen:
            seen.add(libname)
            out.insert(0, libs[libname]["path"])
            libname = libs[libname]["parent"]
        return out

    objects: List[Dict[str, Any]] = []
    for o in raw.get("objects") or []:
        props = {k: v for k, v in (o.get("props") or {}).items() if is_graph_prop(k)}
        lib = o.get("data_library") or o.get("library") or None
        chain = chain_of(lib) if lib else []
        source = chain[-1] if chain else blend
        missing = bool(lib and (lib not in libs or not libs[lib]["exists"]
                                or any(not libs[n]["exists"] for n in libs if libs[n]["path"] in chain)))
        row = {
            "name": str(o.get("name") or ""), "type": str(o.get("type") or ""),
            "collections": list(o.get("collections") or []), "props": props,
            "triangles": int(o.get("triangles") or 0), "vertices": int(o.get("vertices") or 0),
            "mesh": str(o.get("mesh") or ""), "fingerprint": str(o.get("fingerprint") or ""),
            "library": lib, "linked": bool(lib), "object_linked": bool(o.get("library")),
            "source": source, "source_rel": _rel(source, here), "chain": chain,
            "missing": missing,
            "epochs": _strings(props.get("EM_ep_belong_ob")),
            "units": _strings(props.get("em_belong_id")),
        }
        row["kind"] = object_kind(row)
        row["content"] = row["type"] in CONTENT_TYPES
        objects.append(row)
        if lib in libs:
            libs[lib]["objects"].append(row["name"])

    images: List[Dict[str, Any]] = []
    for im in raw.get("images") or []:
        if im.get("source") not in (None, "", "FILE", "SEQUENCE", "TILED"):
            continue   # the viewer, render results, generated
        ab = _norm(im.get("abspath") or "")
        if im.get("library"):
            state = "linked"
        elif im.get("packed"):
            state = "packed"
        elif ab and im.get("exists"):
            state = "external"
        else:
            state = "missing"
        images.append({"name": str(im.get("name") or ""), "state": state, "path": ab,
                       "rel": _rel(ab, here) if ab else "", "filepath": str(im.get("filepath") or ""),
                       "library": im.get("library") or None, "users": list(im.get("users") or [])})

    cols = []
    for c in raw.get("collections") or []:
        cols.append({"name": str(c.get("name") or ""), "children": list(c.get("children") or []),
                     "objects": list(c.get("objects") or []), "library": c.get("library") or None})

    tex_counts = {s: 0 for s in ("packed", "external", "missing", "linked")}
    for im in images:
        tex_counts[im["state"]] += 1
    return {
        "blend": blend, "folder": here, "objects": objects, "collections": cols,
        "top": list(raw.get("scene_collection") or []),
        "images": images, "libraries": sorted(libs.values(), key=lambda lb: (lb["depth"], lb["rel"])),
        "counts": {
            "objects": len(objects),
            "content": sum(1 for o in objects if o["content"]),
            "linked": sum(1 for o in objects if o["linked"]),
            "graph": sum(1 for o in objects if o["props"]),
            "kinds": {k: sum(1 for o in objects if o["kind"] == k) for k in KINDS},
            "textures": tex_counts,
            "libraries": len(libs),
            "libraries_missing": sum(1 for lb in libs.values() if not lb["exists"]),
        },
        "measured_at": raw.get("measured_at"), "mtime": raw.get("mtime"),
        "blender": raw.get("blender"),
    }


def tree(inv: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The folder view: the collections nested as in Blender (the top ones
    first, in the scene's order), each with its objects; the objects in no
    collection under «—»; then the LIBRARIES with what comes from each.
    → ``[{kind: collection|library|loose, name, children, objects}]``."""
    by = {c["name"]: c for c in inv.get("collections") or []}
    child = {ch for c in by.values() for ch in c["children"]}
    tops = [n for n in inv.get("top") or [] if n in by] or [n for n in by if n not in child]

    def node(name: str, seen: set) -> Dict[str, Any]:
        c = by[name]
        seen = seen | {name}
        return {"kind": "collection", "name": name, "library": c.get("library"),
                "objects": list(c["objects"]),
                "children": [node(ch, seen) for ch in c["children"] if ch in by and ch not in seen]}

    out = [node(n, set()) for n in tops]
    placed = {o for c in by.values() for o in c["objects"]}
    loose = [o["name"] for o in inv.get("objects") or [] if o["name"] not in placed]
    if loose:
        out.append({"kind": "loose", "name": "", "objects": loose, "children": []})
    for lb in inv.get("libraries") or []:
        out.append({"kind": "library", "name": lb["name"], "path": lb["path"], "rel": lb["rel"],
                    "exists": lb["exists"], "depth": lb["depth"], "parent": lb["parent"],
                    "objects": list(lb["objects"]), "children": []})
    return out


def _fold(text: Any) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def filter_objects(inv: Dict[str, Any], *, name: str = "", kind: str = "", collection: str = "",
                   model: str = "", epoch: str = "", unit: str = "", document: str = "",
                   state: str = "", states: Optional[Dict[str, str]] = None,
                   content_only: bool = False) -> List[Dict[str, Any]]:
    """The objects that pass every filter given (an empty filter passes all).
    ``model``/``epoch``/``unit``/``document`` read the graph properties;
    ``state`` reads ``states`` (object name → state key, :func:`check`)."""
    q = _fold(name)
    out = []
    for o in inv.get("objects") or []:
        p = o["props"]
        if content_only and not o["content"]:
            continue
        if q and q not in _fold(o["name"]):
            continue
        if kind and o["kind"] != kind:
            continue
        if collection and collection not in o["collections"]:
            continue
        if model and _fold(model) not in _fold(p.get("em_rm_node_id") or p.get("em_asset_id") or ""):
            continue
        if epoch and not any(_fold(epoch) == _fold(e) for e in o["epochs"]):
            continue
        if unit and not (any(_fold(unit) == _fold(u) for u in o["units"])
                         or _fold(unit) == _fold(unit_name(o["name"]))):
            continue
        if document and _fold(document) not in _fold(p.get("em_doc_node_id") or ""):
            continue
        if state and (states or {}).get(o["name"]) != state:
            continue
        out.append(o)
    return out


def chase(inv: Dict[str, Any], object_name: str) -> Optional[Dict[str, Any]]:
    """«Go to the linked file»: the .blend that HOLDS an object's mesh, through
    every library in between. → ``{object, file, rel, chain, linked, missing}``
    (``linked`` False = the mesh is in this .blend), or None."""
    for o in inv.get("objects") or []:
        if o["name"] == object_name:
            return {"object": o["name"], "mesh": o["mesh"], "file": o["source"], "rel": o["source_rel"],
                    "chain": list(o["chain"]), "linked": o["linked"], "missing": o["missing"]}
    return None


# ── the graph, read as em.json ───────────────────────────────────────────────

def _graph_of(doc: Any) -> Dict[str, Any]:
    """A graph dict ``{nodes: [...], edges: [...]}`` from an em.json document
    (its active graph), a graph section, or a graph dict."""
    if not isinstance(doc, dict):
        return {"nodes": [], "edges": []}
    if "graphs" in doc:
        gs = doc["graphs"]
        if isinstance(gs, dict):
            g = gs.get(doc.get("active_graph_id")) or next(iter(gs.values()), {})
        else:
            g = (gs or [{}])[0]
        return _graph_of(g)
    if isinstance(doc.get("graph"), dict):          # api.graph_to_emjson
        return _graph_of(doc["graph"])
    nodes = doc.get("nodes") or []
    if isinstance(nodes, dict):
        nodes = [dict(v, id=v.get("id", k)) for k, v in nodes.items()]
    return {"nodes": nodes, "edges": doc.get("edges") or []}


def _data(n: Dict[str, Any]) -> Dict[str, Any]:
    return n.get("data") or {}


def _digest(v: Any) -> str:
    s = str(v or "").strip().lower()
    return ("sha256:" + s) if s and not s.startswith("sha256:") else s


class _G:
    """The few questions :func:`check` asks of a graph."""

    def __init__(self, doc: Any):
        g = _graph_of(doc)
        self.nodes = {n.get("id"): n for n in g["nodes"] if n.get("id")}
        self.by_name: Dict[str, List[str]] = {}
        for nid, n in self.nodes.items():
            self.by_name.setdefault(str(n.get("name") or ""), []).append(nid)
        self.out: Dict[str, List[tuple]] = {}
        self.inc: Dict[str, List[tuple]] = {}
        for e in g["edges"]:
            s, t, k = e.get("source"), e.get("target"), e.get("edge_type")
            self.out.setdefault(s, []).append((k, t))
            self.inc.setdefault(t, []).append((k, s))

    def type(self, nid: str) -> str:
        return str((self.nodes.get(nid) or {}).get("node_type") or "")

    def name(self, nid: str) -> str:
        return str((self.nodes.get(nid) or {}).get("name") or nid)

    def epochs_of(self, nid: str) -> List[str]:
        names = []
        for k, s in self.inc.get(nid, []):
            if k == "has_representation_model" and self.type(s) == "EpochNode":
                names.append(self.name(s))
        for k, t in self.out.get(nid, []):
            if k in ("has_first_epoch", "survive_in_epoch") and self.type(t) == "EpochNode":
                names.append(self.name(t))
        return sorted(set(names))

    def master_of(self, rm_id: str) -> Optional[str]:
        """The master resource an RM (or proxy) hats: its linked resource with
        ``tier: master``, else its only linked 3D resource."""
        cands = [t for k, t in self.out.get(rm_id, []) if k == "has_linked_resource" and t in self.nodes]
        masters = [t for t in cands if _data(self.nodes[t]).get("tier") == "master"]
        if masters:
            return masters[0]
        threed = [t for t in cands if _data(self.nodes[t]).get("url_type") == "3d_model"]
        return threed[0] if len(threed) == 1 else None

    def children_of(self, res_id: str) -> List[str]:
        """The versions born from a resource (``version ─dtc_derived_from▶
        master``)."""
        return sorted({s for k, s in self.inc.get(res_id, []) if k == "dtc_derived_from"
                       and self.type(s) == "resource"})

    def newer_revision(self, res_id: str) -> Optional[str]:
        """The revision that replaced a resource (``new ─was_revision_of▶ old``),
        followed to the newest."""
        cur, seen = res_id, set()
        while True:
            nxt = [s for k, s in self.inc.get(cur, []) if k == "was_revision_of"]
            if not nxt or nxt[0] in seen:
                return cur if cur != res_id else None
            seen.add(cur)
            cur = nxt[0]

    def resource_for(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """The node an object stands for, from its bindings: the version shown
        (``em_version_id``), the asset (``em_asset_id``), the resource
        (``em_resource_id``), the RM (``em_rm_node_id``) and its master, a
        proxy (its name) and its master."""
        p = obj["props"]
        out: Dict[str, Any] = {"rm": None, "resource": None, "master": None, "unit": None}
        for key in ("em_version_id", "em_resource_id"):
            v = str(p.get(key) or "")
            if v and v in self.nodes:
                out["resource"] = v
                break
        a = str(p.get("em_asset_id") or "")
        if a in self.nodes:
            out["master"] = a
            out["resource"] = out["resource"] or a
        rm = str(p.get("em_rm_node_id") or "")
        if rm in self.nodes:
            out["rm"] = rm
        elif obj["kind"] in ("proxy", "usv", "sf"):
            hits = self.by_name.get(unit_name(obj["name"])) or []
            if hits:
                out["unit"] = hits[0]
        hat = out["rm"] or out["unit"]
        if hat and not out["master"]:
            out["master"] = self.master_of(hat)
            out["resource"] = out["resource"] or out["master"]
        return out


#: on a master exported from a datablock («Export as master»): the
#: ``blend://`` locator it was made from — so a .blend still knows the masters
#: it made when their url is a file outside
FROM_DATABLOCK = "from_datablock"


def _blend_url(url: str) -> bool:
    return str(url or "").startswith("blend://")


def _same_blend(url: str, blend: str, em_folder: str) -> bool:
    """A ``blend://<rel>#Mesh/<name>`` url that points at this .blend."""
    path = str(url or "")[len("blend://"):].split("#", 1)[0]
    if not path or not blend:
        return False
    if not os.path.isabs(path) and em_folder:
        path = os.path.join(em_folder, path)
    return _norm(path) == _norm(blend) or os.path.basename(path) == os.path.basename(blend)


def check(inv: Dict[str, Any], doc: Any, *, files: Optional[Dict[str, Dict[str, Any]]] = None,
          source: str = "disk", offline: bool = False, as_of: str = "",
          em_folder: str = "") -> Dict[str, Any]:
    """«Check against the graph» — the same function in EM Tools and in EMStudio.

    ``inv``: :func:`normalize`'s inventory (of the .blend and, followed, its
    libraries: an object linked from a library is checked as any other — its
    file is said). ``doc``: the em.json (or its graph). ``files``: what the
    SOURCE knows of the files the graph cites, by resource id or by checksum —
    ``{id or sha256: {sha256, exists, path}}``: from the disk (the stamps and
    the fingerprints beside the files) or from the room (the server's
    fingerprints). ``offline``: the room was not reached and ``files`` is the
    last state known (``as_of``): every row says so.

    → ``{rows: [{key, kind, name, state, sign, why, file, actions, action,
    tick, …}], counts, sentence, source, offline, as_of}``. The actions are
    what a row CAN do; ``action`` is the one proposed, ``tick`` whether it is
    ticked by default: what brings in what is outside is ticked, what
    registers a change made here is not (it is a person's call), nothing
    overwrites a change made in Blender."""
    g = _G(doc)
    files = files or {}
    blend = inv.get("blend") or ""
    rows: List[Dict[str, Any]] = []
    seen_rm, seen_res = set(), set()

    def row(**kw) -> Dict[str, Any]:
        r = {"tick": False, "actions": [], "action": None, "why": "", "notes": []}
        r.update(kw)
        r["sign"] = STATES[r["state"]]
        if offline:
            r["notes"].append("last state known" + (f" ({as_of})" if as_of else ""))
        rows.append(r)
        return r

    for o in inv.get("objects") or []:
        if not o["content"]:
            continue
        p = o["props"]
        bound = g.resource_for(o)
        hat = bound["rm"] or bound["unit"]
        if bound["rm"]:
            seen_rm.add(bound["rm"])
        for rid in (bound["resource"], bound["master"]):
            if rid:
                seen_res.add(rid)
        base = {"key": "object:" + o["name"], "kind": "object", "name": o["name"], "object": o["name"],
                "file": o["source_rel"] if o["linked"] else "", "library": o["library"],
                "rm": bound["rm"], "unit": bound["unit"], "resource": bound["resource"],
                "master": bound["master"], "object_kind": o["kind"]}
        if not hat and not bound["resource"]:
            if p.get("tileset_path") or any(k.startswith("em_alternative_") for k in p):
                row(state="aligned", why="a reference to a file outside (tileset / alternative)", **base)
                continue
            row(state="only_here", why="only in the .blend, not stamped",
                actions=["register_resource", "leave"], action="leave", **base)
            continue
        if o["missing"]:
            row(state="missing", why=f"its library is missing: {o['source_rel']}",
                actions=["relink_library", "restore_from_master"], action="relink_library", tick=True, **base)
            continue
        res = bound["resource"]
        node = g.nodes.get(res) if res else None
        want = _digest(_data(node).get("checksum")) if node else ""
        have = _digest(p.get("em_asset_sha256"))
        recorded = str(p.get("em_mesh_fp") or "")
        notes: List[str] = []
        state, why, actions, action, tick = "aligned", "", [], None, False
        # the version shown was revised in the graph
        newer = g.newer_revision(res) if res else None
        # what the source (disk or room) says of the master's file
        f = files.get(res or "") or (files.get(want) if want else None) or {}
        if recorded and o["fingerprint"] and recorded != o["fingerprint"]:
            state, why = "changed_here", "the mesh changed in Blender since its bytes were stamped"
            actions, action = ["register_version", "register_resource", "restore_from_master", "leave"], "register_version"
        elif newer:
            state, why = "newer_outside", f"a newer revision is in the graph: {g.name(newer)}"
            actions, action, tick = ["restore_from_master", "leave"], "restore_from_master", True
        elif have and want and have != want:
            state, why = "newer_outside", "the graph cites other bytes than the ones in the .blend"
            actions, action, tick = ["restore_from_master", "register_version", "leave"], "restore_from_master", True
        elif f and f.get("exists") is False:
            state, why = "missing", "the master the graph cites is not on the " + ("server" if source == "room" else "disk")
            actions, action = ["export_master", "leave"], "export_master"
        elif f and f.get("sha256") and want and _digest(f["sha256"]) != want:
            state, why = "newer_outside", "the file on the " + ("server" if source == "room" else "disk") + " is not the one the graph cites"
            actions, action, tick = ["restore_from_master", "leave"], "restore_from_master", True
        elif node and _blend_url(_data(node).get("url")) and _same_blend(_data(node).get("url"), blend, em_folder):
            # the master IS a datablock of this .blend: aligned, but nothing
            # stamped holds it outside (the decision: «fanno fede i file timbrati»)
            notes.append("its master is a datablock of this .blend: export it as a master")
            actions, action = ["export_master", "leave"], "export_master"
        elif not recorded and not have:
            notes.append("no fingerprint yet: the first stamp writes it")
        # epochs: the object's against the graph's
        if hat:
            mine = {e for e in o["epochs"] if e}
            theirs = set(g.epochs_of(hat))
            if mine and theirs and mine != theirs:
                only_here = sorted(mine - theirs)
                only_graph = sorted(theirs - mine)
                if only_here:
                    notes.append("epochs only in Blender: " + ", ".join(only_here))
                if only_graph:
                    notes.append("epochs only in the graph: " + ", ".join(only_graph))
                if state == "aligned":
                    state, why = "newer_outside", "the epochs differ from the graph's"
                    actions, action, tick = ["take_epochs_from_graph", "leave"], "take_epochs_from_graph", True
        children = g.children_of(bound["master"]) if bound["master"] else []
        r = row(state=state, why=why, actions=actions, action=action, tick=tick, **base)
        r["notes"] += notes
        r["versions"] = len(children)
        r["version_names"] = [g.name(c) for c in children][:12]
        r["epochs_graph"] = g.epochs_of(hat) if hat else []

    # the RMs and masters cited by the graph that point at THIS .blend and no
    # object here holds — missing
    for rid, n in g.nodes.items():
        if n.get("node_type") != "representation_model" or rid in seen_rm:
            continue
        master = g.master_of(rid)
        if not master or master in seen_res:
            continue
        d = _data(g.nodes[master])
        url = str(d.get("url") or "")
        made_here = str(d.get(FROM_DATABLOCK) or "")
        if (_blend_url(url) and _same_blend(url, blend, em_folder)) or \
                (made_here and _same_blend(made_here, blend, em_folder)):
            stamped = not _blend_url(url)
            row(key="rm:" + rid, kind="resource", name=g.name(rid), state="missing",
                why=("its object was deleted from this .blend; the stamped master is outside" if stamped
                     else "the graph cites it in this .blend and no object holds it"),
                rm=rid, master=master, object=g.name(rid),
                actions=["restore_from_master", "leave"], action="restore_from_master", tick=False)

    for im in inv.get("images") or []:
        base = {"key": "image:" + im["name"], "kind": "texture", "name": im["name"],
                "file": im["rel"] or im["filepath"]}
        if im["state"] == "missing":
            row(state="missing", why="the texture is not where the .blend says",
                actions=["relink_texture", "leave"], action="relink_texture", tick=True, **base)
        elif im["state"] == "packed":
            row(state="aligned", why="packed in the .blend",
                actions=["unpack_texture", "leave"], action="leave", **base)
        else:
            row(state="aligned", why="external" if im["state"] == "external" else "from a library", **base)

    for lb in inv.get("libraries") or []:
        if not lb["exists"]:
            row(key="library:" + lb["name"], kind="library", name=lb["name"], file=lb["rel"],
                state="missing", why="the linked .blend is not there",
                actions=["relink_library", "leave"], action="relink_library", tick=True)

    rows.sort(key=lambda r: (STATE_ORDER.index(r["state"]), r["kind"], r["name"].lower()))
    counts = {k: sum(1 for r in rows if r["state"] == k) for k in STATES}
    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], {k: 0 for k in STATES})[r["state"]] += 1
    return {"rows": rows, "counts": counts, "by_kind": by_kind, "sentence": sentence(counts),
            "source": source, "offline": offline, "as_of": as_of, "blend": blend,
            "objects": {r["object"]: r["state"] for r in rows if r["kind"] == "object"}}


def disk_files(doc: Any, em_folder: str) -> Dict[str, Dict[str, Any]]:
    """What the DISK says of the masters the graph cites, for :func:`check`:
    each master file there or not, and the digest its stamp says (the
    ``.stamp.json`` beside it) — never reading the big files themselves."""
    import json
    out: Dict[str, Dict[str, Any]] = {}
    for n in _graph_of(doc)["nodes"]:
        d = _data(n)
        if n.get("node_type") != "resource" or d.get("tier") != "master":
            continue
        url = str(d.get("url") or "")
        if not url or url.startswith(("blend://", "http://", "https://", "sha256:")):
            continue
        path = url if os.path.isabs(url) else os.path.normpath(os.path.join(em_folder or "", url))
        row: Dict[str, Any] = {"path": path, "exists": os.path.exists(path)}
        try:
            with open(path + ".stamp.json", "r", encoding="utf-8") as fh:
                st = json.load(fh)
            row["sha256"] = str(((st.get("self") or {}).get("digest")) or "")
        except (OSError, ValueError):
            pass
        out[n["id"]] = row
    return out


def node_states(result: Dict[str, Any]) -> Dict[str, str]:
    """The state of each graph node a row stands for (its RM, its unit, its
    master, its resource) — the dot EMStudio's Outliner and Inspector draw. A
    node held by several objects shows the worst."""
    acc: Dict[str, List[str]] = {}
    for r in result.get("rows") or []:
        for k in ("rm", "unit", "master", "resource"):
            nid = r.get(k)
            if nid:
                acc.setdefault(nid, []).append(r["state"])
    return {nid: worst(sts) or "aligned" for nid, sts in acc.items()}


def sentence(counts: Dict[str, int]) -> str:
    """One line, the signs and the numbers that are not zero."""
    parts = [f"{STATES[k]} {counts[k]}" for k in ("aligned", "changed_here", "newer_outside", "missing", "only_here")
             if counts.get(k)]
    return " · ".join(parts) if parts else "nothing to check"


def worst(states: Iterable[str]) -> Optional[str]:
    """The state a folder (a .blend, a collection) shows: the first one a hand
    is needed for, in :data:`STATE_ORDER`."""
    got = set(states)
    for k in STATE_ORDER:
        if k in got:
            return k
    return None


# ── point 1 · who may save a .blend ──────────────────────────────────────────

#: where a Blender with its interface says it has a .blend open: one small
#: file per .blend in a folder of this user on this computer. Blender itself
#: leaves NOTHING (no lock, no open descriptor — measured on 5.2, 30 Oct 2026),
#: and the file is never beside the .blend: rewritten every few seconds in a
#: OneDrive folder it would be uploaded every few seconds.
SESSIONS_DIR = (".stratigraph", "blender-sessions")
#: a presence older than this is a Blender that ended without saying so
PRESENCE_STALE_S = 90


def sessions_dir(home: Optional[str] = None) -> str:
    return os.path.join(home or os.path.expanduser("~"), *SESSIONS_DIR)


def session_file(blend: str, home: Optional[str] = None) -> str:
    """The presence file of a .blend: named by the sha1 of its real path."""
    import hashlib
    real = os.path.realpath(blend) if blend else ""
    return os.path.join(sessions_dir(home), hashlib.sha1(real.encode("utf-8")).hexdigest()[:16] + ".json")


def session_record(blend: str, *, dirty: bool, pid: int, host: str, now: float,
                   version: str = "", sidecar_port: int = 0) -> Dict[str, Any]:
    """What a Blender with its interface says of itself."""
    return {"blend": os.path.realpath(blend) if blend else "", "dirty": bool(dirty), "pid": int(pid),
            "host": host, "at": now, "blender": version, "sidecar_port": int(sidecar_port or 0)}


def read_session(blend: str, home: Optional[str] = None) -> Optional[Dict[str, Any]]:
    import json
    try:
        with open(session_file(blend, home), "r", encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else None
    except (OSError, ValueError):
        return None


def pid_alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:      # alive, another user's
        return True
    except (OSError, ValueError, TypeError):
        return False


def session_state(blend: str, *, now: Optional[float] = None, host: str = "",
                  read_mtime: Optional[float] = None, home: Optional[str] = None) -> Dict[str, Any]:
    """:func:`save_rule` for a .blend on this computer, read from its presence
    file and its mtime. → the rule's answer plus ``presence``."""
    import platform
    import time
    pres = read_session(blend, home)
    host = host or platform.node()
    alive = None
    if pres and (not pres.get("host") or pres.get("host") == host):
        alive = pid_alive(pres.get("pid"))
    try:
        mtime = os.path.getmtime(blend)
    except OSError:
        mtime = None
    out = save_rule(presence=pres, now=time.time() if now is None else now, host=host,
                    pid_alive=alive, mtime=mtime, read_mtime=read_mtime)
    out["presence"] = pres
    out["mtime"] = mtime
    return out


def save_rule(*, presence: Optional[Dict[str, Any]], now: float, host: str = "",
              pid_alive: Optional[bool] = None, mtime: Optional[float] = None,
              read_mtime: Optional[float] = None) -> Dict[str, Any]:
    """Who may save the .blend, said before a job starts (MICRO point 1).

    Measured on Blender 5.2 (30 Oct 2026): a headless Blender READS a .blend
    open in another Blender without trouble and sees the SAVED file (not the
    unsaved changes); it can also SAVE it, silently; and the other Blender,
    saving later, overwrites that save without a word (no lock, no warning,
    no reload). So the rule is ours:

    * ``read`` is always allowed (it reads the saved file: when the session
      has unsaved changes, it says «save first» to read them);
    * ``save`` is allowed only to the session that has the file open — a
      background job that would change the .blend goes TO that session (the
      sidecar) or waits for it to close; with no live session it may save,
      after checking the file did not change since it was read (``mtime`` vs
      ``read_mtime``).

    ``presence``: the session file's content (``{pid, host, dirty, at,
    blend}``) or None; ``pid_alive``: whether that pid lives (same host
    only). → ``{read, save, route, say, dirty}`` with ``route`` one of
    ``session`` (send it to the open Blender), ``background`` (a headless
    Blender may do it, with confirmation), ``refuse`` (the file changed under
    the job)."""
    live = False
    dirty = False
    who = ""
    if presence:
        age = now - float(presence.get("at") or 0)
        same_host = not host or not presence.get("host") or presence.get("host") == host
        live = age <= PRESENCE_STALE_S and (pid_alive is not False if same_host else True)
        dirty = bool(presence.get("dirty")) and live
        who = str(presence.get("host") or "")
    if read_mtime is not None and mtime is not None and abs(float(mtime) - float(read_mtime)) > 1e-3:
        return {"read": True, "save": False, "route": "refuse", "dirty": dirty, "live": live,
                "say": "the .blend changed on disk since it was read: read it again"}
    if live:
        say = "open in Blender" + (f" on {who}" if who and host and who != host else "")
        if dirty:
            say += " with unsaved changes: what is read is the saved file — save in Blender first"
        return {"read": True, "save": False, "route": "session", "dirty": dirty, "live": True,
                "say": say + "; changes go to that Blender, never a second save"}
    return {"read": True, "save": True, "route": "background", "dirty": False, "live": False,
            "say": "no Blender has it open: a background Blender may change it (after you confirm)"}


# ── point 4 · where a master goes ────────────────────────────────────────────

def master_folder(project_root: str, branch: str, container: str) -> str:
    """``<root>/<SB|RB>/<Container>/master/`` — the default convention, not an
    invariant: a file elsewhere is lawful if the graph registers it."""
    safe = re.sub(r"[^A-Za-z0-9 ._-]+", "_", str(container or "")).strip(" ._") or "Container"
    return os.path.join(project_root, branch, safe, "master")


def master_format(branch: str) -> Dict[str, Any]:
    """The master's format by branch (the decision): glTF with EXTERNAL
    textures for the source-based reconstruction (SB), OBJ + textures for the
    reality-based survey (RB; PLY when it has no UVs)."""
    if str(branch).upper() == "RB":
        return {"format": "obj", "ext": ".obj", "textures": "external", "alt": "ply"}
    return {"format": "gltf", "ext": ".gltf", "textures": "external", "alt": None}


def branch_of(blend_or_path: str, project_root: str = "") -> str:
    """SB or RB from where a file sits in the project's tree (``SB/…``,
    ``RB/…``); SB when it cannot be told (a reconstruction is the common
    case)."""
    rel = _rel(_norm(blend_or_path), _norm(project_root)) if project_root else _norm(blend_or_path)
    for part in rel.split("/"):
        if part.upper() in ("SB", "RB"):
            return part.upper()
    return "SB"
