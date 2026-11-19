"""The plugins on the node — third parties' code run for a room, in a cage (X7).

MICRO-PL27-PLUGIN-SUL-NODO, row X7 of the extensions plan (E.D., 18–19 Nov
2026): «plugins on the server side, installed by the administrator from a
repository, run per room with isolation (process, quotas, time)», and the
decision of phase 2: **with serious isolation or it does not turn on**.
SPEC-plugin §10 and §14.6: on the web there is no Python of the user's; a
plugin there is third parties' code on a shared server, beside the rooms of
others. What this module is (the library's half; the routes are the node's):

* **installed by the administrator** — with the same library and the same
  commands as a desktop (``python -m s3dgraphy.extensions repo install …``,
  ``enable``), in the node's folders (``S3DGRAPHY_EXTENSIONS_DIR``,
  ``S3DGRAPHY_PLUGINS_DIR`` on the node's volume). Only a code that names
  ``server`` in its ``hosts`` is a plugin of the node (an empty ``hosts`` is
  NOT read as «everywhere» here), and only one that asks neither the
  ``network`` nor ``processes`` permission (:func:`eligible`): the cage takes
  both away, a plugin that needs them would only fail;
* **turned on per room** (:func:`set_room`): a room has none until its owner
  turns one on (``rooms.json`` in the node's folder, who and when);
* **run in a cage** (:func:`run`): one process per call, started fresh
  (``python -I -B``, a clean environment, a work dir that dies with the
  call), under the machine's sandbox — **bubblewrap** on Linux (no network,
  no other process, only the interpreter, the library and the plugin's folder
  visible, read only), **sandbox-exec** on macOS (the developer's machine) —
  with the limits put by the process on itself before the plugin is imported:
  CPU seconds, memory (where the system keeps the limit: not macOS), file
  size, open files; the wall clock is the server's (the whole process group
  killed). The room's document goes in as a COPY; what the command writes
  comes back as deltas, never applied there;
* **quotas per room** (:func:`quota`): calls per minute, CPU seconds per
  hour, one call at a time per room, a few at a time on the node;
* **the seriousness proved, not promised** (:func:`isolation`): the cage is
  tested by a probe that tries every way out — a socket to the server, a file
  written outside its folder, a file of the node read, a process of its own,
  memory beyond the limit. Any escape, or a sandbox that does not start, and
  the plugins of the node stay OFF (``node_isolation_off``), with the reason.
  ``S3DGRAPHY_NODE_SANDBOX=none`` exists for tests and is never serious;
* **the answer is not trusted**: the plugin owns its process, so it may write
  any ``result.json``. :func:`deltas` re-reads the deltas, rewrites their
  author (the room's person) and their process (the DTC: plugin and version
  as the instrument, ``host: server``), refuses every delta of a command
  declared ``writes = false``, and the node applies them through the seam
  (:func:`apply_to_section`: :func:`s3dgraphy.contract.apply_delta`, the
  plugin's declared capabilities, transport ``cloud``), as a connector.

What it is NOT: a way to run the person's own code on the node (there is no
console on the web), nor a store of the plugins' state (``ctx.data_dir`` is
the call's scratch folder: a plugin of the node keeps nothing between calls).
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Mapping, Optional, Tuple

from ..profiles.problems import ERROR, WARNING, Problem
from . import store

NODE_ENV = "S3DGRAPHY_NODE_DIR"
SANDBOX_ENV = "S3DGRAPHY_NODE_SANDBOX"
#: more folders of the node a plugin must never read (``:``-separated)
PROTECT_ENV = "S3DGRAPHY_NODE_PROTECT"
HOST = "server"
BACKENDS = ("bwrap", "sandbox-exec", "none")
#: the permissions the cage takes away: a plugin asking them is not one of the node's
DENIED_PERMISSIONS = ("network", "processes")
#: every way out the probe tries; an escape anywhere = not serious
PROBES = ("network", "write_outside", "read_protected", "spawn", "cpu", "memory")
#: the probes a system may not be able to enforce, said instead of refusing (macOS keeps no RLIMIT_AS)
SAID_ONLY = {"darwin": ("memory",)}

DEFAULT_LIMITS: Dict[str, float] = {
    "wall_s": 10, "cpu_s": 5, "memory_mb": 512, "file_mb": 16, "open_files": 64, "output_kb": 1024,
    "document_mb": 64, "calls_per_minute": 30, "cpu_s_per_hour": 120, "concurrent_room": 1, "concurrent_node": 4,
}

_CHILD = Path(__file__).with_name("_node_child.py")


class NodeError(Exception):
    """A refusal of the node, with its code and its two sentences."""

    def __init__(self, code: str, **params: Any):
        self.code, self.params = code, params
        self.messages = _both(code, **params)
        super().__init__(self.messages["en"])

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": False, "reason": self.code, "messages": dict(self.messages)}


def _both(code: str, **params: Any) -> Dict[str, str]:
    pr = Problem(code, ERROR, "", params)
    return {"en": pr.text("en"), "it": pr.text("it")}


def _problem(code: str, level: str = ERROR, **params: Any) -> Dict[str, Any]:
    return {"code": code, "level": level, **_both(code, **params)}


# ── the node's folder ───────────────────────────────────────────────────────

def node_dir() -> Path:
    env = os.environ.get(NODE_ENV)
    return Path(env).expanduser() if env else store.extensions_dir() / "node"


def _read(path: Path) -> Dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def limits(room: Optional[str] = None) -> Dict[str, float]:
    """The limits: the defaults, the node's (``node.json`` ``limits``, the
    administrator's), a room's own (``rooms.json``) — a room may only LOWER
    the node's, never raise them."""
    out = dict(DEFAULT_LIMITS)
    for k, v in (_read(node_dir() / "node.json").get("limits") or {}).items():
        if k in out and isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            out[k] = v
    if room:
        for k, v in ((_rooms().get(room) or {}).get("limits") or {}).items():
            if k in out and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < out[k]:
                out[k] = v
    return out


def set_limits(changes: Mapping[str, Any], *, room: Optional[str] = None) -> Dict[str, float]:
    """The administrator's limits (``room=None``) or a room's lower ones."""
    bad = [k for k, v in changes.items() if k not in DEFAULT_LIMITS
           or not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0]
    if bad:
        raise NodeError("node_limit_bad", keys=", ".join(sorted(bad)), allowed=", ".join(DEFAULT_LIMITS))
    if room is None:
        path = node_dir() / "node.json"
        doc = _read(path)
        doc["limits"] = {**(doc.get("limits") or {}), **dict(changes)}
        _save(path, doc)
    else:
        doc = _rooms()
        r = doc.setdefault(room, {})
        r["limits"] = {**(r.get("limits") or {}), **dict(changes)}
        _save_rooms(doc)
    return limits(room)


# ── the cage ────────────────────────────────────────────────────────────────

def _protected() -> List[str]:
    """What a plugin never reads: the node's folder (the rooms' state, the
    probe's secret), the register and the repositories with their tokens,
    and the administrator's list."""
    out = [str(node_dir()), str(store.extensions_dir())]
    out += [p for p in os.environ.get(PROTECT_ENV, "").split(os.pathsep) if p.strip()]
    return [os.path.realpath(p) for p in out]


def backend() -> str:
    """The sandbox of this machine: the one named (``S3DGRAPHY_NODE_SANDBOX``),
    else bubblewrap on Linux, sandbox-exec on macOS, else ``none``."""
    want = os.environ.get(SANDBOX_ENV, "auto").strip() or "auto"
    if want != "auto":
        return want
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return "bwrap"
    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists():
        return "sandbox-exec"
    return "none"


def _sbpl(work: str, readable: List[str]) -> str:
    """The macOS profile: everything as the user, minus the network, minus
    every write but the work dir, minus every process but this interpreter,
    minus reading the node's folders (the work dir read again after)."""
    q = lambda p: json.dumps(os.path.realpath(p))           # noqa: E731 — SBPL strings are JSON strings
    lines = ["(version 1)", "(allow default)", "(deny network*)", "(deny file-write*)",
             f"(allow file-write* (subpath {q(work)}) (literal \"/dev/null\"))",
             "(deny process-fork)", "(deny process-exec*)",
             f"(allow process-exec* (literal {q(sys.executable)}) (literal {q(os.path.realpath(sys.executable))})"
             # a framework build re-executes itself in place (Python.app): the interpreter's own tree
             f" (subpath {q(sys.base_prefix)}))"]
    for p in _protected():
        lines.append(f"(deny file-read* (subpath {q(p)}))")
    for p in [work] + readable:
        lines.append(f"(allow file-read* (subpath {q(p)}))")
    return "\n".join(lines) + "\n"


def _bwrap(work: str, readable: List[str], env: Mapping[str, str]) -> List[str]:
    """The Linux cage: new namespaces for everything (no network, its own
    pids), a fresh /tmp, /proc and /dev, only the system's libraries, the
    interpreter, the library and the plugin visible — read only — and the
    work dir writable. The node's folders are simply not there."""
    args = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for k, v in sorted(env.items()):                        # --clearenv: the environment said again here
        args += ["--setenv", k, v]
    seen = set()
    roots = ["/usr", "/lib", "/lib64", "/bin", "/etc/ld.so.cache", "/etc/localtime",
             sys.prefix, sys.base_prefix, os.path.dirname(os.path.realpath(sys.executable))] + readable
    for p in roots:
        rp = os.path.realpath(p)
        if rp in seen or not os.path.exists(rp):
            continue
        seen.add(rp)
        args += ["--ro-bind", rp, rp]
        if p != rp and os.path.isabs(p) and p not in seen:
            seen.add(p)
            args += ["--symlink", rp, p]
    args += ["--bind", work, work, "--chdir", work]
    return args + ["--"]


def _command(work: str, mode: str, readable: List[str], which: Optional[str] = None) -> List[str]:
    py = [sys.executable, "-I", "-B", str(_CHILD), work, mode]
    b = which or backend()
    if b == "bwrap":
        return _bwrap(work, readable, _env(work)) + py
    if b == "sandbox-exec":
        prof = Path(work).parent / (Path(work).name + ".sb")
        prof.write_text(_sbpl(work, readable), encoding="utf-8")
        return ["/usr/bin/sandbox-exec", "-f", str(prof)] + py
    if b == "none":
        return py
    raise NodeError("node_sandbox_unknown", name=b, known=", ".join(BACKENDS))


def _env(work: str) -> Dict[str, str]:
    out = os.path.join(work, "out")
    env = {"PATH": "/usr/bin:/bin", "HOME": out, "TMPDIR": out, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}
    # the data a plugin may read (packages A/B, vocabularies): the node's own folders for them
    for k in ("S3DGRAPHY_PROFILES_DIR", "EM_VOCABULARIES_DIR", "S3DGRAPHY_PLUGINS_DIR"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    env[store.EXTENSIONS_ENV] = os.path.join(out, "extensions")     # never the node's register
    return env


def _readable() -> List[str]:
    """What the child must read: the library (and its dependencies, through
    the interpreter's prefix), the plugins' folder, the data folders."""
    lib = str(Path(__file__).resolve().parents[2])
    out = [lib, str(store.plugins_dir())]
    for k in ("S3DGRAPHY_PROFILES_DIR", "EM_VOCABULARIES_DIR"):
        if os.environ.get(k):
            out.append(os.environ[k])
    return [os.path.realpath(p) for p in out if os.path.exists(p)]


def _spawn(job: Dict[str, Any], mode: str, lim: Mapping[str, float], *, which: Optional[str] = None,
           document: Optional[bytes] = None) -> Dict[str, Any]:
    """One child, in its work dir, under the cage; the wall clock kept here.
    Returns the child's result (or a reason of ours) with ``wall_s``,
    ``cpu_s`` (measured by the kernel for that pid, not said by the child)."""
    base = node_dir() / "work"
    base.mkdir(parents=True, exist_ok=True)
    work = os.path.realpath(tempfile.mkdtemp(prefix="run-", dir=str(base)))
    try:
        os.makedirs(os.path.join(work, "out"), exist_ok=True)
        job = dict(job, limits=dict(lim), sys_path=[str(Path(__file__).resolve().parents[2])])
        Path(work, "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        if document is not None:
            Path(work, "document.em.json").write_bytes(document)
        cmd = _command(work, mode, _readable(), which)
        log = open(os.path.join(work + ".log"), "wb")
        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=_env(work),
                                    cwd=work, start_new_session=True, close_fds=True)
        except OSError as exc:
            log.close()
            return {"ok": False, "reason": "node_sandbox_failed", "error": str(exc), "wall_s": 0.0, "cpu_s": 0.0}
        status, ru, timed_out = _wait(proc.pid, float(lim["wall_s"]))
        proc.returncode = status
        wall = round(time.monotonic() - t0, 3)
        log.close()
        cpu = round(ru.ru_utime + ru.ru_stime, 3) if ru is not None else 0.0
        # ru_maxrss: bytes on macOS, kilobytes on Linux
        rss_mb = round(ru.ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1) if ru is not None else 0.0
        res_path = Path(work, "result.json")
        out: Dict[str, Any]
        if timed_out:
            out = {"ok": False, "reason": "node_timeout"}
        elif os.WIFSIGNALED(status) and os.WTERMSIG(status) in (signal.SIGXCPU, signal.SIGKILL) \
                and cpu >= float(lim["cpu_s"]) - 0.5:
            out = {"ok": False, "reason": "node_cpu"}
        elif not res_path.is_file():
            tail = Path(work + ".log").read_bytes()[-600:].decode("utf-8", "replace") \
                if Path(work + ".log").is_file() else ""
            reason = "node_crashed" if Path(work, "started").exists() else "node_sandbox_failed"
            out = {"ok": False, "reason": reason, "error": tail.strip()[-400:], "status": status}
        elif res_path.stat().st_size > float(lim["output_kb"]) * 1024:
            out = {"ok": False, "reason": "node_output", "size": res_path.stat().st_size}
        else:
            try:
                out = json.loads(res_path.read_text(encoding="utf-8"))
                if not isinstance(out, dict):
                    raise ValueError("not an object")
            except ValueError as exc:
                out = {"ok": False, "reason": "node_crashed", "error": f"result.json: {exc}"}
            if out.get("reason") == "memory":
                out["reason"] = "node_memory"
            elif out.get("reason") == "crashed":
                out["reason"] = "node_crashed"
        out["wall_s"], out["cpu_s"], out["max_rss_mb"] = wall, cpu, rss_mb
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)
        for extra in (work + ".log", work + ".sb"):
            try:
                os.unlink(extra)
            except OSError:
                pass


def _wait(pid: int, wall: float) -> Tuple[int, Any, bool]:
    """``os.wait4`` for that pid (its own rusage), the group killed at the wall."""
    deadline = time.monotonic() + wall
    delay = 0.005
    while True:
        try:
            got, status, ru = os.wait4(pid, os.WNOHANG)
        except ChildProcessError:
            return 0, None, False
        if got == pid:
            return status, ru, False
        if time.monotonic() >= deadline:
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            _got, status, ru = os.wait4(pid, 0)
            return status, ru, True
        time.sleep(delay)
        delay = min(delay * 2, 0.05)


_probe_cache: Dict[str, Dict[str, Any]] = {}


def isolation(*, refresh: bool = False, which: Optional[str] = None) -> Dict[str, Any]:
    """Is the cage serious on this machine? The probe runs the child in the
    cage and tries every way out (:data:`PROBES`); ``serious`` only when the
    sandbox started and nothing escaped (what the system cannot enforce, said:
    the memory on macOS). Kept for the process (``refresh`` asks again) and
    written to ``isolation.json`` for the administrator.

    ``{backend, serious, platform, checks: [{name, ok, said, how, en, it}],
    problems, at}``."""
    b = which or backend()
    key = f"{b}|{sys.executable}"
    if not refresh and key in _probe_cache:
        return _probe_cache[key]
    checks: List[Dict[str, Any]] = []
    problems: List[Dict[str, Any]] = []
    said_only = SAID_ONLY.get(sys.platform, ())
    if b not in BACKENDS:
        problems.append(_problem("node_sandbox_unknown", name=b, known=", ".join(BACKENDS)))
    elif b == "none":
        problems.append(_problem("node_sandbox_none"))
    if not problems or b == "none":
        secret_dir = node_dir() / "probe"
        secret_dir.mkdir(parents=True, exist_ok=True)
        secret = os.urandom(8).hex()
        (secret_dir / "secret.txt").write_text(secret, encoding="utf-8")
        outside = secret_dir / f"outside-{secret}.txt"
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        lim = dict(limits(), memory_mb=64, wall_s=20)
        try:
            got = _spawn({"probe": {"port": port, "outside": str(outside), "protected": str(secret_dir / "secret.txt"),
                                    "secret": secret}}, "probe", lim, which=b)
            cpu = _spawn({}, "probe-cpu", dict(lim, cpu_s=1, wall_s=8), which=b)
        finally:
            listener.close()
        wrote = outside.exists()
        for f in (outside, secret_dir / "secret.txt"):
            try:
                f.unlink()
            except OSError:
                pass
        probe = got.get("probe") if isinstance(got.get("probe"), dict) else None
        if probe is None:
            problems.append(_problem("node_probe_failed", backend=b, why=str(got.get("error") or got.get("reason"))[:300]))
        else:
            for name in PROBES:
                if name == "cpu":
                    held = cpu.get("reason") == "node_cpu"
                    how = f"{cpu.get('reason')} after {cpu.get('cpu_s')} s of CPU"
                else:
                    r = probe.get(name) or {}
                    held = not r.get("escaped") and not (name == "write_outside" and wrote)
                    how = str(r.get("how") or "")
                said = name in said_only and not held
                checks.append({"name": name, "ok": held, "said": said, "how": how,
                               **_both("node_probe_" + name + ("_ok" if held else "_escaped"))})
                if not held and not said:
                    problems.append(_problem("node_escape", name=name, how=how))
                elif said:
                    problems.append(_problem("node_not_enforced", WARNING, name=name, system=sys.platform))
    serious = b in ("bwrap", "sandbox-exec") and not any(p["level"] == ERROR for p in problems)
    out = {"backend": b, "serious": serious, "platform": sys.platform, "checks": checks, "problems": problems,
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _probe_cache[key] = out
    try:
        _save(node_dir() / "isolation.json", out)
    except OSError:
        pass
    return out


# ── the plugins of the node ─────────────────────────────────────────────────

def eligible(meta: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Why an installed code is NOT a plugin of the node (empty: it is)."""
    out: List[Dict[str, Any]] = []
    pid = str(meta.get("id") or "?")
    if HOST not in [str(h) for h in meta.get("hosts") or []]:
        out.append(_problem("node_not_server", id=pid))
    perms = ((meta.get("code") or {}).get("permissions") or {})
    for p in DENIED_PERMISSIONS:
        if isinstance(perms, dict) and p in perms:
            out.append(_problem("node_permission", id=pid, permission=p, why=str(perms.get(p) or "")))
    return out


def _rooms() -> Dict[str, Any]:
    return _read(node_dir() / "rooms.json").get("rooms") or {}


def _save_rooms(rooms: Mapping[str, Any]) -> None:
    _save(node_dir() / "rooms.json", {"format": "s3dgraphy/node-rooms", "format_version": "1", "rooms": dict(rooms)})


def _active() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for e in store.active_code(HOST):
        if HOST in (e.get("hosts") or []):            # active_code lets an empty hosts through: the node does not
            out[str(e["id"])] = e
    return out


def _meta_of(e: Mapping[str, Any]) -> Dict[str, Any]:
    from ..em.plugins import _meta
    return _meta(Path(str(e.get("folder"))))


def plugins(room: Optional[str] = None, *, lang: str = "en") -> List[Dict[str, Any]]:
    """The plugins of the node: active for ``server`` (the administrator's),
    each with ``eligible``, its problems, its commands and — for a room —
    whether it is on there. Never a path of the node's disk."""
    from ..em.plugins import read_commands
    on = ((_rooms().get(room) or {}).get("plugins") or {}) if room else {}
    out = []
    for pid, e in sorted(_active().items()):
        meta = _meta_of(e)
        probs = eligible(meta) if meta else [_problem("node_plugin_missing", id=pid)]
        cmds = read_commands(pid, meta.get("code") or {}) if meta else []
        d = (meta.get("code") or {}).get("descriptor") or {}
        row = {"id": pid, "version": str(e.get("version")), "source": str(e.get("source") or ""),
               "name": meta.get("name") or pid, "verified": bool(meta.get("verified")),
               "reviewed": meta.get("reviewed"), "eligible": not probs, "problems": probs,
               "capabilities": list(d.get("capabilities") or ["read-graph"]),
               "commands": [dict(c.as_dict(), label_text=c.label_in(lang)) for c in cmds]}
        if room is not None:
            r = on.get(pid) or {}
            row["on"] = bool(r.get("on")) and not probs
            row["turned_on"] = {k: r.get(k) for k in ("by", "at") if r.get(k)}
        out.append(row)
    return out


def set_room(room: str, plugin_id: str, on: bool, *, by: Optional[str] = None) -> Dict[str, Any]:
    """The room's owner turns a plugin of the node on (or off) for the room.
    Only a plugin of the node that is eligible can be turned on."""
    if not room or not isinstance(room, str):
        raise NodeError("node_room_bad", room=str(room))
    have = {p["id"]: p for p in plugins()}
    p = have.get(plugin_id)
    if on and p is None:
        raise NodeError("node_no_plugin", id=plugin_id)
    if on and not p["eligible"]:
        raise NodeError("node_not_eligible", id=plugin_id, why="; ".join(x["en"] for x in p["problems"]))
    doc = _rooms()
    r = doc.setdefault(room, {})
    pl = r.setdefault("plugins", {})
    if on:
        pl[plugin_id] = {"on": True, "by": by, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    else:
        pl.pop(plugin_id, None)
    _save_rooms(doc)
    return {"room": room, "id": plugin_id, "on": bool(on)}


def room_plugins(room: str) -> List[str]:
    return sorted(k for k, v in ((_rooms().get(room) or {}).get("plugins") or {}).items() if v.get("on"))


# ── quotas ──────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_ledger: Dict[str, Deque[Tuple[float, float]]] = {}
_running: Dict[str, int] = {}


def quota(room: str) -> Dict[str, Any]:
    """What the room used: calls in the last minute, CPU seconds in the last
    hour, calls running now — against its limits. Kept in the server's
    process (a restart starts the hour again)."""
    lim = limits(room)
    now = time.monotonic()
    with _lock:
        q = _ledger.get(room) or deque()
        while q and now - q[0][0] > 3600:
            q.popleft()
        calls = sum(1 for t, _c in q if now - t <= 60)
        cpu = round(sum(c for _t, c in q), 3)
        running = _running.get(room, 0)
    return {"calls_last_minute": calls, "cpu_s_last_hour": cpu, "running": running,
            "limits": {k: lim[k] for k in ("calls_per_minute", "cpu_s_per_hour", "concurrent_room",
                                           "wall_s", "cpu_s", "memory_mb")}}


def _take(room: str, lim: Mapping[str, float]) -> None:
    now = time.monotonic()
    with _lock:
        q = _ledger.setdefault(room, deque())
        while q and now - q[0][0] > 3600:
            q.popleft()
        if sum(1 for t, _c in q if now - t <= 60) >= lim["calls_per_minute"]:
            raise NodeError("node_quota_calls", room=room, n=int(lim["calls_per_minute"]))
        if sum(c for _t, c in q) >= lim["cpu_s_per_hour"]:
            raise NodeError("node_quota_cpu", room=room, n=lim["cpu_s_per_hour"])
        if _running.get(room, 0) >= lim["concurrent_room"]:
            raise NodeError("node_quota_busy", room=room)
        if sum(_running.values()) >= lim["concurrent_node"]:
            raise NodeError("node_quota_node", n=int(lim["concurrent_node"]))
        _running[room] = _running.get(room, 0) + 1
        q.append((now, 0.0))


def _give(room: str, cpu: float) -> None:
    with _lock:
        _running[room] = max(0, _running.get(room, 0) - 1)
        q = _ledger.setdefault(room, deque())
        if q:
            t, _c = q.pop()
            q.append((t, float(cpu)))


def reset_quotas() -> None:
    """Every room's usage forgotten (tests; the administrator)."""
    with _lock:
        _ledger.clear()
        _running.clear()


# ── running ─────────────────────────────────────────────────────────────────

def _document_bytes(document: Any, lim: Mapping[str, float]) -> Optional[bytes]:
    if document is None:
        return None
    if isinstance(document, (bytes, bytearray)):
        raw = bytes(document)
    elif isinstance(document, (str, os.PathLike)) and Path(document).is_file():
        raw = Path(document).read_bytes()
    elif isinstance(document, Mapping):
        raw = json.dumps(document, ensure_ascii=False).encode("utf-8")
    else:
        raise NodeError("node_document_bad", what=type(document).__name__)
    if len(raw) > float(lim["document_mb"]) * 1024 * 1024:
        raise NodeError("node_document_big", mb=lim["document_mb"])
    return raw


def run(room: str, plugin_id: str, command_id: str, slots: Optional[Mapping[str, Any]] = None, *,
        document: Any = None, author: Optional[str] = None, can_write: bool = True,
        lang: str = "en") -> Dict[str, Any]:
    """Run a command of a plugin of the node for a room, in the cage.

    ``document``: the room's em.json (bytes, a dict, a path) — the child gets a
    COPY. ``author``: the identity of the person calling, from the server's
    session (never a slot). ``can_write``: the person's role in the room lets
    them write (a command declared ``writes = true`` is refused before it runs
    when not).

    Returns ``{ok, reason?, messages {en, it}, message, value?, file?,
    deltas [{label, capability, delta}], wall_s, cpu_s, plugin {id, version},
    command}``. The deltas are NOT applied anywhere: :func:`deltas` reads
    them for the node, :func:`apply_to_section` applies them through the seam.
    A refusal is a result with ``ok: False`` and a ``reason`` (``node_*``, or
    the contract's), never an exception."""
    try:
        return _run(room, plugin_id, command_id, dict(slots or {}), document=document, author=author,
                    can_write=can_write, lang=lang)
    except NodeError as exc:
        out = exc.as_dict()
        out["message"] = out["messages"].get(lang[:2], out["messages"]["en"])
        return out


def _run(room: str, plugin_id: str, command_id: str, slots: Dict[str, Any], *, document: Any,
         author: Optional[str], can_write: bool, lang: str) -> Dict[str, Any]:
    iso = isolation()
    if not iso["serious"]:
        why = "; ".join(p["en"] for p in iso["problems"] if p["level"] == ERROR) or iso["backend"]
        raise NodeError("node_isolation_off", backend=iso["backend"], why=why)
    active = _active()
    e = active.get(plugin_id)
    if e is None:
        raise NodeError("node_no_plugin", id=plugin_id)
    meta = _meta_of(e)
    probs = eligible(meta) if meta else [_problem("node_plugin_missing", id=plugin_id)]
    if probs:
        raise NodeError("node_not_eligible", id=plugin_id, why="; ".join(p["en"] for p in probs))
    if plugin_id not in room_plugins(room):
        raise NodeError("node_not_in_room", id=plugin_id, room=room)
    from ..em.plugins import read_commands
    cmds = {c.id: c for c in read_commands(plugin_id, meta.get("code") or {})}
    cmd = cmds.get(command_id)
    if cmd is None:
        raise NodeError("node_no_command", id=plugin_id, command=command_id)
    if cmd.writes and not can_write:
        raise NodeError("node_role_read_only", command=cmd.name, room=room)
    lim = limits(room)
    raw = _document_bytes(document, lim)
    _take(room, lim)
    cpu = 0.0
    try:
        job = {"plugin": {"id": plugin_id, "version": str(e.get("version")), "source": str(e.get("source") or ""),
                          "folder": os.path.realpath(str(e.get("folder"))), "meta": meta,
                          "module": e.get("module") or meta.get("module") or "",
                          "entry": e.get("entry") or meta.get("entry") or ""},
               "command": command_id, "slots": slots, "author": author, "lang": lang}
        got = _spawn(job, "run", lim, document=raw)
        cpu = float(got.get("cpu_s") or 0.0)
    finally:
        _give(room, cpu)
    out: Dict[str, Any] = {"plugin": {"id": plugin_id, "version": str(e.get("version"))}, "command": cmd.name,
                           "wall_s": got.get("wall_s"), "cpu_s": got.get("cpu_s"),
                           "max_rss_mb": got.get("max_rss_mb"), "room": room}
    reason = got.get("reason")
    if reason and str(reason).startswith("node_"):
        msgs = _both(str(reason), id=plugin_id, command=cmd.name, wall=lim["wall_s"], cpu=lim["cpu_s"],
                     mb=lim["memory_mb"], kb=lim["output_kb"], error=str(got.get("error") or "")[:300])
        out.update(ok=False, reason=reason, messages=msgs, message=msgs.get(lang[:2], msgs["en"]))
        return out
    data = got.get("data") if isinstance(got.get("data"), dict) else {}
    msgs = data.get("messages") if isinstance(data.get("messages"), dict) else None
    out.update(ok=bool(got.get("ok")), message=str(got.get("message") or ""),
               messages=msgs or {"en": str(got.get("message") or ""), "it": str(got.get("message") or "")})
    if not out["ok"]:
        out["reason"] = str(data.get("reason") or "refused")
        if got.get("problems"):
            out["problems"] = got["problems"]
    for k in ("value", "file"):
        if k in data:
            out[k] = data[k]
    out["deltas"] = [d for d in (got.get("deltas") or []) if isinstance(d, dict)]
    if not cmd.writes and out["deltas"]:
        # the child said a read-only command wrote: never believed, never applied
        msgs = _both("node_read_only_wrote", command=cmd.name)
        out.update(ok=False, reason="node_read_only_wrote", deltas=[], messages=msgs,
                   message=msgs.get(lang[:2], msgs["en"]))
    return out


def descriptor(plugin_id: str, *, room: Optional[str] = None):
    """The plugin as a connector of the node: its declared capabilities,
    transport ``cloud``, ``host: server`` in its vendor (the DTC's instrument)."""
    from .. import __version__
    from ..contract.connector import ConnectorDescriptor, current_versions
    e = _active().get(plugin_id)
    if e is None:
        raise NodeError("node_no_plugin", id=plugin_id)
    meta = _meta_of(e)
    d = (meta.get("code") or {}).get("descriptor") or {}
    return ConnectorDescriptor(
        name=plugin_id, host="app-side", transport=["cloud"],
        capabilities=list(d.get("capabilities") or ["read-graph"]), versions=current_versions(),
        provenance=str(d.get("provenance") or "derivation"), service="app",
        description=f"plugin {plugin_id} {e.get('version')} on the node",
        vendor={"version": str(e.get("version")), "plugin": plugin_id, "source": str(e.get("source") or ""),
                "verified": bool(meta.get("verified")), "host": HOST, "room": room, "s3dgraphy": __version__})


def deltas(result: Mapping[str, Any], *, author: Optional[str]) -> List[Tuple[str, Any]]:
    """The deltas of a run as the node applies them: ``[(capability, Delta)]``.
    The child's word is not taken: the author is the room's person (``author``),
    the process (DTC) is written here, the capability follows the delta
    (``ingest-batch`` for a proposal), a read-only command's deltas are none."""
    from ..contract import Delta
    from ..em.host import process_of
    if not result.get("ok") or not result.get("deltas"):
        return []
    pid = str((result.get("plugin") or {}).get("id") or "")
    desc = descriptor(pid, room=result.get("room"))
    out = []
    for entry in result["deltas"]:
        if not isinstance(entry, dict):
            continue
        d = Delta.from_dict(entry.get("delta") if isinstance(entry.get("delta"), dict) else {})
        d.author = author
        d.process = process_of(desc, str(entry.get("label") or result.get("command") or pid)[:200], host=HOST)
        d.process["command"] = result.get("command")
        out.append(("ingest-batch" if d.volatile else "write-graph", d))
    return out


def apply_to_section(section: Dict[str, Any], result: Mapping[str, Any], *, author: Optional[str]) -> List[Any]:
    """Apply a run's deltas to a room's graph section, through the seam, as the
    plugin (its declared capabilities, transport ``cloud``): each one a
    :class:`~s3dgraphy.contract.Result` — a refused one leaves the section as
    it was. What the node does after a run (the room's ops, its broadcast)
    is the node's."""
    from ..contract.connector import apply_delta
    pid = str((result.get("plugin") or {}).get("id") or "")
    desc = descriptor(pid, room=result.get("room"))
    return [apply_delta(section, desc, cap, d) for cap, d in deltas(result, author=author)]


def describe(room: Optional[str] = None, *, lang: str = "en") -> Dict[str, Any]:
    """What the page reads (``GET /v1/plugins``): the cage's state (no path),
    the plugins of the node, the room's quota."""
    iso = isolation()
    out: Dict[str, Any] = {"host": HOST, "isolation": {"backend": iso["backend"], "serious": iso["serious"],
                                                       "problems": iso["problems"], "at": iso["at"]},
                           "plugins": plugins(room, lang=lang)}
    if room is not None:
        out["room"] = room
        out["quota"] = quota(room)
    return out


__all__ = ["NODE_ENV", "SANDBOX_ENV", "PROTECT_ENV", "HOST", "BACKENDS", "PROBES", "DEFAULT_LIMITS",
           "DENIED_PERMISSIONS", "NodeError", "node_dir", "limits", "set_limits", "backend", "isolation",
           "eligible", "plugins", "set_room", "room_plugins", "quota", "reset_quotas", "run", "descriptor",
           "deltas", "apply_to_section", "describe"]
