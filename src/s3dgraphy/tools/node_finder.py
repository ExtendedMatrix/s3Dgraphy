"""N1 · find a StratiGraph node: this computer, the local network, the saved
ones, one typed by hand — and say in one sentence what to do.

Shared by EMStudio (through its bridge) and EM Tools, so the panel «Choose the
node» answers the same in both (decided by E.D., 4 Oct 2026).

**The local network without a new dependency** (measured 4 Oct 2026): Blender's
Python and the bridge's have no ``zeroconf``; macOS ships ``dns-sd`` and Linux
desktops ``avahi-browse``. :func:`browse_lan` asks whichever is there for
``_stratigraph._tcp`` and says which it used; with neither, it says that the
network cannot be browsed from here and the panel falls back to «this
computer» and the saved list — never a discovery pretending to have browsed.
A node announces itself only when its owner opened it to the network
(:data:`SERVICE`, ``stratigraph-server/scripts/personal_node.py --lan``).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Iterable, List, Optional

#: the DNS-SD service type a StratiGraph node announces
SERVICE = "_stratigraph._tcp"

#: where a node on THIS computer answers: the personal node, the dev stack
#: (server port and Caddy), in this order
LOCAL_CANDIDATES = ("http://127.0.0.1:8777", "http://localhost:8000",
                    "https://em.localhost:8443/em")

SENTENCES = {
    "local": {"it": "Sul tuo computer c'è un nodo acceso: usalo per lavorare offline.",
              "en": "There is a node running on your computer: use it to work offline."},
    "lan": {"it": "C'è un nodo nella rete locale: entra in una sua stanza per lavorare con gli altri.",
            "en": "There is a node on the local network: enter one of its rooms to work with the others."},
    "saved": {"it": "Un nodo salvato risponde: puoi entrare nelle sue stanze.",
              "en": "A saved node answers: you can enter its rooms."},
    "none": {"it": "Nessun nodo trovato: lavora sul computer, potrai portare il progetto in una stanza più tardi.",
             "en": "No node found: work on this computer, you can bring the project into a room later."},
    "personal": {"it": "Nodo personale: i file restano nelle tue cartelle; tienile su un disco salvato.",
                 "en": "Personal node: the files stay in your folders; keep them on a backed-up disk."},
    "real_node": {"it": "Lavori con altri o vuoi il nodo sempre acceso: installalo su un mini-PC del laboratorio.",
                  "en": "Working with others, or want the node always on: install it on a mini-PC of the lab."},
}


def _get_json(url: str, timeout: float) -> Optional[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}),
                                    timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — not there, not JSON, refused: no answer
        return None


def probe(base: str, *, timeout: float = 2.0,
          fetch: Optional[Callable[[str, float], Optional[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """What a node at ``base`` says of itself: reachable, version, profile and
    the ways in (``/v1/auth-config``). ``fetch`` replaces the network (tests)."""
    get = fetch or _get_json
    base = base.rstrip("/")
    health = get(f"{base}/health", timeout) or get(f"{base}/v1/health", timeout)
    out: Dict[str, Any] = {"url": base, "reachable": bool(health and health.get("ok", True))}
    if not out["reachable"]:
        return out
    out["version"] = str(health.get("version") or "")
    out["s3dgraphy"] = str(health.get("s3dgraphy") or "")
    out["profile"] = str(health.get("profile") or ("dev" if health.get("auth") in ("dev", "none")
                                                   else "node"))
    out["rooms"] = health.get("rooms")
    auth = get(f"{base}/v1/auth-config", timeout) or {}
    ways = []
    if auth.get("enforcing"):
        ways.append("node_password")
        if auth.get("orcid_idp_ready"):
            ways.append("orcid")
    else:
        ways.append("open")                       # dev / personal: no identity asked
    out["ways_in"] = ways
    return out


def parse_dns_sd(text: str) -> List[Dict[str, str]]:
    """The instances of ``dns-sd -B _stratigraph._tcp`` output (macOS)."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\S+\s+Add\s+\S+\s+\S+\s+(\S+)\.\s+" + re.escape(SERVICE) + r"\.\s+(.+)$",
                     line.strip())
        if m:
            out.append({"domain": m.group(1), "name": m.group(2).strip()})
    return out


def parse_avahi(text: str) -> List[Dict[str, str]]:
    """The resolved lines of ``avahi-browse -rpt _stratigraph._tcp`` (Linux):
    ``=;iface;proto;name;type;domain;host;address;port;txt``."""
    out = []
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) >= 9 and parts[0] == "=":
            out.append({"name": parts[3], "host": parts[6], "address": parts[7], "port": parts[8],
                        "txt": parts[9] if len(parts) > 9 else ""})
    return out


def url_of(host: str, port: str, txt: str = "") -> str:
    """The node's address from what DNS-SD gives: host, port and the TXT keys
    ``scheme`` (default ``http``) and ``path`` (default none). The personal node
    announces ``path=/``; the dev stack behind Caddy announces ``scheme=https
    path=/em`` (``fcn-up.sh``), because that port answers https and the API
    lives under ``/em`` — ``http://host:8443`` would be a node that never answers."""
    keys = dict(m.groups() for m in re.finditer(r'"?([A-Za-z][\w-]*)=([^"\s]*)"?', txt or ""))
    scheme = keys.get("scheme") if keys.get("scheme") in ("http", "https") else "http"
    path = (keys.get("path") or "").rstrip("/")
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{scheme}://{host.rstrip('.')}:{port}{path}"


def browse_lan(timeout: float = 3.0, *, tool: Optional[str] = None,
               runner: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """The nodes that announce themselves on the local network.

    → ``{how, found: [{name, url?}], note}``: ``how`` is ``dns-sd``,
    ``avahi-browse`` or ``none`` (and then ``note`` says why). ``tool`` and
    ``runner`` replace what this computer has (tests)."""
    run = runner or subprocess.run
    tool = tool or ("avahi-browse" if shutil.which("avahi-browse")
                    else "dns-sd" if shutil.which("dns-sd") else None)
    if tool == "avahi-browse":
        try:
            done = run(["avahi-browse", "-rpt", SERVICE], capture_output=True, text=True,
                       timeout=timeout)
            found = [{"name": f["name"], "url": url_of(f["host"], f["port"], f.get("txt", ""))}
                     for f in parse_avahi(done.stdout)]
            return {"how": "avahi-browse", "found": found, "note": ""}
        except Exception as exc:  # noqa: BLE001
            return {"how": "avahi-browse", "found": [], "note": str(exc)}
    if tool == "dns-sd":
        try:
            done = run(["dns-sd", "-B", SERVICE, "local."], capture_output=True, text=True,
                       timeout=timeout)
            text = done.stdout
        except subprocess.TimeoutExpired as exc:          # dns-sd browses until killed
            text = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        except Exception as exc:  # noqa: BLE001
            return {"how": "dns-sd", "found": [], "note": str(exc)}
        found = []
        for inst in parse_dns_sd(text):
            url = resolve_dns_sd(inst["name"], timeout=timeout, runner=runner)
            found.append({"name": inst["name"], **({"url": url} if url else {})})
        return {"how": "dns-sd", "found": found, "note": ""}
    return {"how": "none", "found": [],
            "note": "this computer has neither dns-sd nor avahi-browse: the local "
                    "network cannot be browsed from here (type the address)"}


def resolve_dns_sd(name: str, *, timeout: float = 3.0,
                   runner: Optional[Callable[..., Any]] = None) -> Optional[str]:
    """``dns-sd -L <name>`` → ``<scheme>://<host>:<port><path>`` (:func:`url_of`;
    the TXT record is the line after «can be reached at»), or None."""
    run = runner or subprocess.run
    try:
        done = run(["dns-sd", "-L", name, SERVICE, "local."], capture_output=True, text=True,
                   timeout=timeout)
        text = done.stdout
    except subprocess.TimeoutExpired as exc:
        text = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"can be reached at (\S+?)\.?:(\d+)[^\n]*\n?([^\n]*)", text)
    if not m:
        return None
    txt = m.group(3) if "=" in m.group(3) and "can be reached" not in m.group(3) else ""
    return url_of(m.group(1), m.group(2), txt)


def find_nodes(*, saved: Iterable[str] = (), typed: str = "", lan: bool = True,
               timeout: float = 2.0, prober: Optional[Callable[[str], Dict[str, Any]]] = None,
               browser: Optional[Callable[[], Dict[str, Any]]] = None,
               lang: str = "it") -> Dict[str, Any]:
    """«Choose the node»: four groups, each node probed, and the sentence.

    → ``{local: [...], lan: [...], saved: [...], typed: [...], lan_how, lan_note,
    suggestion, suggestion_key}``; each node ``{url, reachable, version,
    profile, ways_in, …}``."""
    look = prober or (lambda u: probe(u, timeout=timeout))
    local = [p for p in (look(u) for u in LOCAL_CANDIDATES) if p["reachable"]]
    seen = {p["url"] for p in local}
    lan_answer = (browser or (lambda: browse_lan(timeout + 1)))() if lan else \
        {"how": "off", "found": [], "note": ""}
    lan_nodes = []
    for f in lan_answer["found"]:
        if f.get("url") and f["url"] not in seen:
            p = look(f["url"])
            p["name"] = f["name"]
            lan_nodes.append(p)
            seen.add(f["url"])
    saved_nodes = [look(u) for u in saved if u and u.rstrip("/") not in seen]
    typed_nodes = [look(typed)] if typed.strip() else []
    if local:
        key = "personal" if any(p.get("profile") == "personal" for p in local) else "local"
    elif any(p["reachable"] for p in lan_nodes):
        key = "lan"
    elif any(p["reachable"] for p in saved_nodes + typed_nodes):
        key = "saved"
    else:
        key = "none"
    return {"local": local, "lan": lan_nodes, "saved": saved_nodes, "typed": typed_nodes,
            "lan_how": lan_answer["how"], "lan_note": lan_answer["note"],
            "suggestion_key": key, "suggestion": SENTENCES[key][lang if lang in ("it", "en") else "en"],
            "real_node": SENTENCES["real_node"][lang if lang in ("it", "en") else "en"]}
