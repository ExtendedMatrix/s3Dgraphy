#!/usr/bin/env python3
"""`./em.sh release` — one dev, from the publication to the desktop, in one command.

The dev27 → dev28 round asked for six blocks of commands in four folders, two
waits by hand (the tag on origin, PyPI's index), a date typed into dtcstamp's
CHANGELOG, the pin commits repository by repository and, at the end, EMStudio's
desktop build. Every one of those was already a command (each repository has
its `em.sh`); this file only puts them in a row.

    ./em.sh release <V> [--dtcstamp X] [--desktop] [--dry-run] [--yes]
    ./em.sh release status [<V>] [--dtcstamp X] [--desktop]

NO STATE FILE. Every step first LOOKS whether it is already done — a tag on
origin, a version on PyPI, a pin in a file, a commit in HEAD — and skips it
saying so. Run the command again after an interruption and it resumes at the
first step not done, because the state is read from the repositories and from
PyPI, never from a file this script would have to keep true.

Standard library only, Python 3.9 (the .venv's interpreter). Every outside
command can be replaced for the tests (tests/test_release.py):
    EM_RELEASE_PARENT   the folder holding the repositories (default: ../ of s3Dgraphy)
    EM_RELEASE_PIP      the pip that asks PyPI (default: <this python> -m pip)
    EM_RELEASE_PYTHON   the python that makes the clean venv (default: python3)
    EM_RELEASE_TMP      where the clean venv goes (default: /tmp)
    EM_RELEASE_GH       gh (default: gh)
    EM_RELEASE_POLL     seconds between two looks (default: 15)
    EM_RELEASE_WAIT_TAG / _WAIT_RUN / _WAIT_PYPI / _WAIT_BUILD   the caps, seconds
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = Path(os.environ.get("EM_RELEASE_PARENT") or HERE.parent.parent).resolve()
ROOT = PARENT / "s3Dgraphy"

PIP = shlex.split(os.environ.get("EM_RELEASE_PIP") or f"{shlex.quote(sys.executable)} -m pip")
PYTHON = os.environ.get("EM_RELEASE_PYTHON") or "python3"
TMP = Path(os.environ.get("EM_RELEASE_TMP") or "/tmp")
GH = shlex.split(os.environ.get("EM_RELEASE_GH") or "gh")
POLL = float(os.environ.get("EM_RELEASE_POLL") or 15)
WAIT = {
    "tag": float(os.environ.get("EM_RELEASE_WAIT_TAG") or 300),     # a pushed tag, seen by ls-remote
    "run": float(os.environ.get("EM_RELEASE_WAIT_RUN") or 120),     # a dispatched run, seen by gh
    "pypi": float(os.environ.get("EM_RELEASE_WAIT_PYPI") or 900),   # PyPI's CDN is late: a wait, not an error
    "build": float(os.environ.get("EM_RELEASE_WAIT_BUILD") or 5400),  # gh run watch: publish.yml, the four installers
}
EXIT_WAIT = 75   # the same code verifica-provenance.sh gives «not visible yet»

#: the repositories a release touches, in the order the precondition reads them
REPOS = ["s3Dgraphy", "dtcstamp", "EMStudio", "EM-blender-tools", "stratigraph-server",
         "stratigraph-templates", "stratigraph-chatbot", "3D-survey-collection"]

#: what steps 6–8 write, per repository: after s3dgraphy V is on PyPI, changes
#: HERE are the release's own work in progress, not somebody's unsaved edits
WRITES = {
    "stratigraph-templates": ["registry/", "dist/"],
    "stratigraph-chatbot": ["schede/", "vocabolari/", "pyproject.toml"],
    "EMStudio": ["tools/requirements.txt", "frontend/src/assets/", "crates/em-core/assets/"],
    "stratigraph-server": ["pyproject.toml", "Dockerfile", "dev-stack/docker-compose.dev.yml"],
    "EM-blender-tools": ["scripts/requirements_wheels.txt"],
}

#: step 9: the pin commits, with the messages of table H of the dev28 report
def commit_messages(v: str, d: str | None) -> dict:
    return {
        "stratigraph-templates": f"Snapshot s3Dgraphy {v} from PyPI",
        "stratigraph-chatbot": f"Vendor the schede against s3Dgraphy {v} and require it",
        "EMStudio": f"Pin s3dgraphy {v}",
        "stratigraph-server": f"Pin s3dgraphy {v} in one place and its two copies",
        "EM-blender-tools": f"Bundle s3dgraphy {v}" + (f" and dtcstamp {d}" if d else ""),
    }


def dtc_message(d: str) -> str:
    return f"Require dtcstamp {d}"


# ══ output ════════════════════════════════════════════════════════════════════

def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if sys.stdout.isatty() else s


def log(s: str) -> None:
    print(_c("1;36", f"▸ {s}"), flush=True)


def ok(s: str) -> None:
    print(_c("1;32", f"✓ {s}"), flush=True)


def warn(s: str) -> None:
    print(_c("1;33", f"⚠  {s}"), file=sys.stderr, flush=True)


class Stop(Exception):
    """The release stops here; the message says why and how to go on."""

    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


# ══ outside commands ══════════════════════════════════════════════════════════

ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}   # em.sh exports src/: not for the others


def sh(cmd, cwd: Path, check: bool = True, capture: bool = False, quiet: bool = False,
       stdin=None) -> subprocess.CompletedProcess:
    if not quiet:
        print(f"    $ ({_rel(cwd)}) {' '.join(shlex.quote(str(c)) for c in cmd)}", flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=ENV, text=True,
                       stdin=stdin if stdin is not None else (subprocess.DEVNULL if capture else None),
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None)
    if check and r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()[-5:] if capture else []
        raise Stop(f"failed (exit {r.returncode}) in {_rel(cwd)}: {' '.join(map(str, cmd))}"
                   + ("\n      " + "\n      ".join(err) if err else ""))
    return r


def out(cmd, cwd: Path) -> str:
    """A READ: its output, or '' if it failed."""
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=ENV, text=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.stdout.strip() if r.returncode == 0 else ""


def git(repo: Path, *args) -> str:
    return out(["git", "--no-optional-locks", *args], repo)


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(PARENT))
    except ValueError:
        return str(p)


def repo(name: str) -> Path:
    return PARENT / name


def exists(name: str) -> bool:
    return (repo(name) / ".git").exists()


# ══ what can be read ══════════════════════════════════════════════════════════

def origin_has_tag(r: Path, tag: str) -> bool:
    return subprocess.run(["git", "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}"],
                          cwd=str(r), env=ENV, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).returncode == 0


def local_has_tag(r: Path, tag: str) -> bool:
    return bool(git(r, "rev-parse", "-q", "--verify", f"refs/tags/{tag}"))


def tag_time(r: Path, tag: str):
    s = git(r, "for-each-ref", "--format=%(creatordate:iso-strict)", f"refs/tags/{tag}")
    return _parse_time(s) if s else None


def _parse_time(s: str):
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def pyproject_version(r: Path) -> str:
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', _read(r / "pyproject.toml"))
    return m.group(1) if m else ""


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def head_file(r: Path, path: str) -> str:
    return git(r, "show", f"HEAD:{path}")


def pypi_has(pkg: str, v: str) -> bool:
    """`pip download pkg==v`: what a consumer's pip will see, CDN included."""
    with tempfile.TemporaryDirectory(prefix="em-release-pip-") as d:
        r = subprocess.run([*PIP, "download", f"{pkg}=={v}", "--no-deps", "--no-cache-dir",
                            "--only-binary=:all:", "--quiet", "--disable-pip-version-check", "-d", d],
                           cwd=d, env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL)
        return r.returncode == 0


def dirty(r: Path) -> list:
    """`git status --porcelain` paths (tracked and untracked-not-ignored)."""
    s = subprocess.run(["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=all"],
                       cwd=str(r), env=ENV, text=True, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout   # not stripped: «XY path»
    return [line[3:].split(" -> ")[-1].strip('"') for line in s.splitlines() if line.strip()]


def remote_distance(r: Path):
    """(ahead, problem): measured against origin with ls-remote, without fetching."""
    branch = git(r, "branch", "--show-current")
    if not branch:
        return 0, "detached HEAD"
    line = out(["git", "ls-remote", "origin", f"refs/heads/{branch}"], r)
    if not line:
        return 0, f"origin has no branch {branch} (or cannot be reached)"
    remote = line.split()[0]
    head = git(r, "rev-parse", "HEAD")
    if remote == head:
        return 0, ""
    if not git(r, "cat-file", "-t", remote):
        return 0, f"behind origin/{branch} (origin has commits this checkout lacks: git pull)"
    if subprocess.run(["git", "merge-base", "--is-ancestor", remote, head], cwd=str(r), env=ENV,
                      stdin=subprocess.DEVNULL).returncode != 0:
        return 0, f"diverged from origin/{branch} (git pull --rebase)"
    return int(git(r, "rev-list", "--count", f"{remote}..HEAD") or 0), ""


def ahead_subjects(r: Path) -> list:
    branch = git(r, "branch", "--show-current")
    line = out(["git", "ls-remote", "origin", f"refs/heads/{branch}"], r)
    if not line:
        return []
    return git(r, "log", "--format=%s", f"{line.split()[0]}..HEAD").splitlines()


def gh_ok() -> bool:
    return subprocess.run([*GH, "auth", "status"], env=ENV, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).returncode == 0


def gh_runs(r: Path, workflow: str) -> list:
    s = out([*GH, "run", "list", "--workflow", workflow, "-L", "20", "--json",
             "databaseId,status,conclusion,createdAt,url,event,headBranch"], r)
    try:
        return json.loads(s) if s else []
    except ValueError:
        return []


def newest_run_since(r: Path, workflow: str, since) -> dict | None:
    runs = [x for x in gh_runs(r, workflow)
            if since is None or _parse_time(x["createdAt"]) >= since - _dt.timedelta(seconds=5)]
    runs.sort(key=lambda x: x["createdAt"], reverse=True)
    return runs[0] if runs else None


def wait_for(what: str, probe, cap: float, resume: str):
    """Look every POLL seconds until `probe()` is truthy; past `cap`, say what and how to resume."""
    t0 = time.monotonic()
    n = 0
    while True:
        n += 1
        got = probe()
        if got:
            return got
        waited = time.monotonic() - t0
        if waited >= cap:
            raise Stop(f"waited {int(waited)} s for {what} and it is not there yet — nothing is wrong yet.\n"
                       f"    When it is, resume with:  {resume}", EXIT_WAIT)
        print(f"    … {what}: look {n}, not yet — next in {POLL:g} s (cap {cap:g} s)", flush=True)
        time.sleep(POLL)


def watch(r: Path, run: dict, what: str, c) -> None:
    """`gh run watch --exit-status`, with a cap: a run past it is still running, not failed."""
    if run.get("status") == "completed":
        if run.get("conclusion") != "success":
            raise Stop(f"{what} ended '{run.get('conclusion')}': gh run view {run.get('databaseId')} --log-failed "
                       f"(in {_rel(r)})")
        return
    cmd = [*GH, "run", "watch", str(run["databaseId"]), "--exit-status"]
    print(f"    $ ({_rel(r)}) {' '.join(cmd)}   (≤{WAIT['build']:g} s)", flush=True)
    try:
        rc = subprocess.run(cmd, cwd=str(r), env=ENV, timeout=WAIT["build"]).returncode
    except subprocess.TimeoutExpired:
        raise Stop(f"waited {WAIT['build']:g} s for {what} ({run.get('url')}) and it is still running.\n"
                   f"    When it ends, resume with:  {c.resume()}", EXIT_WAIT)
    if rc != 0:
        raise Stop(f"{what} failed: gh run view {run['databaseId']} --log-failed (in {_rel(r)})")


# ══ the pins, read and written ════════════════════════════════════════════════

def _has(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.M)
    return m.group(0) if m else ""


def pin_s3d_dtc(text: str, d: str) -> str:
    return _has(r'^\s*"dtcstamp>=' + re.escape(d) + r'"', text)


def pin_emtools_dtc(text: str, d: str) -> str:
    return _has(r'^dtcstamp>=' + re.escape(d) + r'\s*$', text)


def pin_emtools_s3d(text: str, v: str) -> str:
    return _has(r'^s3dgraphy>=' + re.escape(v) + r',<[^\s#]+', text)


def pin_studio(text: str, v: str) -> str:
    return _has(r'^s3dgraphy(\[[^\]]*\])?==' + re.escape(v) + r'\s*$', text)


def pin_server(text: str, v: str) -> str:
    return _has(r'"s3dgraphy\[[^\]]*\]==' + re.escape(v) + r'"', text)


def pin_stratifield(text: str, v: str) -> str:
    return _has(r'"s3dgraphy>=' + re.escape(v) + r'"', text)


def snapshot_version(text: str) -> str:
    m = re.search(r'"s3dgraphy_version"\s*:\s*"([^"]+)"', text)
    return m.group(1) if m else ""


def rewrite(path: Path, pattern: str, repl: str) -> bool:
    text = _read(path)
    new, n = re.subn(pattern, repl, text, count=1, flags=re.M)
    if n != 1:
        raise Stop(f"no line to rewrite in {_rel(path)} (pattern {pattern})")
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


#: the upper bound EMtools keeps: `<1.7.0` for a 1.6 dev (`./em.sh help bump`)
def next_minor(v: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)", v)
    return f"{m.group(1)}.{int(m.group(2)) + 1}.0" if m else "1.7.0"


# ══ the steps ═════════════════════════════════════════════════════════════════
#
# Each step has check() → (state, proof) with state in done / todo / skip, a
# plan() → [(folder, command)] for --dry-run, and run(). `status` and
# `--dry-run` call only check() and plan(); nothing there writes.

DONE, TODO, SKIP, BLOCKED = "done", "to do", "not asked", "blocked"


class Ctx:
    def __init__(self, v, d, desktop, dry, yes):
        self.v, self.d, self.desktop, self.dry, self.yes = v, d, desktop, dry, yes
        self.confirmed = yes

    def resume(self) -> str:
        a = f"./em.sh release {self.v}"
        if self.d:
            a += f" --dtcstamp {self.d}"
        if self.desktop:
            a += " --desktop"
        return a

    def ask(self, q: str) -> bool:
        if self.yes:
            return True
        try:
            r = input(f"{q} [y/N] ")
        except EOFError:
            r = ""
        return r.strip().lower() in ("y", "yes", "s", "si", "sì")

    def published(self) -> bool:
        if not hasattr(self, "_pub"):
            self._pub = pypi_has("s3dgraphy", self.v)
        return self._pub


class Step:
    n = 0
    title = ""

    def check(self, c: Ctx):
        raise NotImplementedError

    def plan(self, c: Ctx):
        return []

    def run(self, c: Ctx):
        raise NotImplementedError


# ── 1 · preconditions ────────────────────────────────────────────────────────

class Preconditions(Step):
    n, title = 1, "preconditions (clean trees, nothing to push, gh)"

    def problems(self, c: Ctx) -> list:
        msgs = commit_messages(c.v, c.d)
        own = set(msgs.values()) | ({dtc_message(c.d)} if c.d else set())
        published = c.published()
        probs = []
        for name in REPOS:
            r = repo(name)
            if not exists(name):
                if name in ("s3Dgraphy",) or (name == "dtcstamp" and c.d):
                    probs.append(f"{name}: not found in {PARENT}")
                continue
            allowed = WRITES.get(name, []) if published else []
            stray = [p for p in dirty(r) if not any(p == a or p.startswith(a) for a in allowed)]
            if stray:
                probs.append(f"{name}: uncommitted changes the release did not make — "
                             + ", ".join(stray[:4]) + (f" (+{len(stray) - 4})" if len(stray) > 4 else ""))
            ahead, problem = remote_distance(r)
            if problem:
                probs.append(f"{name}: {problem}")
            elif ahead:
                # s3Dgraphy's and dtcstamp's bumps push their branch; the others'
                # commits must be the release's own (step 3 or 9), pushed at step 10
                if name == "s3Dgraphy" and not origin_has_tag(r, f"v{c.v}"):
                    continue
                if name == "dtcstamp" and c.d and not origin_has_tag(r, f"v{c.d}"):
                    continue
                foreign = [s for s in ahead_subjects(r) if s not in own]
                if foreign:
                    probs.append(f"{name}: {ahead} commit(s) not pushed that are not the release's "
                                 f"(\"{foreign[0]}\"…): push or explain them first")
        if not shutil.which(GH[0]) and not Path(GH[0]).exists():
            probs.append("gh: not installed (brew install gh && gh auth login)")
        elif not gh_ok():
            probs.append("gh: not authenticated (gh auth status)")
        return probs

    def check(self, c):
        p = self.problems(c)
        return (BLOCKED, "; ".join(p)) if p else (DONE, f"{len(REPOS)} repositories clean and pushed · gh authenticated")

    def plan(self, c):
        return [("each of the 8", "git status --porcelain · git ls-remote origin <branch>"), ("", "gh auth status")]

    def run(self, c):
        p = self.problems(c)
        if p:
            raise Stop("preconditions:\n    " + "\n    ".join(p))
        ok("preconditions: trees clean, nothing foreign to push, gh authenticated")


# ── 2 · dtcstamp ─────────────────────────────────────────────────────────────

class Dtcstamp(Step):
    n, title = 2, "dtcstamp: bump → tag on origin → publish.yml → PyPI"

    def check(self, c):
        if not c.d:
            return SKIP, "no --dtcstamp"
        if pypi_has("dtcstamp", c.d):
            return DONE, f"dtcstamp {c.d} is on PyPI"
        r = repo("dtcstamp")
        t = "on origin" if origin_has_tag(r, f"v{c.d}") else ("here only" if local_has_tag(r, f"v{c.d}") else "absent")
        return TODO, f"tag v{c.d} {t} · dtcstamp {c.d} not on PyPI"

    def plan(self, c):
        return [("dtcstamp", f"./bump_and_push.sh --set {c.d}   (dates the CHANGELOG, commit, tag, push)"),
                ("dtcstamp", f"git ls-remote --tags origin refs/tags/v{c.d}   (until it is there, ≤{WAIT['tag']:g} s)"),
                ("dtcstamp", f"gh workflow run publish.yml -f target=pypi -f version_tag=v{c.d}"),
                ("dtcstamp", "gh run watch <that run> --exit-status"),
                ("", f"pip download dtcstamp=={c.d} --no-deps --no-cache-dir   (until it works, ≤{WAIT['pypi']:g} s)")]

    def run(self, c):
        r, d, tag = repo("dtcstamp"), c.d, f"v{c.d}"
        tag_and_publish(c, r, d, tag, "dtcstamp", publish_cmd=None)
        wait_for(f"dtcstamp {d} on PyPI (pip download)", lambda: pypi_has("dtcstamp", d),
                 WAIT["pypi"], c.resume())
        ok(f"dtcstamp {d} is on PyPI")


def tag_and_publish(c: Ctx, r: Path, v: str, tag: str, label: str, publish_cmd):
    """Shared by dtcstamp and s3Dgraphy: bump (or push the tag already made),
    wait for the tag on origin, then dispatch publish.yml unless a run since the
    tag exists — a run in progress is watched, a successful one is waited on."""
    if origin_has_tag(r, tag):
        print(f"    tag {tag} already on origin — skipped", flush=True)
    else:
        if pyproject_version(r) != v:
            if label == "s3Dgraphy":
                sh(["./em.sh", "bump", v, "--yes"], r)
            else:
                sh(["./bump_and_push.sh", "--set", v], r, stdin=subprocess.DEVNULL)
        else:
            # the version is written: the commit (and maybe the tag) are here, the push failed
            sh(["./bump_and_push.sh", "--tag-only"], r, stdin=subprocess.DEVNULL)
        wait_for(f"tag {tag} on origin ({label})", lambda: origin_has_tag(r, tag), WAIT["tag"], c.resume())
        ok(f"tag {tag} is on origin")
    since = tag_time(r, tag)
    run = newest_run_since(r, "publish.yml", since)
    if run and run.get("status") == "completed" and run.get("conclusion") != "success":
        raise Stop(f"the newest publish.yml run since {tag} ended '{run.get('conclusion')}': {run.get('url')}\n"
                   f"    read it:   gh run view {run.get('databaseId')} --log-failed   (in {_rel(r)})\n"
                   f"    try again: gh workflow run publish.yml -f target=pypi -f version_tag={tag}, then {c.resume()}")
    if run:
        print(f"    publish.yml run since {tag} already there ({run.get('status')}): {run.get('url')} — not dispatched again",
              flush=True)
        if publish_cmd is not None:
            publish_cmd(run)
            return
    else:
        if publish_cmd is not None:
            publish_cmd(None)
            return
        t0 = _dt.datetime.now(_dt.timezone.utc)
        sh([*GH, "workflow", "run", "publish.yml", "-f", "target=pypi", "-f", f"version_tag={tag}"], r)
        run = wait_for(f"the publish.yml run just dispatched ({label})",
                       lambda: newest_run_since(r, "publish.yml", t0), WAIT["run"], c.resume())
        print(f"    {run.get('url')}", flush=True)
    watch(r, run, f"publish.yml for {tag}", c)


# ── 3 · the dtcstamp pin ─────────────────────────────────────────────────────

class DtcPin(Step):
    n, title = 3, "the dtcstamp pin in s3Dgraphy and EM-blender-tools, committed"

    TARGETS = (("s3Dgraphy", "pyproject.toml", pin_s3d_dtc),
               ("EM-blender-tools", "scripts/requirements_wheels.txt", pin_emtools_dtc))

    def check(self, c):
        if not c.d:
            return SKIP, "no --dtcstamp"
        proofs, todo = [], False
        for name, path, has in self.TARGETS:
            if not exists(name):
                continue
            r = repo(name)
            if has(head_file(r, path), c.d):
                proofs.append(f"{name} {git(r, 'log', '-1', '--format=%h', '--', path)}")
            else:
                todo = True
                proofs.append(f"{name} not yet")
        return (TODO if todo else DONE), f"dtcstamp>={c.d}: " + " · ".join(proofs)

    def plan(self, c):
        return [("s3Dgraphy", f'pyproject.toml: "dtcstamp>={c.d}" · git commit -m "{dtc_message(c.d)}"'),
                ("EM-blender-tools", f'scripts/requirements_wheels.txt: dtcstamp>={c.d} · git commit -m "{dtc_message(c.d)}"')]

    def run(self, c):
        for name, path, has in self.TARGETS:
            if not exists(name):
                continue
            r = repo(name)
            if has(head_file(r, path), c.d):
                print(f"    {name}: {path} already requires dtcstamp>={c.d} — skipped", flush=True)
                continue
            if name == "s3Dgraphy" and origin_has_tag(r, f"v{c.v}"):
                warn(f"s3Dgraphy v{c.v} is already tagged without dtcstamp>={c.d}: the pin goes in the NEXT dev")
                continue
            if name == "s3Dgraphy":
                rewrite(r / path, r'^(\s*"dtcstamp>=)[^"]*(")', r"\g<1>" + c.d + r"\g<2>")
            else:
                rewrite(r / path, r'^dtcstamp>=\S*', f"dtcstamp>={c.d}")
            sh(["git", "add", "--", path], r)
            sh(["git", "commit", "-q", "-m", dtc_message(c.d), "--", path], r)
            ok(f"{name}: {dtc_message(c.d)} ({git(r, 'rev-parse', '--short', 'HEAD')})")


# ── 4 · s3Dgraphy bump → publish ─────────────────────────────────────────────

class S3dPublish(Step):
    n, title = 4, "s3Dgraphy: ./em.sh bump → ./em.sh publish"

    def check(self, c):
        if c.published():
            return DONE, f"s3dgraphy {c.v} is on PyPI"
        r = ROOT
        t = "on origin" if origin_has_tag(r, f"v{c.v}") else ("here only" if local_has_tag(r, f"v{c.v}") else "absent")
        return TODO, f"tag v{c.v} {t} · s3dgraphy {c.v} not on PyPI · source says {pyproject_version(r)}"

    def plan(self, c):
        return [("s3Dgraphy", f"./em.sh bump {c.v} --yes   (commit, tag, push)"),
                ("s3Dgraphy", f"git ls-remote --tags origin refs/tags/v{c.v}   (≤{WAIT['tag']:g} s)"),
                ("s3Dgraphy", f"./em.sh publish {c.v} --yes   (publish.yml + verifica-provenance.sh)"),
                ("", f"pip download s3dgraphy=={c.v} --no-deps   (≤{WAIT['pypi']:g} s)")]

    def run(self, c):
        r, v, tag = ROOT, c.v, f"v{c.v}"

        def publish(run):
            if run is None:
                sh(["./em.sh", "publish", v, "--yes"], r)
                return
            watch(r, run, f"publish.yml for {tag}", c)
            sh(["./scripts/verifica-provenance.sh", v], r)

        tag_and_publish(c, r, v, tag, "s3Dgraphy", publish_cmd=publish)
        wait_for(f"s3dgraphy {v} on PyPI (pip download)", lambda: pypi_has("s3dgraphy", v),
                 WAIT["pypi"], c.resume())
        c._pub = True
        ok(f"s3dgraphy {v} is on PyPI")


# ── 5 · the proof ────────────────────────────────────────────────────────────

FP_CODE = ("import s3dgraphy; from s3dgraphy.datamodel import datamodel_fingerprint as f; "
           "print(s3dgraphy.__version__); print(f()['digest'])")


def tree_fingerprint() -> str:
    s = out(["./em.sh", "fingerprint", "--json"], ROOT)
    try:
        return json.loads(s)["digest"]
    except (ValueError, KeyError):
        return ""


class Proof(Step):
    n, title = 5, "the proof: clean venv from PyPI, fingerprint = working tree's"

    def venv(self, c) -> Path:
        return TMP / f"em-release-{c.v}"

    def measured(self, c):
        py = self.venv(c) / "bin" / "python"
        if not py.exists():
            return None
        s = subprocess.run([str(py), "-c", FP_CODE], cwd="/", env=ENV, text=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        lines = s.stdout.split()
        return tuple(lines[:2]) if s.returncode == 0 and len(lines) >= 2 else None

    def check(self, c):
        m = self.measured(c)
        if not m:
            return TODO, f"no venv at {self.venv(c)}"
        tree = tree_fingerprint()
        if m[0] == c.v and m[1] == tree:
            return DONE, f"{self.venv(c)}: s3dgraphy {m[0]}, {m[1][:19]}… = working tree"
        return TODO, f"{self.venv(c)} has s3dgraphy {m[0]} {m[1][:19]}…, working tree {tree[:19]}…"

    def plan(self, c):
        vd = self.venv(c)
        return [("", f"{PYTHON} -m venv {vd}"),
                ("", f'{vd}/bin/pip install --no-cache-dir "s3dgraphy[geo,rdf]=={c.v}"'),
                ("", f"{vd}/bin/python -c <fingerprint>   vs   ./em.sh fingerprint --json")]

    def run(self, c):
        state, proof = self.check(c)
        if state == DONE:
            print(f"    {proof} — already proved", flush=True)
            return
        vd = self.venv(c)
        if vd.exists():
            shutil.rmtree(vd)
        sh([PYTHON, "-m", "venv", vd], TMP)
        sh([vd / "bin" / "pip", "install", "--quiet", "--no-cache-dir", f"s3dgraphy[geo,rdf]=={c.v}"], TMP)
        m = self.measured(c)
        tree = tree_fingerprint()
        if not m:
            raise Stop(f"the clean venv cannot import s3dgraphy ({vd})")
        print(f"    installed s3dgraphy {m[0]}  {m[1]}\n    working tree          {tree}", flush=True)
        if m[0] != c.v:
            raise Stop(f"PyPI gave s3dgraphy {m[0]}, not {c.v}")
        if m[1] != tree:
            raise Stop("the fingerprint from PyPI is NOT the working tree's: what was published is not "
                       "what is here. Stop and find out (./em.sh fingerprint; git log v" + c.v + "..HEAD).")
        ok(f"s3dgraphy {c.v} from PyPI carries the working tree's datamodel")


# ── 6 · propagate ────────────────────────────────────────────────────────────

class Propagate(Step):
    n, title = 6, "./em.sh propagate --pins (templates, StratiField, EMStudio, server)"

    def facts(self, c):
        f = {}
        if exists("stratigraph-templates"):
            f["templates snapshot"] = snapshot_version(_read(repo("stratigraph-templates") / "registry" / "s3dgraphy-snapshot.json")) == c.v
        if exists("EMStudio"):
            f["EMStudio pin"] = bool(pin_studio(_read(repo("EMStudio") / "tools" / "requirements.txt"), c.v))
        if exists("stratigraph-server"):
            f["server pin"] = bool(pin_server(_read(repo("stratigraph-server") / "pyproject.toml"), c.v))
        return f

    def check(self, c):
        f = self.facts(c)
        proof = " · ".join(f"{k} {'= ' + c.v if v else 'not ' + c.v}" for k, v in f.items())
        return (DONE if f and all(f.values()) else TODO), proof

    def plan(self, c):
        return [("s3Dgraphy", "./em.sh propagate --pins --yes")]

    def run(self, c):
        state, proof = self.check(c)
        if state == DONE:
            print(f"    {proof} — skipped", flush=True)
            return
        sh(["./em.sh", "propagate", "--pins", "--yes"], ROOT)
        state, proof = self.check(c)
        if state != DONE:
            raise Stop(f"propagate ran but: {proof}")
        ok("propagated: " + proof)


# ── 7 · EM-blender-tools ─────────────────────────────────────────────────────

class EMtools(Step):
    n, title = 7, "EM-blender-tools: pin, rebundle, manifests, .venv, pytest"
    REQ = "scripts/requirements_wheels.txt"

    def cps(self):
        w = repo("EM-blender-tools") / "wheels"
        return [p for p in (w / "cp311", w / "cp313") if p.is_dir()]

    def venv_versions(self):
        py = repo("EM-blender-tools") / ".venv" / "bin" / "python"
        if not py.exists():
            return "", ""
        s = out([py, "-c", "import s3dgraphy, dtcstamp; print(s3dgraphy.__version__); print(dtcstamp.__version__)"],
                Path("/"))
        parts = s.split()
        return (parts[0], parts[1]) if len(parts) >= 2 else ("", "")

    def facts(self, c):
        r = repo("EM-blender-tools")
        text = _read(r / self.REQ)
        f = {"pin": bool(pin_emtools_s3d(text, c.v))}
        for cp in self.cps():
            f[f"{cp.name} s3dgraphy wheel"] = any(cp.glob(f"s3dgraphy-{c.v}-*.whl"))
            if c.d:
                f[f"{cp.name} dtcstamp wheel"] = any(cp.glob(f"dtcstamp-{c.d}-*.whl"))
        manifest = _read(r / "blender_manifest.toml")
        f["manifest"] = f"s3dgraphy-{c.v}-" in manifest and (not c.d or f"dtcstamp-{c.d}-" in manifest)
        sv, dv = self.venv_versions()
        f[".venv"] = sv == c.v and (not c.d or dv == c.d)
        return f

    def committed(self, c) -> bool:
        head = head_file(repo("EM-blender-tools"), self.REQ)
        return bool(pin_emtools_s3d(head, c.v)) and (not c.d or bool(pin_emtools_dtc(head, c.d)))

    def check(self, c):
        if not exists("EM-blender-tools"):
            return SKIP, "not here"
        f = self.facts(c)
        missing = [k for k, v in f.items() if not v]
        if not missing and self.committed(c):
            return DONE, f"s3dgraphy>={c.v} committed · wheels, manifest, .venv at {c.v}"
        return TODO, ("missing: " + ", ".join(missing)) if missing else "all in place, pytest not yet run (not committed)"

    def plan(self, c):
        p = [("EM-blender-tools", f"{self.REQ}: s3dgraphy>={c.v},<{next_minor(c.v)}"),
             ("EM-blender-tools", "./em.sh rebundle")]
        if c.d:
            p.append(("EM-blender-tools", f"pip download dtcstamp=={c.d} --no-deps -d wheels/cp311|cp313 (the old one removed)"))
        p += [("EM-blender-tools", "./em.sh manifest 3.11 && ./em.sh manifest 3.13"),
              ("EM-blender-tools", f'.venv/bin/python -m pip install "s3dgraphy=={c.v}"'
               + (f' "dtcstamp=={c.d}"' if c.d else "")),
              ("EM-blender-tools", ".venv/bin/python -m pytest -q")]
        return p

    def run(self, c):
        if not exists("EM-blender-tools"):
            print("    not here — skipped", flush=True)
            return
        r = repo("EM-blender-tools")
        if self.committed(c) and all(self.facts(c).values()):
            print("    already committed with wheels, manifest and .venv at " + c.v + " — skipped", flush=True)
            return
        f = self.facts(c)
        if not f["pin"]:
            rewrite(r / self.REQ, r'^s3dgraphy>=\S*', f"s3dgraphy>={c.v},<{next_minor(c.v)}")
            print(f"    {self.REQ}: s3dgraphy>={c.v},<{next_minor(c.v)}", flush=True)
        changed = False
        if not all(f.get(f"{cp.name} s3dgraphy wheel", True) for cp in self.cps()):
            sh(["./em.sh", "rebundle"], r)
            changed = True
        if c.d:
            for cp in self.cps():
                if any(cp.glob(f"dtcstamp-{c.d}-*.whl")):
                    continue
                for old in cp.glob("dtcstamp-*.whl"):
                    print(f"    rm {_rel(old)}", flush=True)
                    old.unlink()
                sh([*PIP, "download", f"dtcstamp=={c.d}", "--no-deps", "--no-cache-dir",
                    "--only-binary=:all:", "--quiet", "-d", cp], r)
                changed = True
        if changed or not f["manifest"]:
            sh(["./em.sh", "manifest", "3.11"], r)
            sh(["./em.sh", "manifest", "3.13"], r)
        sv, dv = self.venv_versions()
        if sv != c.v or (c.d and dv != c.d):
            pkgs = [f"s3dgraphy=={c.v}"] + ([f"dtcstamp=={c.d}"] if c.d else [])
            sh([r / ".venv" / "bin" / "python", "-m", "pip", "install", "--quiet", "--no-cache-dir", *pkgs], r)
        rc = sh([r / ".venv" / "bin" / "python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], r,
                check=False).returncode
        if rc != 0:
            raise Stop(f"EM-blender-tools: pytest is red (exit {rc}). Nothing is committed; fix, then {c.resume()}")
        ok("EM-blender-tools: bundled, manifests rewritten, .venv at " + c.v + ", pytest green")


# ── 8 · StratiField's pin ────────────────────────────────────────────────────

class StratiFieldPin(Step):
    n, title = 8, "StratiField (stratigraph-chatbot) pyproject: s3dgraphy>=V"

    def check(self, c):
        if not exists("stratigraph-chatbot"):
            return SKIP, "not here"
        t = _read(repo("stratigraph-chatbot") / "pyproject.toml")
        if pin_stratifield(t, c.v):
            return DONE, f'"s3dgraphy>={c.v}" in pyproject.toml'
        m = re.search(r'"s3dgraphy>=([^"]+)"', t)
        return TODO, f"pyproject.toml says >={m.group(1) if m else '?'}"

    def plan(self, c):
        return [("stratigraph-chatbot", f'pyproject.toml: "s3dgraphy>={c.v}"')]

    def run(self, c):
        state, proof = self.check(c)
        if state != TODO:
            print(f"    {proof} — skipped", flush=True)
            return
        rewrite(repo("stratigraph-chatbot") / "pyproject.toml", r'"s3dgraphy>=[^"]+"', f'"s3dgraphy>={c.v}"')
        ok(f'stratigraph-chatbot: "s3dgraphy>={c.v}"')


# ── 9 · the pin commits ──────────────────────────────────────────────────────

def at_v_in(name: str, text_of, c: Ctx) -> bool:
    """Is the pin (or snapshot) of `name` at V in the text `text_of(path)` gives?"""
    if name == "stratigraph-templates":
        return snapshot_version(text_of("registry/s3dgraphy-snapshot.json")) == c.v
    if name == "stratigraph-chatbot":
        return bool(pin_stratifield(text_of("pyproject.toml"), c.v))
    if name == "EMStudio":
        return bool(pin_studio(text_of("tools/requirements.txt"), c.v))
    if name == "stratigraph-server":
        return bool(pin_server(text_of("pyproject.toml"), c.v))
    if name == "EM-blender-tools":
        t = text_of(EMtools.REQ)
        return bool(pin_emtools_s3d(t, c.v)) and (not c.d or bool(pin_emtools_dtc(t, c.d)))
    return False


def proof_file(name: str) -> str:
    return {"stratigraph-templates": "registry/s3dgraphy-snapshot.json", "stratigraph-chatbot": "pyproject.toml",
            "EMStudio": "tools/requirements.txt", "stratigraph-server": "pyproject.toml",
            "EM-blender-tools": EMtools.REQ}[name]


class Commits(Step):
    n, title = 9, "the pin commits (y/N per repository)"

    def states(self, c):
        res = []
        for name, msg in commit_messages(c.v, c.d).items():
            if not exists(name):
                continue
            r = repo(name)
            mine = [p for p in dirty(r) if any(p == a or p.startswith(a) for a in WRITES[name])]
            if mine:
                res.append((name, TODO, f"{len(mine)} path(s) to commit", msg, mine))
            elif at_v_in(name, lambda p: head_file(r, p), c):
                res.append((name, DONE, git(r, "log", "-1", "--format=%h", "--", proof_file(name)), msg, []))
            else:
                res.append((name, BLOCKED, "nothing written yet", msg, []))
        return res

    def check(self, c):
        st = self.states(c)
        proof = " · ".join(f"{n} {p}" for n, s, p, _, _ in st)
        if all(s == DONE for _, s, _, _, _ in st):
            return DONE, proof
        return TODO, proof

    def plan(self, c):
        return [(n, f'git diff --stat · [y/N] · git commit -m "{m}"') for n, m in commit_messages(c.v, c.d).items()]

    def run(self, c):
        declined = []
        for name, state, proof, msg, paths in self.states(c):
            r = repo(name)
            if state == DONE:
                print(f"    {name}: committed ({proof}) — skipped", flush=True)
                continue
            if state == BLOCKED:
                raise Stop(f"{name}: the pin is not at {c.v} and nothing is written — an earlier step did not run")
            print(f"\n  {name} — \"{msg}\"", flush=True)
            sh(["git", "--no-optional-locks", "status", "--short", "--", *WRITES[name]], r, quiet=True)
            sh(["git", "--no-optional-locks", "diff", "--stat", "--", *WRITES[name]], r, quiet=True)
            if not c.ask(f"Commit {name} with \"{msg}\"?"):
                declined.append(name)
                print(f"    {name}: not committed", flush=True)
                continue
            sh(["git", "add", "-A", "--", *paths], r)   # what changed, not every place that could
            sh(["git", "commit", "-q", "-m", msg], r)
            ok(f"{name}: {git(r, 'rev-parse', '--short', 'HEAD')} {msg}")
        if declined:
            raise Stop(f"not committed: {', '.join(declined)}. When ready: {c.resume()}")


# ── 10 · the push ────────────────────────────────────────────────────────────

class Push(Step):
    n, title = 10, "the push of the committed repositories (one confirmation)"

    def ahead(self, c):
        res = []
        for name in REPOS:
            if exists(name):
                n, problem = remote_distance(repo(name))
                if n and not problem:
                    res.append((name, n))
        return res

    def check(self, c):
        a = self.ahead(c)
        if not a:
            return DONE, "nothing ahead of origin"
        return TODO, " · ".join(f"{n} {k} ahead" for n, k in a)

    def plan(self, c):
        return [("<each repository ahead of origin>", "git push")]

    def run(self, c):
        a = self.ahead(c)
        if not a:
            print("    nothing ahead of origin — skipped", flush=True)
            return
        for name, k in a:
            print(f"    {name:24} {k} commit(s): " + "; ".join(ahead_subjects(repo(name))[:3]), flush=True)
        if not c.ask(f"Push these {len(a)} repositories?"):
            raise Stop(f"not pushed. When ready: {c.resume()}")
        for name, _ in a:
            sh(["git", "push"], repo(name))
        ok("pushed: " + ", ".join(n for n, _ in a))


# ── 11 · the desktop ─────────────────────────────────────────────────────────

class Desktop(Step):
    n, title = 11, "the desktop: EMStudio devrel → release.yml → the release's URL"

    def tag_with_pin(self, c):
        r = repo("EMStudio")
        for t in git(r, "tag", "-l", "v*", "--sort=-creatordate").splitlines()[:10]:
            if pin_studio(git(r, "show", f"{t}:tools/requirements.txt"), c.v):
                return t
        return ""

    def run_for(self, tag):
        runs = [x for x in gh_runs(repo("EMStudio"), "release.yml") if x.get("headBranch") == tag]
        runs.sort(key=lambda x: x["createdAt"], reverse=True)
        return runs[0] if runs else None

    def check(self, c):
        if not c.desktop:
            return SKIP, "no --desktop"
        if not exists("EMStudio"):
            return SKIP, "EMStudio not here"
        tag = self.tag_with_pin(c)
        if not tag:
            return TODO, f"no EMStudio tag carries s3dgraphy=={c.v}"
        run = self.run_for(tag)
        if run and run.get("conclusion") == "success":
            return DONE, f"{tag} built: {run.get('url')}"
        return TODO, f"{tag} tagged · release.yml " + (f"{run.get('status')} {run.get('conclusion') or ''}".strip() if run else "not seen")

    def plan(self, c):
        return [("EMStudio", "./em.sh s3d status --check"), ("EMStudio", "./em.sh devrel --yes"),
                ("EMStudio", "gh run watch <release.yml run of the tag> --exit-status"),
                ("EMStudio", "gh release view <tag> --json url")]

    def run(self, c):
        r = repo("EMStudio")
        tag = self.tag_with_pin(c)
        if tag:
            print(f"    {tag} already carries s3dgraphy=={c.v} — devrel skipped", flush=True)
        else:
            sh(["./em.sh", "s3d", "status", "--check"], r)
            sh(["./em.sh", "devrel", "--yes"], r)
            tag = self.tag_with_pin(c)
            if not tag:
                raise Stop("devrel ran but no tag carries the pin")
        run = wait_for(f"the release.yml run of {tag}", lambda: self.run_for(tag), WAIT["run"], c.resume())
        print(f"    {run.get('url')}", flush=True)
        watch(r, run, f"release.yml for {tag}", c)
        url = out([*GH, "release", "view", tag, "--json", "url", "-q", ".url"], r)
        ok(f"the desktop {tag}: {url or run.get('url')}")


STEPS = [Preconditions(), Dtcstamp(), DtcPin(), S3dPublish(), Proof(), Propagate(), EMtools(),
         StratiFieldPin(), Commits(), Push(), Desktop()]


# ══ the three ways in ═════════════════════════════════════════════════════════

def table(c: Ctx, with_plan: bool) -> int:
    first_todo = None
    rows = []
    for s in STEPS:
        state, proof = s.check(c)
        if state in (TODO, BLOCKED) and first_todo is None:
            first_todo = s.n
        elif state == TODO and first_todo is not None:
            state = BLOCKED
            proof = f"after step {first_todo} · " + proof
        rows.append((s, state, proof))
    print(f"release s3dgraphy {c.v}" + (f" · dtcstamp {c.d}" if c.d else "") + (" · desktop" if c.desktop else "")
          + f"   ({PARENT})")
    for s, state, proof in rows:
        mark = {DONE: "✓", TODO: "→", BLOCKED: "·", SKIP: "-"}[state]
        print(f"  {mark} {s.n:>2} {state:9} {s.title}")
        if proof:
            print(f"               {proof}")
        if with_plan and state in (TODO, BLOCKED):
            for where, cmd in s.plan(c):
                print(f"               would run{(' in ' + where) if where else ''}: {cmd}")
    if with_plan:
        print("--dry-run: nothing written")
    nxt = next((s for s, st, _ in rows if st in (TODO, BLOCKED)), None)
    print(f"next: step {nxt.n} — {c.resume()}" if nxt else "every step is done")
    return 0


def release(c: Ctx) -> int:
    print(f"release s3dgraphy {c.v}" + (f" · dtcstamp {c.d}" if c.d else "") + (" · desktop" if c.desktop else ""))
    remote = []
    if c.d and not pypi_has("dtcstamp", c.d):
        remote.append(f"publishes dtcstamp {c.d} on PyPI")
    if not c.published():
        remote.append(f"bumps, pushes and publishes s3dgraphy {c.v} on PyPI")
    if c.desktop:
        remote.append("tags EMStudio and starts its four installers")
    if remote and not c.ask("This " + "; ".join(remote) + ". A published version cannot be withdrawn. Go on?"):
        print("stopped: nothing was done")
        return 1
    for s in STEPS:
        state, proof = s.check(c)
        print()
        log(f"{s.n} · {s.title}")
        if state == SKIP:
            print(f"    {proof} — skipped", flush=True)
            continue
        if state == DONE and s.n != 1:
            print(f"    already done: {proof}", flush=True)
            continue
        s.run(c)
    print()
    ok(f"release {c.v} done")
    return 0


def usage() -> str:
    return ("usage: ./em.sh release <V> [--dtcstamp X] [--desktop] [--dry-run] [--yes]\n"
            "       ./em.sh release status [<V>] [--dtcstamp X] [--desktop]")


def main(argv) -> int:
    args, d, desktop, dry, yes, status = [], None, False, False, False, False
    it = iter(argv)
    for a in it:
        if a == "--dtcstamp":
            d = next(it, None)
            if not d:
                print(usage(), file=sys.stderr)
                return 2
        elif a.startswith("--dtcstamp="):
            d = a.split("=", 1)[1]
        elif a == "--desktop":
            desktop = True
        elif a in ("--dry-run", "-n"):
            dry = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a == "status" and not args and not status:
            status = True
        elif a in ("-h", "--help"):
            print(usage())
            return 0
        elif a.startswith("-"):
            print(f"unknown option {a}\n{usage()}", file=sys.stderr)
            return 2
        else:
            args.append(a)
    if len(args) > 1:
        print(usage(), file=sys.stderr)
        return 2
    v = args[0] if args else (pyproject_version(ROOT) if status else "")
    if not v:
        print(usage(), file=sys.stderr)
        return 2
    if not re.match(r"^\d+\.\d+\.\d+((a|b|rc)\d+)?(\.dev\d+)?$", v) or (d and not re.match(r"^\d+\.\d+\.\d+\S*$", d)):
        print(f"not a PEP 440 version: {v}{' / ' + d if d else ''}", file=sys.stderr)
        return 2
    c = Ctx(v, d, desktop, dry, yes)
    try:
        if status or dry:
            if status and not args:
                print(f"(version from s3Dgraphy's pyproject.toml; ./em.sh release status <V> asks about another)")
            return table(c, with_plan=dry)
        return release(c)
    except Stop as e:
        print(_c("1;31", f"✗ {e}"), file=sys.stderr)
        if e.code != EXIT_WAIT:
            print(f"  nothing already done is undone. After the fix: {c.resume()}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        print(f"\ninterrupted. Resume with: {c.resume()}", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
