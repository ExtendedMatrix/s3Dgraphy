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

THE CONFIRMATIONS COUNT DOWN (3 Oct 2026). On a terminal each y/N says «yes in
10 s (n to stop)» and goes on with yes at zero; «n» stops, Enter or «y» go at
once; `--yes` skips the wait; EM_RELEASE_CONFIRM_SECONDS sets the seconds (0 =
ask y/N with no timer). Without a terminal the answer is read from stdin, and
with none the row stops, saying why.

Standard library only, Python 3.9 (the .venv's interpreter). Every outside
command can be replaced for the tests (tests/test_release.py):
    EM_RELEASE_PARENT   the folder holding the repositories (default: ../ of s3Dgraphy)
    EM_RELEASE_PIP      the pip that asks PyPI (default: <this python> -m pip)
    EM_RELEASE_PYTHON   the python that makes the clean venv (default: python3)
    EM_RELEASE_TMP      where the clean venv goes (default: /tmp)
    EM_RELEASE_GH       gh (default: gh)
    EM_RELEASE_POLL     seconds between two looks (default: 15)
    EM_RELEASE_WAIT_TAG / _WAIT_RUN / _WAIT_PYPI / _WAIT_BUILD   the caps, seconds
    EM_RELEASE_PROGRESS seconds between two lines of a long wait (default: 30)
    EM_RELEASE_CONFIRM_SECONDS  the countdown of a confirmation (default: 10; 0 = no timer)
    EM_RELEASE_WHEEL    the command that builds a wheel of a working tree into a
                        folder: `<cmd> <outdir> <tree>` (default: pip wheel)
    EM_RELEASE_DOCKER   docker, asked whether em-dev-server runs (default: docker)
    EM_RELEASE_NODE_HEALTH  the development node's health (default: http://localhost:8000/v1/health)
    EM_RELEASE_WAIT_NODE    the cap for it to say V after the rebuild (default: 180)
    EM_RELEASE_DOWNSTREAM  a JSON list of {repo, cmd, known?} that replaces the
                        consumers of step 0 (each cmd run in its repository,
                        `{python}` = the python that sees the new wheels)
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
    "build": float(os.environ.get("EM_RELEASE_WAIT_BUILD") or 5400),  # gh run watch: publish.yml, the installers
}
PROGRESS = float(os.environ.get("EM_RELEASE_PROGRESS") or 30)
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
    # app/__init__.py and pyproject.toml's own `version`: bump-s3dgraphy.sh counts
    # one more iteration of the server when it moves the pin (W3, 4 Oct 2026)
    "stratigraph-server": ["pyproject.toml", "Dockerfile", "dev-stack/docker-compose.dev.yml", "app/__init__.py"],
    # the fingerprint is rewritten by `./em.sh rebundle` at step 7 (dev29, C3):
    # left out, the rerun stopped at step 1 on it and step 9 did not commit it
    "EM-blender-tools": ["scripts/requirements_wheels.txt", "em_setup/datamodel.fingerprint.json"],
}

#: step 9: the pin commits, with the messages of table H of the dev28 report
def commit_messages(v: str, d: str | None) -> dict:
    return {
        "stratigraph-templates": f"Snapshot s3Dgraphy {v} from PyPI",
        "stratigraph-chatbot": f"Vendor the schede against s3Dgraphy {v} and require it",
        "EMStudio": f"Pin s3dgraphy {v}",
        "stratigraph-server": f"Pin s3dgraphy {v} in one place and its two copies, and count one more iteration of the server",
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
# NO PAGER in any subprocess (dev29, C1): on 2 Oct 2026 step 6 stopped on «:»
# because the `git diff` of stratigraph-server's bump-s3dgraphy.sh opened
# `less`, and the release waited for a `q` nobody knew to press.
ENV.update({"GIT_PAGER": "cat", "PAGER": "cat"})


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


def wait_for(what: str, probe, cap: float, resume: str, not_yet: str = ""):
    """Look every POLL seconds until `probe()` is truthy; past `cap`, say what and how to resume.
    `not_yet`, when given, is the sentence printed for each «not yet» instead of the plain one."""
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
        print(f"    … {what}: look {n}, not yet — "
              + (f"{not_yet}, trying again in {POLL:g} s" if not_yet else f"next in {POLL:g} s")
              + f" (cap {cap:g} s)", flush=True)
        time.sleep(POLL)


def _seconds(a: str, b: str | None = None) -> float:
    """Seconds from the ISO instant `a` to `b` (or now)."""
    try:
        t0 = _parse_time(a)
        t1 = _parse_time(b) if b else _dt.datetime.now(_dt.timezone.utc)
        return max(0.0, (t1 - t0).total_seconds())
    except (TypeError, ValueError):
        return 0.0


def _mmss(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def expected_duration(r: Path, workflow: str) -> float | None:
    """The mean of the last three SUCCESSFUL runs of `workflow`, seconds."""
    s = out([*GH, "run", "list", "--workflow", workflow, "--status", "success", "-L", "3",
             "--json", "createdAt,updatedAt"], r)
    try:
        runs = json.loads(s) if s else []
    except ValueError:
        return None
    took = [_seconds(x.get("createdAt"), x.get("updatedAt")) for x in runs
            if x.get("createdAt") and x.get("updatedAt")]
    took = [t for t in took if t > 0]
    return sum(took) / len(took) if took else None


def run_view(r: Path, run_id) -> dict:
    s = out([*GH, "run", "view", str(run_id), "--json", "status,conclusion,jobs,url"], r)
    try:
        v = json.loads(s) if s else {}
    except ValueError:
        v = {}
    return v if isinstance(v, dict) else {}


def progress_lines(view: dict, run: dict, header: str, expected: float | None) -> list:
    """What a long wait says, every PROGRESS seconds (dev30, R2):

        ▸ 12 · build desktop v1.6.0-dev.15 · 4:12 of ~11 min (mean of the last 3 runs) · end expected 16:05
            macos-arm64  in progress · step «tauri build» (2:40)
            linux        done ✓      · 3:58
    """
    started = run.get("createdAt")
    elapsed = _seconds(started) if started else 0.0
    line = f"▸ {header} · {_mmss(elapsed)}"
    if expected:
        end = _dt.datetime.now() + _dt.timedelta(seconds=max(0.0, expected - elapsed))
        line += (f" of ~{max(1, round(expected / 60))} min (mean of the last 3 runs)"
                 f" · end expected {end:%H:%M}")
    lines = [line]
    jobs = view.get("jobs") or []
    width = max([len(str(j.get("name") or "")) for j in jobs] + [4])
    for j in jobs:
        name = str(j.get("name") or "?").ljust(width)
        st, concl = j.get("status"), j.get("conclusion")
        if st == "completed":
            took = _mmss(_seconds(j.get("startedAt"), j.get("completedAt")))
            word = "done ✓     " if concl == "success" else f"{concl or 'ended'} ✗".ljust(11)
            lines.append(f"    {name}  {word} · {took}")
        elif st == "in_progress":
            step = next((x for x in j.get("steps") or [] if x.get("status") == "in_progress"), None)
            where = f"step «{step.get('name')}» ({_mmss(_seconds(step.get('startedAt')))})" if step \
                else f"({_mmss(_seconds(j.get('startedAt')))})"
            lines.append(f"    {name}  in progress · {where}")
        else:
            lines.append(f"    {name}  {st or 'waiting'}")
    return lines


def _state_of(lines: list) -> list:
    """The lines without their clocks: what changed, for an output that is not a terminal."""
    return [re.sub(r"\d+:\d\d|~\d+ min|end expected \d\d:\d\d", "", x) for x in lines]


def github_warnings(r: Path, view: dict) -> list:
    """The annotations GitHub attaches to the jobs (Node 20 deprecated,
    ubuntu-latest moving…): kept, but said AFTER, as «GitHub's warnings»."""
    nwo = out([*GH, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], r)
    if not nwo:
        return []
    said = []
    for j in view.get("jobs") or []:
        jid = j.get("databaseId")
        if not jid:
            continue
        s = out([*GH, "api", f"repos/{nwo}/check-runs/{jid}/annotations"], r)
        try:
            for a in json.loads(s) if s else []:
                msg = str(a.get("message") or "").strip().splitlines()
                if msg:
                    said.append(f"{j.get('name')}: {a.get('annotation_level', 'notice')} — {msg[0]}")
        except (ValueError, AttributeError):
            continue
    return sorted(set(said))


def watch(r: Path, run: dict, what: str, c, workflow: str = "", step: int | None = None) -> None:
    """Wait for a run, SAYING what is happening (dev30, R2): every PROGRESS
    seconds the jobs, their state, the step in progress and the times, on a line
    that rewrites itself in a terminal (a new line per change of state when the
    output is not one), with the expected duration from the last three
    successful runs. A run past the cap is still running, not failed."""
    header = f"{step} · {what}" if step is not None else what
    if run.get("status") != "completed":
        expected = expected_duration(r, workflow) if workflow else None
        tty = sys.stdout.isatty()
        shown, last_state = 0, None
        t0 = time.monotonic()
        print(f"    {run.get('url') or ''}", flush=True)
        while True:
            view = run_view(r, run["databaseId"])
            status = view.get("status") or run.get("status")
            lines = progress_lines(view, run, header, expected)
            if tty:
                if shown:
                    sys.stdout.write(f"\033[{shown}F\033[J")
                sys.stdout.write("\n".join(lines) + "\n")
                sys.stdout.flush()
                shown = len(lines)
            elif _state_of(lines) != last_state:
                print("\n".join(lines), flush=True)
            last_state = _state_of(lines)
            if status == "completed":
                run = dict(run, status="completed", conclusion=view.get("conclusion"))
                break
            if time.monotonic() - t0 >= WAIT["build"]:
                raise Stop(f"waited {WAIT['build']:g} s for {what} ({run.get('url')}) and it is still running.\n"
                           f"    When it ends, resume with:  {c.resume()}", EXIT_WAIT)
            time.sleep(min(PROGRESS, max(0.01, WAIT["build"] - (time.monotonic() - t0))))
    else:
        view = {}
    if run.get("conclusion") != "success":
        raise Stop(f"{what} ended '{run.get('conclusion')}': gh run view {run.get('databaseId')} --log-failed "
                   f"(in {_rel(r)})")
    notes = github_warnings(r, view) if view else []
    if notes:
        print("    GitHub's warnings:", flush=True)
        for n in notes:
            print(f"      {n}", flush=True)


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

# ── the confirmations: a countdown that goes on by itself (E.D., 3 Oct 2026) ──
#
# Every y/N of the row (the pin commits, the push, the remote ones) used to wait
# for a key — and a release left running while one looks elsewhere waited for
# nothing. On a terminal the question now counts down on its own line, «yes in
# 10 s (n to stop)», and at zero it goes on with YES: «n» stops, Enter or «y» go
# at once. `--yes` still skips the wait. EM_RELEASE_CONFIRM_SECONDS changes the
# length; 0 asks as before, y/N and no timer. Without a terminal there is no
# key to read: the answer is read from stdin as before, and with none the row
# STOPS and says why — a countdown nobody can see must not say yes for anybody.

CONFIRM_ENV = "EM_RELEASE_CONFIRM_SECONDS"
CONFIRM_DEFAULT = 10


def confirm_seconds() -> int:
    raw = os.environ.get(CONFIRM_ENV, "").strip()
    if not raw:
        return CONFIRM_DEFAULT
    try:
        return max(0, int(raw))
    except ValueError:
        return CONFIRM_DEFAULT


def countdown_confirm(q: str, seconds: int, stdin=None, stdout=None,
                      clock=time.monotonic) -> bool:
    """[Y/n] on a terminal, the seconds going down on the same line: «n» stops,
    Enter or «y» go now, and at zero the answer is yes. The terminal is put in
    cbreak mode for the length of the question (one key, no Enter needed) and
    always given back."""
    import math
    import select
    import termios
    import tty
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    fd = stdin.fileno()
    saved = termios.tcgetattr(fd)

    def line(text: str, end: str = "") -> None:
        stdout.write(f"\r{q} [Y/n] — {text}\033[K{end}")
        stdout.flush()

    try:
        # TCSANOW, not the default TCSAFLUSH (which waits for the output to be
        # drained, and on a pty whose echo nobody reads waits for ever); the
        # keys typed BEFORE the question are thrown away explicitly — an Enter
        # pressed a minute ago is not an answer to this
        tty.setcbreak(fd, termios.TCSANOW)
        termios.tcflush(fd, termios.TCIFLUSH)
        deadline = clock() + seconds
        shown = None
        while True:
            left = deadline - clock()
            if left <= 0:
                line(f"yes (no answer in {seconds} s)", "\n")
                return True
            whole = math.ceil(left)
            if whole != shown:
                line(f"yes in {whole} s (n to stop)")
                shown = whole
            ready, _, _ = select.select([fd], [], [], min(0.1, left))
            if not ready:
                continue
            key = os.read(fd, 1).decode(errors="ignore")
            if key in ("n", "N"):
                line("no", "\n")
                return False
            if key in ("y", "Y", "s", "S", "\r", "\n"):
                line("yes", "\n")
                return True
    finally:
        # TCSANOW: given back at once — DRAIN would wait for the echo to be read
        # by the other end, which on a pty nobody may ever do
        termios.tcsetattr(fd, termios.TCSANOW, saved)


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
        seconds = confirm_seconds()
        if seconds and sys.stdin.isatty():
            try:
                return countdown_confirm(q, seconds)
            except (ImportError, OSError) as e:      # no termios (Windows): ask as before
                print(f"    (no countdown here: {e})", flush=True)
            except Exception as e:                   # termios.error is not an OSError
                print(f"    (no countdown here: {e})", flush=True)
        try:
            r = input(f"{q} [y/N] ")
        except EOFError:
            # no terminal, and nothing on stdin: nobody answered, so nobody said yes
            print(f"\n    no answer: stdin is not a terminal and gave none — run it in a "
                  f"terminal, or pass --yes to go on without asking", flush=True)
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


# ── 0 · the downstream proof ─────────────────────────────────────────────────
#
# dev30, R1: on 2 Oct 2026 step 7 found EM-blender-tools red
# (tests/test_georef_roundtrip.py: dev29 had taken `epsg` off the new
# GeoPositionNode, and graph_sync.py still wrote 4326) AFTER 1.6.0.dev29 was on
# PyPI. A published version cannot be withdrawn: the red has to be found BEFORE
# the tag. This step builds the wheel of the working tree and runs each
# consumer's tests on it, in temporary venvs; it writes nothing in any
# repository, so --dry-run runs it for real.

WHEEL_CMD = shlex.split(os.environ.get("EM_RELEASE_WHEEL") or
                        f"{shlex.quote(sys.executable)} -m pip wheel --no-deps --no-build-isolation "
                        f"--quiet -w")

#: how each consumer is tested, as its own step says (step 7 for EM-blender-tools)
DOWNSTREAM = [
    {"repo": "EM-blender-tools", "base": ".venv/bin/python", "kind": "pytest", "args": [],
     # red BY CONSTRUCTION before step 7, which rewrites the fingerprint it
     # compares (em_setup/datamodel.fingerprint.json, `./em.sh rebundle`): said
     # as such, never counted as a break and never hidden
     "realigned": {"tests/test_datamodel_fingerprint.py::test_l_atteso_e_quello_della_ruota_importata":
                   "step 7 rewrites em_setup/datamodel.fingerprint.json"}},
    {"repo": "stratigraph-server", "base": ".venv/bin/python", "kind": "pytest", "args": ["tests"]},
    {"repo": "EMStudio", "base": "../s3Dgraphy/.venv/bin/python", "kind": "emstudio"},
    {"repo": "stratigraph-templates", "base": ".venv/bin/python", "kind": "templates"},
]

#: where a repository keeps the tests it knows fail (one pytest node id a line)
KNOWN_FILES = ("known-test-failures.txt", "scripts/known-test-failures.txt",
               "tests/known-test-failures.txt")


def known_failures(r: Path) -> set:
    for rel in KNOWN_FILES:
        p = r / rel
        if p.is_file():
            return {ln.split("#", 1)[0].strip() for ln in _read(p).splitlines()} - {""}
    return set()


def pytest_failures(said: str) -> list:
    """[(node id, first line of the error)] from the short summary of `pytest -rfE`."""
    got = []
    for ln in said.splitlines():
        m = re.match(r"^(FAILED|ERROR) (\S+)(?: - (.*))?$", ln.strip())
        if m:
            got.append((m.group(2), (m.group(3) or m.group(1)).strip()))
    return got


def _first_error(said: str) -> str:
    for ln in said.splitlines():
        t = ln.strip()
        if re.search(r"(✗|Error|error:|FAILED|AssertionError|Traceback|not ok)", t):
            return t
    lines = [ln.strip() for ln in said.splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


class DownstreamProof(Step):
    n, title = 0, "the downstream proof: the working tree's wheel under each consumer's tests (writes nothing)"

    def where(self, c) -> Path:
        return TMP / f"em-release-{c.v}-prova"

    def consumers(self) -> list:
        raw = os.environ.get("EM_RELEASE_DOWNSTREAM")
        if raw:
            return [dict(x, kind="cmd") for x in json.loads(raw)]
        return DOWNSTREAM

    def check(self, c):
        if c.published():
            return DONE, f"s3dgraphy {c.v} is on PyPI: the proof before the tag is behind us"
        if getattr(c, "_downstream", None):
            return DONE, c._downstream
        return TODO, "runs at the start of every release and of --dry-run (quick, writes nothing)"

    def plan(self, c):
        w = self.where(c)
        p = [("s3Dgraphy", f"{' '.join(WHEEL_CMD)} {w}/dist .")]
        if c.d:
            p.append(("dtcstamp", f"{' '.join(WHEEL_CMD)} {w}/dist ."))
        for x in self.consumers():
            if exists(x["repo"]):
                p.append((x["repo"], {"pytest": "pytest -q -p no:cacheprovider -rfE "
                                                 + " ".join(x.get("args") or []),
                                      "emstudio": "sync-datamodels.sh + npm run check:datamodel on a "
                                                  "scratch copy, graphml2em.py on the wheel",
                                      "templates": "registry-snapshot + validate on a scratch copy",
                                      "cmd": " ".join(x.get("cmd") or [])}[x["kind"]]
                          + "   (in a temporary venv that sees the new wheels)"))
        return p

    # ── the pieces ──────────────────────────────────────────────────────────
    def wheels(self, c) -> list:
        dist = self.where(c) / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        dist.mkdir(parents=True)
        trees = [ROOT] + ([repo("dtcstamp")] if c.d and exists("dtcstamp") else [])
        for t in trees:
            sh([*WHEEL_CMD, dist, t], t)
        got = sorted(dist.glob("*.whl"))
        if len(got) < len(trees):
            raise Stop(f"step 0: the wheel(s) were not built in {dist}")
        return got

    def venv(self, c, x, wheels) -> Path:
        """A venv that sees the consumer's own packages, with the new wheels in front."""
        # normalised, NOT resolved: the venv's python is a symlink to the base
        # interpreter, and resolving it would see the base's packages, not the venv's
        base = Path(os.path.normpath(repo(x["repo"]) / x["base"]))
        if not base.exists():
            raise Stop(f"step 0: {x['repo']} has no python at {base} — make its venv first")
        vd = self.where(c) / x["repo"] / "venv"
        if vd.exists():
            shutil.rmtree(vd)
        sh([base, "-m", "venv", "--without-pip", vd], TMP, quiet=True)
        py = vd / "bin" / "python"
        purelib = out([py, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"], TMP)
        theirs = out([base, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"], TMP)
        if not purelib or not theirs:
            raise Stop(f"step 0: cannot read the site-packages of {base}")
        Path(purelib, "zz-consumer.pth").write_text(theirs + "\n", encoding="utf-8")
        sh([base, "-m", "pip", "install", "--quiet", "--no-deps", "--no-index", "--upgrade",
            "--target", purelib, *wheels], TMP, quiet=True)
        return py

    def run_one(self, c, x, wheels):
        """(failures [(test, first line)], how many were known) for one consumer."""
        r = repo(x["repo"])
        # wide lines: pytest cuts the short summary to the terminal's width
        env = dict({k: v for k, v in ENV.items() if k != "PYTHONPATH"}, COLUMNS="250")
        if x["kind"] == "cmd":
            cmd = [str(a).replace("{python}", sys.executable) for a in x["cmd"]]
            res = subprocess.run(cmd, cwd=str(r), env=env, text=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            return self.judge(r, x, res.returncode, res.stdout)
        py = self.venv(c, x, wheels)
        if x["kind"] == "pytest":
            res = subprocess.run([str(py), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE",
                                  *x.get("args", [])], cwd=str(r), env=env, text=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            return self.judge(r, x, res.returncode, res.stdout)
        if x["kind"] == "templates":
            return self.templates(c, x, py, env)
        return self.emstudio(c, x, py, env)

    def judge(self, r, x, rc, said):
        if rc == 0:
            return [], 0
        fails = pytest_failures(said)
        if not fails:
            return [("(the run)", _first_error(said))], 0
        known = known_failures(r)
        realigned = x.get("realigned") or {}
        for test, _ in fails:
            if test in realigned and test not in known:
                print(f"    {x['repo']}: {test} — red until {realigned[test]}", flush=True)
        new = [f for f in fails if f[0] not in known and f[0] not in realigned]
        return new, len(fails) - len(new)

    def templates(self, c, x, py, env):
        """What step 6 will do (registry-snapshot) and then validate — on a
        scratch copy, so the repository is not touched."""
        src = repo(x["repo"])
        scratch = self.where(c) / x["repo"] / "tree"
        if scratch.exists():
            shutil.rmtree(scratch)
        shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(
            ".git", ".venv", "dist", "out", "__pycache__", "*.egg-info", "node_modules"))
        e = dict(env, PYTHONPATH=str(scratch / "src"), STRATIGRAPH_S3DGRAPHY_SRC="")
        for verb in ("registry-snapshot", "validate"):
            res = subprocess.run([str(py), "-m", "stratigraph_templates.cli", verb], cwd=str(scratch),
                                 env=e, text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            if res.returncode != 0:
                return [(verb, _first_error(res.stdout))], 0
        return [], 0

    def emstudio(self, c, x, py, env):
        """What step 6 will do (sync-datamodels.sh from the wheel) and then
        `npm run check:datamodel` — on a scratch copy of the frontend's scripts
        and assets, beside a stand-in «s3Dgraphy» that IS the installed wheel —
        and the Python sidecar's conversion (graphml2em.py) on the wheel."""
        studio = repo(x["repo"])
        base = self.where(c) / x["repo"] / "tree"
        if base.exists():
            shutil.rmtree(base)
        fe = base / "EMStudio" / "frontend"
        shutil.copytree(studio / "frontend" / "scripts", fe / "scripts")
        shutil.copytree(studio / "frontend" / "src" / "assets", fe / "src" / "assets")
        (base / "EMStudio" / "crates" / "em-core" / "assets").mkdir(parents=True)
        pkg = out([py, "-c", "import os, s3dgraphy; print(os.path.dirname(s3dgraphy.__file__))"], TMP)
        if not pkg:
            return [("import s3dgraphy", "the wheel does not import in the temporary venv")], 0
        stand = base / "s3Dgraphy"
        (stand / "src").mkdir(parents=True)
        (stand / ".venv" / "bin").mkdir(parents=True)
        os.symlink(pkg, stand / "src" / "s3dgraphy")
        os.symlink(py, stand / ".venv" / "bin" / "python")
        e = dict(env, PATH=f"{py.parent}{os.pathsep}{env.get('PATH', '')}")
        for label, cmd in (("sync-datamodels.sh", ["bash", "scripts/sync-datamodels.sh", str(stand)]),
                           ("npm run check:datamodel", ["node", "scripts/check-datamodel.mjs"])):
            res = subprocess.run(cmd, cwd=str(fe), env=e, text=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if res.returncode != 0:
                return [(label, _first_error(res.stdout))], 0
        graphml = ROOT / "tests" / "fixtures" / "dev29" / "tiny.graphml"
        sample = next((p for p in (graphml, *sorted((ROOT / "tests").rglob("*.graphml")))
                       if p.is_file()), None)
        if sample is not None and (studio / "tools" / "graphml2em.py").is_file():
            res = subprocess.run([str(py), str(studio / "tools" / "graphml2em.py"), str(sample),
                                  str(base / "out.em.json")], cwd=str(studio / "tools"), env=e,
                                 text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            if res.returncode != 0:
                return [(f"tools/graphml2em.py {sample.name}", _first_error(res.stdout))], 0
        return [], 0

    def run(self, c):
        if c.published():
            print(f"    s3dgraphy {c.v} is on PyPI: the proof before the tag is behind us — skipped",
                  flush=True)
            return
        wheels = [] if os.environ.get("EM_RELEASE_DOWNSTREAM") and not os.environ.get("EM_RELEASE_WHEEL") \
            else self.wheels(c)
        for w in wheels:
            print(f"    built {_rel(w)}", flush=True)
        said, red = [], []
        for x in self.consumers():
            if not exists(x["repo"]):
                print(f"    {x['repo']}: not here — skipped", flush=True)
                continue
            print(f"    {x['repo']} …", flush=True)
            new, known = self.run_one(c, x, wheels)
            if new:
                red.append((x["repo"], new))
                for test, first in new[:5]:
                    print(_c("1;31", f"    ✗ {x['repo']}: {test}"), flush=True)
                    print(f"        {first}", flush=True)
            else:
                said.append(f"{x['repo']} green" + (f" ({known} known)" if known else ""))
                ok(f"{x['repo']}: green" + (f", {known} known failure(s) only" if known else ""))
        if red:
            first = red[0]
            raise Stop(f"step 0: a consumer is red on the working tree's wheel — nothing is tagged.\n"
                       f"    {first[0]}: {first[1][0][0]}\n      {first[1][0][1]}\n"
                       f"    fix it (or add it to that repository's known-test-failures.txt), then {c.resume()}")
        c._downstream = " · ".join(said) or "no consumer here"


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
                # commits must be the release's own (step 3 or 9), pushed at step 11
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
                ("dtcstamp", "gh run view <that run> --json jobs   (every 30 s: the jobs, their step, the times)"),
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
    watch(r, run, f"publish.yml for {tag}", c, workflow="publish.yml",
          step=2 if label == "dtcstamp" else 4)


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
                ("s3Dgraphy", f"gh workflow run publish.yml -f target=pypi -f version_tag=v{c.v}   (watched, job by job)"),
                ("s3Dgraphy", f"./scripts/verifica-provenance.sh {c.v}"),
                ("", f"pip download s3dgraphy=={c.v} --no-deps   (≤{WAIT['pypi']:g} s)")]

    def run(self, c):
        r, v, tag = ROOT, c.v, f"v{c.v}"

        def publish(run):
            if run is None:
                # what `./em.sh publish` does, with the wait said (dev30, R2):
                # dispatch, watch the run job by job, then the provenance
                branch = git(r, "branch", "--show-current") or "HEAD"
                t0 = _dt.datetime.now(_dt.timezone.utc)
                sh([*GH, "workflow", "run", "publish.yml", "--ref", branch, "-f", "target=pypi",
                    "-f", f"version_tag={tag}"], r)
                run = wait_for(f"the publish.yml run just dispatched (s3Dgraphy)",
                               lambda: newest_run_since(r, "publish.yml", t0), WAIT["run"], c.resume())
            watch(r, run, f"publish.yml for {tag}", c, workflow="publish.yml", step=4)
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


#: what pip says when the index does not show the version YET (dev29, C2): on
#: 2 Oct 2026 `pip install s3dgraphy==1.6.0.dev28` gave «No matching
#: distribution» right after step 4 had seen it — PyPI's CDN answers per node
NOT_VISIBLE_YET = re.compile(r"No matching distribution found|Could not find a version that satisfies")


#: the sentence of each «not yet» of a pip that asks PyPI for what was just published
PIP_NOT_YET = "PyPI does not show it to this pip yet"


def from_pypi(cmd: list, cwd: Path, spec: str, c: Ctx, verb: str = "pip install") -> str:
    """Run `cmd` — a `pip install`/`pip download` of `spec`, or a command that
    makes one (`./em.sh rebundle`) — retried with step 4's cap while PyPI does
    not show `spec` to this pip yet: right after a publication that is a wait,
    not a failure (W2: on 4 Oct 2026 step 4 saw dev34 and step 7's `pip
    install`, minutes later and from another pip, did not). Every pip of the
    release that asks for a version just published goes through here. Any
    other error stops the release. Returns what the command said."""
    print(f"    $ ({_rel(cwd)}) {' '.join(shlex.quote(str(x)) for x in cmd)}", flush=True)
    said_ok = []

    def attempt():
        r = subprocess.run([str(x) for x in cmd], cwd=str(cwd), env=ENV, text=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        said = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            said_ok.append(said)
            return True
        if NOT_VISIBLE_YET.search(said):
            return False
        tail = "\n      ".join(said.strip().splitlines()[-5:])
        raise Stop(f"failed (exit {r.returncode}) in {_rel(cwd)}: {' '.join(str(x) for x in cmd)}"
                   + (f"\n      {tail}" if tail else ""))

    wait_for(f"{spec} from PyPI ({verb})", attempt, WAIT["pypi"], c.resume(), not_yet=PIP_NOT_YET)
    return said_ok[-1] if said_ok else ""


def install_from_pypi(pip: Path, spec: str, c: Ctx) -> None:
    """`pip install spec` in TMP, through `from_pypi`."""
    from_pypi([pip, "install", "--quiet", "--no-cache-dir", spec], TMP, spec, c)


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
        install_from_pypi(vd / "bin" / "pip", f"s3dgraphy[geo,rdf]=={c.v}", c)
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
            said = from_pypi(["./em.sh", "rebundle"], r, f"s3dgraphy=={c.v}", c, "./em.sh rebundle")
            for line in said.strip().splitlines()[-8:]:
                print(f"      {line}", flush=True)
            changed = True
        if c.d:
            for cp in self.cps():
                if any(cp.glob(f"dtcstamp-{c.d}-*.whl")):
                    continue
                for old in cp.glob("dtcstamp-*.whl"):
                    print(f"    rm {_rel(old)}", flush=True)
                    old.unlink()
                from_pypi([*PIP, "download", f"dtcstamp=={c.d}", "--no-deps", "--no-cache-dir",
                           "--only-binary=:all:", "--quiet", "-d", cp], r, f"dtcstamp=={c.d}", c,
                          "pip download")
                changed = True
        if changed or not f["manifest"]:
            sh(["./em.sh", "manifest", "3.11"], r)
            sh(["./em.sh", "manifest", "3.13"], r)
        sv, dv = self.venv_versions()
        if sv != c.v or (c.d and dv != c.d):
            pkgs = [f"s3dgraphy=={c.v}"] + ([f"dtcstamp=={c.d}"] if c.d else [])
            from_pypi([r / ".venv" / "bin" / "python", "-m", "pip", "install", "--quiet", "--no-cache-dir",
                       *pkgs], r, " ".join(pkgs), c)
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
    n, title = 9, "the pin commits (a confirmation per repository, with its countdown)"

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
        return [(n, f'git diff --stat · [Y/n, yes in {confirm_seconds()} s] · git commit -m "{m}"') for n, m in commit_messages(c.v, c.d).items()]

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


# ── 10 · the development node ────────────────────────────────────────────────
#
# W3, measured on 4 Oct 2026 after `./em.sh release 1.6.0.dev34 --desktop`: the
# server's pin was dev34 in its three files and committed, and the node on this
# computer still answered `"s3dgraphy": "1.6.0.dev33"` on /v1/health — step 6
# only PRINTED «Per applicarlo: ./bump-s3dgraphy.sh 1.6.0.dev34 --build». So
# when the em-dev stack is up (its container `em-dev-server` running), the
# release now rebuilds it after the pin commits, behind a confirmation with its
# countdown, and believes it only when /v1/health says the version. When the
# stack is down it says so and goes on: a node that is off is not a fault.
# BEFORE the push on purpose: an image that does not build with V is a pin
# that should not be pushed yet.

DOCKER = shlex.split(os.environ.get("EM_RELEASE_DOCKER") or "docker")
NODE_CONTAINER = "em-dev-server"
NODE_HEALTH = os.environ.get("EM_RELEASE_NODE_HEALTH") or "http://localhost:8000/v1/health"
WAIT["node"] = float(os.environ.get("EM_RELEASE_WAIT_NODE") or 180)   # the container restarting
NOT_UP = "not up"


def node_running() -> tuple:
    """(running?, why) — `docker ps` asked for the container by its exact name."""
    try:
        r = subprocess.run([*DOCKER, "ps", "--filter", f"name=^{NODE_CONTAINER}$", "--filter", "status=running",
                            "--format", "{{.Names}}"], env=ENV, text=True, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"docker does not answer ({e.__class__.__name__})"
    if r.returncode != 0:
        return False, "docker does not answer (" + ((r.stderr or "").strip().splitlines() or ["exit %d" % r.returncode])[-1] + ")"
    if NODE_CONTAINER in r.stdout.split():
        return True, f"{NODE_CONTAINER} running"
    return False, f"{NODE_CONTAINER} is not running"


def node_health() -> dict:
    """What /v1/health answers, or {} — a READ, never raising."""
    import urllib.request
    try:
        with urllib.request.urlopen(NODE_HEALTH, timeout=3) as r:
            got = json.loads(r.read().decode("utf-8") or "{}")
            return got if isinstance(got, dict) else {}
    except Exception:
        return {}


class DevNode(Step):
    n, title = 10, "the development node: ./bump-s3dgraphy.sh V --build if em-dev is up, then /v1/health"

    def check(self, c):
        if not exists("stratigraph-server"):
            return SKIP, "stratigraph-server not here"
        up, why = node_running()
        if not up:
            return NOT_UP, f"{why} — the em-dev stack is down, nothing to rebuild"
        h = node_health()
        if not h:
            return TODO, f"{why}, {NODE_HEALTH} does not answer"
        said = h.get("s3dgraphy")
        if said == c.v:
            return DONE, f'{NODE_HEALTH} says "s3dgraphy": "{said}" (server {h.get("version")})'
        return TODO, f'{NODE_HEALTH} says "s3dgraphy": "{said}"'

    def plan(self, c):
        return [("stratigraph-server", f"[Y/n, yes in {confirm_seconds()} s] ./bump-s3dgraphy.sh {c.v} --build"),
                ("", f'GET {NODE_HEALTH} until "s3dgraphy": "{c.v}" (cap {WAIT["node"]:g} s)')]

    def run(self, c):
        r = repo("stratigraph-server")
        if not c.ask(f"Rebuild and restart the development node ({NODE_CONTAINER}) with s3dgraphy {c.v}?"):
            # a local node, not a publication: declining it does not stop the row
            print(f"    not rebuilt. When ready:  (stratigraph-server) ./bump-s3dgraphy.sh {c.v} --build", flush=True)
            return
        sh(["./bump-s3dgraphy.sh", c.v, "--build"], r)
        seen = {}

        def answers():
            h = node_health()
            seen["last"] = h.get("s3dgraphy") if h else "no answer"
            return h if h.get("s3dgraphy") == c.v else None

        try:
            h = wait_for(f'{NODE_HEALTH} saying "s3dgraphy": "{c.v}"', answers, WAIT["node"], c.resume(),
                         not_yet="the container is restarting")
        except Stop as e:
            raise Stop(f'the node was rebuilt and {NODE_HEALTH} still says {seen.get("last")!r}, not {c.v!r}.\n'
                       f"    Look:  docker logs {NODE_CONTAINER} --tail 50", e.code)
        ok(f'the development node answers "s3dgraphy": "{c.v}" (server {h.get("version")})')


# ── 11 · the push ────────────────────────────────────────────────────────────

class Push(Step):
    n, title = 11, "the push of the committed repositories (one confirmation)"

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


# ── 12 · the desktop ─────────────────────────────────────────────────────────

class Desktop(Step):
    n, title = 12, "the desktop: EMStudio devrel → release.yml → the release's URL"

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
                ("EMStudio", "gh run view <release.yml run of the tag> --json jobs   (every 30 s)"),
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
        watch(r, run, f"build desktop {tag}", c, workflow="release.yml", step=12)
        url = out([*GH, "release", "view", tag, "--json", "url", "-q", ".url"], r)
        ok(f"the desktop {tag}: {url or run.get('url')}")
        for line in self.assets(tag):
            print(f"      {line}", flush=True)

    def assets(self, tag) -> list:
        """The release's assets with their size, as GitHub lists them."""
        s = out([*GH, "release", "view", tag, "--json", "assets"], repo("EMStudio"))
        try:
            got = json.loads(s).get("assets") or [] if s else []
        except (ValueError, AttributeError):
            return []
        return [f"{a.get('name')}  {int(a.get('size') or 0) / 1e6:.1f} MB" for a in got
                if isinstance(a, dict) and a.get("name")]

    def draft_note(self, c) -> str:
        """Whether the release of the tag is a DRAFT, and the command that
        publishes it — said, never run (dev29, C4)."""
        if not c.desktop or not exists("EMStudio"):
            return ""
        tag = self.tag_with_pin(c)
        if not tag:
            return ""
        draft = out([*GH, "release", "view", tag, "--json", "isDraft", "-q", ".isDraft"], repo("EMStudio"))
        if draft == "true":
            return (f"the EMStudio release {tag} is a DRAFT. To publish it — this script never does:\n"
                    f"      (EMStudio) gh release edit {tag} --draft=false")
        if draft == "false":
            return f"the EMStudio release {tag} is published (not a draft)"
        return f"the EMStudio release {tag}: draft or not could not be read (gh release view {tag})"


STEPS = [DownstreamProof(), Preconditions(), Dtcstamp(), DtcPin(), S3dPublish(), Proof(), Propagate(), EMtools(),
         StratiFieldPin(), Commits(), DevNode(), Push(), Desktop()]


# ══ the three ways in ═════════════════════════════════════════════════════════

def table(c: Ctx, with_plan: bool) -> int:
    first_todo = None
    rows = []
    for s in STEPS:
        state, proof = s.check(c)
        if s.n == 0:
            # step 0 is not a state of the repositories: it runs at the start of
            # every release, so it never stands before the others
            rows.append((s, state, proof))
            continue
        if state in (TODO, BLOCKED) and first_todo is None:
            first_todo = s.n
        elif state == TODO and first_todo is not None:
            state = BLOCKED
            proof = f"after step {first_todo} · " + proof
        rows.append((s, state, proof))
    print(f"release s3dgraphy {c.v}" + (f" · dtcstamp {c.d}" if c.d else "") + (" · desktop" if c.desktop else "")
          + f"   ({PARENT})")
    for s, state, proof in rows:
        mark = {DONE: "✓", TODO: "→", BLOCKED: "·", SKIP: "-", NOT_UP: "-"}[state]
        print(f"  {mark} {s.n:>2} {state:9} {s.title}")
        if proof:
            print(f"               {proof}")
        if with_plan and state in (TODO, BLOCKED):
            for where, cmd in s.plan(c):
                print(f"               would run{(' in ' + where) if where else ''}: {cmd}")
    if with_plan:
        print("--dry-run: nothing written")
    nxt = next((s for s, st, _ in rows if st in (TODO, BLOCKED) and s.n != 0), None)
    print(f"next: step {nxt.n} — {c.resume()}" if nxt else "every step is done")
    if rows[-1][1] == DONE:
        note = STEPS[-1].draft_note(c)
        if note:
            print(note)
    return 0


def release(c: Ctx) -> int:
    print(f"release s3dgraphy {c.v}" + (f" · dtcstamp {c.d}" if c.d else "") + (" · desktop" if c.desktop else ""))
    # step 0 first, before any question: a red consumer stops it here
    print()
    log(f"0 · {STEPS[0].title}")
    STEPS[0].run(c)
    remote = []
    if c.d and not pypi_has("dtcstamp", c.d):
        remote.append(f"publishes dtcstamp {c.d} on PyPI")
    if not c.published():
        remote.append(f"bumps, pushes and publishes s3dgraphy {c.v} on PyPI")
    if c.desktop:
        remote.append("tags EMStudio and starts its installers")
    if remote and not c.ask("This " + "; ".join(remote) + ". A published version cannot be withdrawn. Go on?"):
        print("stopped: nothing was done")
        return 1
    for s in STEPS[1:]:
        state, proof = s.check(c)
        print()
        log(f"{s.n} · {s.title}")
        if state in (SKIP, NOT_UP):
            print(f"    {proof} — skipped", flush=True)
            continue
        if state == DONE and s.n != 1:
            print(f"    already done: {proof}", flush=True)
            continue
        s.run(c)
    note = STEPS[-1].draft_note(c)
    if note:
        print()
        log(note)
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
        if dry and not status:
            # step 0 writes nothing: the dry-run is where it is needed (R1)
            log("0 · " + STEPS[0].title)
            STEPS[0].run(c)
            print()
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
