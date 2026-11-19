"""The child of a plugin's run on the node — what runs INSIDE the cage (X7).

MICRO-PL27-PLUGIN-SUL-NODO. Started by :func:`s3dgraphy.extensions.node.run`
as ``python -I -B <this file> <work dir> run|probe`` under the sandbox of the
machine (bubblewrap on Linux, ``sandbox-exec`` on macOS); never imported by
the server. It reads ``job.json`` from the work dir, puts the limits on itself
BEFORE anything of the plugin is imported (CPU, memory, file size, open files,
no core), and writes ``result.json`` beside it. The plugin's own state is the
work dir's ``out/`` — a scratch folder that dies with the run.

``run``: the room's document (``document.em.json``, a copy) is opened, a host
that applies every ``em.write`` to that copy AND keeps its delta is
installed, the plugin is loaded as the desktop loads it
(:mod:`s3dgraphy.em.plugins`) and its command is invoked through the
contract. The server gets the deltas back and applies them to the room itself,
as a ``cloud`` connector: nothing written here reaches a room.

``probe``: the self-test of the cage — every escape is tried and its outcome
written (:data:`s3dgraphy.extensions.node.PROBES`). It is written for Python
3.9 as well (the venv of the tests).
"""
from __future__ import annotations

import json
import os
import sys


def _limits(lim):
    """Put the limits on this process (inherited by nothing: no child may be
    born). What the system does not enforce is said, never hidden."""
    import resource
    said = {}
    mb = 1024 * 1024
    table = [("cpu", resource.RLIMIT_CPU, int(lim.get("cpu_s", 5))),
             ("file", resource.RLIMIT_FSIZE, int(lim.get("file_mb", 16)) * mb),
             ("open_files", resource.RLIMIT_NOFILE, int(lim.get("open_files", 64))),
             ("core", resource.RLIMIT_CORE, 0)]
    if sys.platform != "darwin":
        # macOS accepts RLIMIT_AS and does not keep it: there it is said, not set
        table.append(("memory", resource.RLIMIT_AS, int(lim.get("memory_mb", 512)) * mb))
    for name, which, value in table:
        try:
            soft, hard = resource.getrlimit(which)
            want = value if hard == resource.RLIM_INFINITY else min(value, hard)
            # the CPU's hard limit one second above: SIGXCPU first, then SIGKILL
            hard_new = want + 1 if name == "cpu" and (hard == resource.RLIM_INFINITY or want + 1 <= hard) else want
            resource.setrlimit(which, (want, hard_new))
            said[name] = "set"
        except (ValueError, OSError) as exc:
            said[name] = "not set: %s" % exc
    if sys.platform == "darwin":
        said["memory"] = "not enforced on macOS"
    return said


def _write(work, doc):
    path = os.path.join(work, "result.json")
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def _probe(work, job):
    """Try every way out; ``escaped`` True = the cage leaks there."""
    p = job.get("probe") or {}
    out = {}
    # the network: a socket listening in the server's process
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", int(p.get("port") or 9)), timeout=1.5)
        s.close()
        out["network"] = {"escaped": True, "how": "connected to 127.0.0.1:%s" % p.get("port")}
    except Exception as exc:                               # noqa: BLE001 — refused, any way
        out["network"] = {"escaped": False, "how": type(exc).__name__}
    # writing outside the work dir
    try:
        with open(str(p.get("outside")), "w") as fh:
            fh.write("escaped")
        out["write_outside"] = {"escaped": True, "how": str(p.get("outside"))}
    except Exception as exc:                               # noqa: BLE001
        out["write_outside"] = {"escaped": False, "how": type(exc).__name__}
    # reading what the node keeps (tokens, the rooms of others)
    try:
        with open(str(p.get("protected")), "r") as fh:
            got = fh.read()
        out["read_protected"] = {"escaped": got == p.get("secret"), "how": "read %d bytes" % len(got)}
    except Exception as exc:                               # noqa: BLE001
        out["read_protected"] = {"escaped": False, "how": type(exc).__name__}
    # a process of its own (fork, then exec)
    try:
        pid = os.fork()
        if pid == 0:                                       # pragma: no cover — the child leaves at once
            os._exit(0)
        os.waitpid(pid, 0)
        out["spawn"] = {"escaped": True, "how": "fork"}
    except Exception as exc:                               # noqa: BLE001
        out["spawn"] = {"escaped": False, "how": type(exc).__name__}
    # memory beyond the limit
    want = int((job.get("limits") or {}).get("memory_mb", 512)) + 64
    try:
        block = bytearray(want * 1024 * 1024)
        block[-1] = 1
        out["memory"] = {"escaped": True, "how": "%d MB allocated" % want}
        del block
    except MemoryError:
        out["memory"] = {"escaped": False, "how": "MemoryError"}
    return out


def _run(work, job):
    from s3dgraphy import em
    from s3dgraphy.em import plugins as PL
    from s3dgraphy.em.host import ScriptHost

    deltas = []

    class NodeHost(ScriptHost):
        name = "server"

        def apply(self, delta, *, descriptor, capability, label):
            res = ScriptHost.apply(self, delta, descriptor=descriptor, capability=capability, label=label)
            if res.ok:
                d = delta.as_dict()
                deltas.append({"label": label, "capability": capability, "delta": d,
                               "applied": res.data.get("applied"), "refused": res.data.get("refused")})
            return res

    h = NodeHost(author=job.get("author") or None, language=job.get("lang") or None)
    doc = os.path.join(work, "document.em.json")
    if os.path.isfile(doc):
        h.open(doc)
    em.host.install(h)
    pj = job["plugin"]
    from pathlib import Path
    p = PL.Plugin(id=pj["id"], version=pj["version"], source=pj["source"], folder=Path(pj["folder"]),
                  meta=pj["meta"], module=pj.get("module") or "", entry=pj.get("entry") or "")
    p = PL._load(p, "server")
    PL._plugins[p.id] = p
    res = PL.invoke(p.id, job["command"], job.get("slots") or {}, author=job.get("author") or None)
    data = dict(res.data or {})
    data.pop("error_trace", None)
    return {"ok": bool(res.ok), "message": res.message, "data": data, "deltas": deltas,
            "state": p.state, "problems": p.problems}


def main(argv):
    work, mode = argv[1], (argv[2] if len(argv) > 2 else "run")
    # the server tells «the cage did not start» from «the plugin's process died» by this file
    open(os.path.join(work, "started"), "w").close()
    with open(os.path.join(work, "job.json"), encoding="utf-8") as fh:
        job = json.load(fh)
    for path in reversed(job.get("sys_path") or []):
        if path not in sys.path:
            sys.path.insert(0, path)
    said = _limits(job.get("limits") or {})
    out_dir = os.path.join(work, "out")
    os.makedirs(out_dir, exist_ok=True)
    os.chdir(out_dir)
    os.environ["S3DGRAPHY_PLUGINS_DATA_DIR"] = os.path.join(out_dir, "plugins-data")
    try:
        if mode == "probe":
            doc = {"probe": _probe(work, job), "limits": said}
        elif mode == "probe-cpu":
            # the CPU limit is proved by spinning until the kernel stops it
            n = 0
            while True:
                n += 1
        else:
            doc = _run(work, job)
            doc["limits"] = said
    except MemoryError:
        doc = {"ok": False, "reason": "memory", "limits": said}
    except BaseException as exc:                           # noqa: BLE001 — said to the server
        doc = {"ok": False, "reason": "crashed", "error": "%s: %s" % (type(exc).__name__, exc), "limits": said}
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF)
        doc["cpu_s"] = round(ru.ru_utime + ru.ru_stime, 3)
    except Exception:                                      # noqa: BLE001
        pass
    _write(work, doc)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
