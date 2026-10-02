"""`./em.sh release` (scripts/release.py) on a world made for it.

Eight throwaway repositories, each with a BARE origin (so `git push` and
`git ls-remote` are the real ones), and fakes for everything that would reach
the outside: `gh` (dispatch, run list/watch, release view), `pip download`
(a folder standing for PyPI, which can be told to be late), the python that
makes the clean venv, the `.venv` of EM-blender-tools, and the `em.sh` of each
repository reduced to what the release calls. dtcstamp's step uses the REAL
`../dtcstamp/bump_and_push.sh` when it is next door, so the CHANGELOG's date is
proved through the release too.

What is proved: the whole row in --dry-run writes nothing; the round goes
through and `status` then says every step is done; an interruption at steps
2, 4, 6 and 9 resumes at the first step not done, skipping the others SAYING
so; a dirty tree stops it before anything is written; a late PyPI is waited
for, and past the cap the wait stops with the command that resumes; a proof
whose fingerprint differs stops it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent / "scripts" / "release.py"
REAL_DTC_BUMP = HERE.parent.parent / "dtcstamp" / "bump_and_push.sh"

pytestmark = pytest.mark.skipif(not shutil.which("git") or not shutil.which("bash"),
                                reason="git and bash are needed")

V, D = "1.6.0.dev28", "0.1.3"

# ── the fakes ─────────────────────────────────────────────────────────────────

FAKE_GH = r'''#!/usr/bin/env python3
import datetime, json, os, subprocess, sys
state = os.path.join(os.environ["FAKE_STATE"], "gh.json")
db = json.load(open(state)) if os.path.exists(state) else {"runs": [], "n": 0}
def save(): json.dump(db, open(state, "w"))
def here():
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    return os.path.basename(top)
def add_run(repo, wf, head):
    db["n"] += 1
    running = os.environ.get("FAKE_RUN_STATUS") == "in_progress"
    db["runs"].append({"repo": repo, "workflow": wf, "databaseId": db["n"],
        "status": "in_progress" if running else "completed",
        "conclusion": None if running else "success", "event": "workflow_dispatch", "headBranch": head,
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "url": f"https://example.invalid/{repo}/runs/{db['n']}"})
    save()
a = sys.argv[1:]
open(os.path.join(os.environ["FAKE_STATE"], "gh.log"), "a").write(" ".join(a) + "\n")
if a[:2] == ["auth", "status"]:
    sys.exit(0 if os.environ.get("FAKE_GH_AUTH", "ok") == "ok" else 1)
if a[:2] == ["workflow", "run"]:
    if os.environ.get("FAKE_FAIL") == "dispatch-s3d" and here() == "s3Dgraphy":
        print("HTTP 500 (fake)", file=sys.stderr); sys.exit(1)
    if os.environ.get("FAKE_FAIL") == "dispatch":
        print("HTTP 500 (fake)", file=sys.stderr); sys.exit(1)
    tag = [x.split("=", 1)[1] for x in a if x.startswith("version_tag=")][0]
    repo = here()
    add_run(repo, a[2], "main")
    pkg = "dtcstamp" if repo == "dtcstamp" else "s3dgraphy"
    os.makedirs(os.path.join(os.environ["FAKE_STATE"], "pypi"), exist_ok=True)
    open(os.path.join(os.environ["FAKE_STATE"], "pypi", f"{pkg}=={tag[1:]}"), "w").write(
        os.environ.get("FAKE_PYPI_DELAY", "0"))
    sys.exit(0)
if a[:1] == ["_add-run"]:
    add_run(here(), a[1], a[2]); sys.exit(0)
if a[:2] == ["run", "list"]:
    wf = a[a.index("--workflow") + 1]
    print(json.dumps([r for r in db["runs"] if r["repo"] == here() and r["workflow"] == wf])); sys.exit(0)
if a[:2] == ["run", "view"]:
    # in progress for FAKE_VIEW_POLLS looks (or while FAKE_WATCH_SLEEP says the
    # run is long), then completed: the polls the release makes are counted
    rid = a[2]
    n = int(db.get("views", {}).get(rid, 0)) + 1
    db.setdefault("views", {})[rid] = n; save()
    polls = int(os.environ.get("FAKE_VIEW_POLLS", "0"))
    running = float(os.environ.get("FAKE_WATCH_SLEEP", "0")) > 0 or n <= polls
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    jobs = [{"name": "macos-arm64", "databaseId": 900 + n,
             "status": "in_progress" if running else "completed",
             "conclusion": None if running else "success", "startedAt": now, "completedAt": now,
             "steps": [{"name": "tauri build", "status": "in_progress" if running else "completed",
                        "startedAt": now}]},
            {"name": "linux", "databaseId": 800, "status": "completed", "conclusion": "success",
             "startedAt": now, "completedAt": now, "steps": []}]
    print(json.dumps({"status": "in_progress" if running else "completed",
                      "conclusion": None if running else "success", "jobs": jobs,
                      "url": f"https://example.invalid/runs/{rid}"}))
    sys.exit(0)
if a[:2] == ["run", "watch"]:
    import time; time.sleep(float(os.environ.get("FAKE_WATCH_SLEEP", "0"))); sys.exit(0)
if a[:2] == ["release", "view"]:
    if "isDraft" in a:
        print(os.environ.get("FAKE_DRAFT", "true")); sys.exit(0)
    print(f"https://example.invalid/releases/{a[2]}"); sys.exit(0)
sys.exit(0)
'''

FAKE_PIP = r'''#!/usr/bin/env bash
# pip download <pkg>==<v> … -d <dir>: the folder $FAKE_STATE/pypi stands for PyPI;
# a file holding N > 0 answers «not yet» N more times (the CDN being late)
[[ "$1" == download ]] || exit 0
spec="$2"; dir=""
while [[ $# -gt 0 ]]; do [[ "$1" == -d ]] && dir="$2"; shift; done
f="$FAKE_STATE/pypi/$spec"
[[ -f "$f" ]] || exit 1
n="$(cat "$f")"
if [[ "$n" -gt 0 ]]; then echo $((n - 1)) > "$f"; exit 1; fi
pkg="${spec%%==*}"; v="${spec#*==}"
[[ -n "$dir" ]] && : > "$dir/$pkg-$v-py3-none-any.whl"
exit 0
'''

FAKE_PYTHON = r'''#!/usr/bin/env bash
# python3 -m venv DIR: a venv whose pip "installs" s3dgraphy==V and whose python
# answers the fingerprint question with $FAKE_PYPI_DIGEST
[[ "$1 $2" == "-m venv" ]] || exit 1
d="$3"; mkdir -p "$d/bin"
cat > "$d/bin/pip" <<EOF
#!/usr/bin/env bash
late="\$FAKE_STATE/venv-pip-late"
if [[ -n "\$FAKE_VENV_PIP_LATE" && ! -f "\$late" ]]; then echo "\$FAKE_VENV_PIP_LATE" > "\$late"; fi
if [[ -f "\$late" && "\$(cat "\$late")" -gt 0 ]]; then
  echo \$(( \$(cat "\$late") - 1 )) > "\$late"
  echo "ERROR: No matching distribution found for s3dgraphy (fake: the CDN is late)" >&2; exit 1
fi
for a in "\$@"; do case "\$a" in s3dgraphy*==*) echo "\${a#*==}" > "$d/installed";; esac; done
EOF
cat > "$d/bin/python" <<EOF
#!/usr/bin/env bash
[[ -f "$d/installed" ]] || exit 1
cat "$d/installed"; echo "\${FAKE_PYPI_DIGEST:-sha256:aaa}"
EOF
chmod +x "$d/bin/pip" "$d/bin/python"
'''

S3D_EM = r'''#!/usr/bin/env bash
set -e
v_of() { sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml; }
case "$1" in
  fingerprint) echo '{"digest": "sha256:aaa"}' ;;
  bump)
    cur="$(v_of)"; sed -i.bak "s/^version = \".*\"/version = \"$2\"/" pyproject.toml; rm -f pyproject.toml.bak
    git commit -q -am "Bump version: $cur → $2"; git tag -a "v$2" -m "v$2"
    [[ "$FAKE_FAIL" == bump-push ]] && { echo "push refused (fake)" >&2; exit 1; }
    git push -q && git push -q --tags ;;
  publish)
    [[ "$FAKE_FAIL" == publish ]] && { echo "publish failed (fake)" >&2; exit 1; }
    gh workflow run publish.yml -f target=pypi -f "version_tag=v$2" ;;
  propagate)
    echo "${GIT_PAGER:-unset} ${PAGER:-unset}" > "$FAKE_STATE/pager"
    [[ "$FAKE_FAIL" == propagate ]] && { echo "after-bump failed (fake)" >&2; exit 1; }
    v="$(v_of)"; P=..
    sed -i.bak "s/\"s3dgraphy_version\": \".*\"/\"s3dgraphy_version\": \"$v\"/" $P/stratigraph-templates/registry/s3dgraphy-snapshot.json
    echo "{\"against\": \"$v\"}" > $P/stratigraph-chatbot/schede/new.json
    sed -i.bak "s/==.*/==$v/" $P/EMStudio/tools/requirements.txt
    sed -i.bak "s/\(s3dgraphy\[geo,rdf\]==\)[^\"]*/\1$v/" $P/stratigraph-server/pyproject.toml
    rm -f $P/*/*.bak $P/*/*/*.bak ;;
  *) exit 2 ;;
esac
'''

S3D_TAG_ONLY = r'''#!/usr/bin/env bash
v="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
git rev-parse -q --verify "refs/tags/v$v" >/dev/null || git tag -a "v$v" -m "v$v"
git push -q && git push -q --tags
'''

FAKE_DTC_BUMP = r'''#!/usr/bin/env bash
set -e
if [[ "$1" == --set ]]; then
  sed -i.bak "s/^version = \".*\"/version = \"$2\"/" pyproject.toml; rm -f pyproject.toml.bak
  git commit -q -am "Bump version: → $2"; git tag -a "v$2" -m "v$2"
fi
git push -q && git push -q --tags
'''

STUDIO_EM = r'''#!/usr/bin/env bash
set -e
case "$1 $2" in
  "s3d status") exit 0 ;;
  "devrel --yes")
    n=$(( $(git tag -l 'v*' | wc -l) + 1 )); echo "$n" > version.txt
    git commit -q -am "build: dev release 1.6.0-dev.$n"; git tag "v1.6.0-dev.$n"
    git push -q origin HEAD && git push -q origin "v1.6.0-dev.$n"
    gh _add-run release.yml "v1.6.0-dev.$n" ;;
  *) exit 2 ;;
esac
'''

EMTOOLS_EM = r'''#!/usr/bin/env bash
set -e
case "$1" in
  rebundle)
    v="$(sed -n 's/^version = "\(.*\)"/\1/p' ../s3Dgraphy/pyproject.toml)"
    for cp in wheels/cp311 wheels/cp313; do rm -f $cp/s3dgraphy-*.whl; : > "$cp/s3dgraphy-$v-py3-none-any.whl"; done
    echo "{\"s3dgraphy\": \"$v\"}" > em_setup/datamodel.fingerprint.json ;;
  manifest)
    cp="cp${2//./}"; { echo "wheels = ["; for w in wheels/$cp/*.whl; do echo "  \"./$w\","; done; echo "]"; } > blender_manifest.toml ;;
  *) exit 2 ;;
esac
'''

EMTOOLS_VENV_PY = r'''#!/usr/bin/env bash
d="$(cd "$(dirname "$0")/.." && pwd)"
case "$1" in
  -c) cat "$d/versions" ;;
  -m)
    if [[ "$2" == pip ]]; then
      s="$(sed -n 1p "$d/versions")"; t="$(sed -n 2p "$d/versions")"
      for a in "$@"; do case "$a" in s3dgraphy==*) s="${a#*==}";; dtcstamp==*) t="${a#*==}";; esac; done
      printf '%s\n%s\n' "$s" "$t" > "$d/versions"
    elif [[ "$2" == pytest ]]; then exit "${FAKE_PYTEST_RC:-0}"; fi ;;
esac
'''

CHANGELOG = "# Changelog\n\n## [0.1.3] — YYYY-MM-DD <!-- the date is written when the tag is made -->\n\nNew.\n"


# ── the world ─────────────────────────────────────────────────────────────────

def _x(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text).lstrip("\n") if not text.startswith("#!") else text, encoding="utf-8")
    p.chmod(0o755)


class World:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.ws = tmp / "ws"
        self.bin = tmp / "bin"
        self.state = tmp / "state"
        for d in (self.ws, self.bin, self.state, tmp / "origins", tmp / "t"):
            d.mkdir(parents=True)
        gitcfg = tmp / "gitconfig"
        gitcfg.write_text("[user]\n\tname = Test\n\temail = test@example.org\n"
                          "[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "EM_RELEASE_", "GIT_"))}
        self.env.update({
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_GLOBAL": str(gitcfg), "GIT_CONFIG_NOSYSTEM": "1",
            "FAKE_STATE": str(self.state),
            "EM_RELEASE_PARENT": str(self.ws), "EM_RELEASE_PIP": str(self.bin / "pip"),
            "EM_RELEASE_PYTHON": str(self.bin / "fakepython"), "EM_RELEASE_TMP": str(tmp / "t"),
            "EM_RELEASE_POLL": "0.02", "EM_RELEASE_WAIT_TAG": "3", "EM_RELEASE_WAIT_RUN": "3",
            "EM_RELEASE_WAIT_PYPI": "5", "EM_RELEASE_WAIT_BUILD": "5", "EM_RELEASE_PROGRESS": "0.02",
            "EM_RELEASE_DOWNSTREAM": json.dumps([{"repo": "EM-blender-tools", "cmd": [
                "bash", "-c", 'echo "$FAKE_DOWNSTREAM_SAYS"; exit "${FAKE_DOWNSTREAM_RC:-0}"']}]),
        })
        self.env.pop("PYTHONPATH", None)
        _x(self.bin / "gh", FAKE_GH)
        _x(self.bin / "pip", FAKE_PIP)
        _x(self.bin / "fakepython", FAKE_PYTHON)

        self.repo("s3Dgraphy", {
            "pyproject.toml": f'[project]\nname = "s3dgraphy"\nversion = "1.6.0.dev27"\ndependencies = [\n'
                              f'    "dtcstamp>=0.1.2",  # 0.1.1 lacks stamp_description\n]\n',
            "em.sh": S3D_EM, "bump_and_push.sh": S3D_TAG_ONLY,
            "scripts/verifica-provenance.sh": "#!/usr/bin/env bash\nexit 0\n",
            "CHANGELOG.md": f"## [{V}]\n"})
        dtc_files = {"pyproject.toml": '[project]\nname = "dtcstamp"\nversion = "0.1.2"\n',
                     "dtcstamp.py": '__version__ = "0.1.2"\n',
                     ".bumpversion.cfg": "[bumpversion]\ncurrent_version = 0.1.2\n",
                     "CHANGELOG.md": CHANGELOG}
        dtc_files["bump_and_push.sh"] = (REAL_DTC_BUMP.read_text(encoding="utf-8")
                                         if REAL_DTC_BUMP.exists() else FAKE_DTC_BUMP)
        self.repo("dtcstamp", dtc_files)
        self.repo("EMStudio", {"tools/requirements.txt": "s3dgraphy[geo,rdf]==1.6.0.dev27\n",
                               "version.txt": "0\n", "em.sh": STUDIO_EM})
        self.repo("EM-blender-tools", {
            "scripts/requirements_wheels.txt": "s3dgraphy>=1.6.0.dev23,<1.7.0\ndtcstamp>=0.1.2\n",
            ".gitignore": "wheels/\n/blender_manifest.toml\n.venv/\n", "em.sh": EMTOOLS_EM,
            "em_setup/datamodel.fingerprint.json": '{"s3dgraphy": "1.6.0.dev27"}\n'})
        et = self.ws / "EM-blender-tools"
        for cp in ("cp311", "cp313"):
            (et / "wheels" / cp).mkdir(parents=True)
            for w in ("s3dgraphy-1.6.0.dev27-py3-none-any.whl", "dtcstamp-0.1.2-py3-none-any.whl"):
                (et / "wheels" / cp / w).write_text("")
        _x(et / ".venv" / "bin" / "python", EMTOOLS_VENV_PY)
        (et / ".venv" / "versions").write_text("1.6.0.dev26\n0.1.2\n")
        self.repo("stratigraph-server", {"pyproject.toml": 'dependencies = [\n    "s3dgraphy[geo,rdf]==1.6.0.dev27",\n]\n'})
        self.repo("stratigraph-templates", {"registry/s3dgraphy-snapshot.json": '{\n  "s3dgraphy_version": "1.6.0.dev27"\n}\n'})
        self.repo("stratigraph-chatbot", {"pyproject.toml": 'dependencies = [\n    "s3dgraphy>=1.6.0.dev22",\n]\n',
                                          "schede/a.json": "{}\n"})
        self.repo("3D-survey-collection", {"README.md": "3DSC\n"})

    def repo(self, name: str, files: dict):
        origin = self.tmp / "origins" / f"{name}.git"
        work = self.ws / name
        self.git(self.tmp, "init", "-q", "--bare", str(origin))
        self.git(self.tmp, "init", "-q", str(work))
        for rel, text in files.items():
            p = work / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            if rel.endswith(".sh") or text.startswith("#!"):
                p.chmod(0o755)
        self.git(work, "add", "-A")
        self.git(work, "commit", "-q", "-m", "start")
        self.git(work, "remote", "add", "origin", str(origin))
        self.git(work, "push", "-q", "-u", "origin", "main")

    def git(self, cwd, *args) -> str:
        return subprocess.run(["git", *args], cwd=str(cwd), env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def release(self, *args, input=None, **fake) -> subprocess.CompletedProcess:
        env = dict(self.env, **{k: str(v) for k, v in fake.items()})
        return subprocess.run([sys.executable, str(RELEASE), *args], env=env, input=input or "",
                              capture_output=True, text=True, timeout=180)

    def origin_tags(self, name: str) -> str:
        return self.git(self.ws / name, "ls-remote", "--tags", "origin")

    def snapshot(self) -> dict:
        return {n: (self.git(self.ws / n, "rev-parse", "HEAD"), self.git(self.ws / n, "status", "--porcelain"))
                for n in os.listdir(self.ws)}


FULL = (V, "--dtcstamp", D, "--desktop")


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def _all(r) -> str:
    return r.stdout + r.stderr


# ── the tests ─────────────────────────────────────────────────────────────────

def test_the_whole_row_in_dry_run_writes_nothing(world):
    before = world.snapshot()
    r = world.release(*FULL, "--dry-run")
    assert r.returncode == 0, _all(r)
    for n in range(1, 12):
        assert f" {n:>2} " in r.stdout, f"step {n} missing:\n{r.stdout}"
    assert "  ✓  1 done" in r.stdout
    assert "  →  2 to do" in r.stdout
    assert "would run in dtcstamp: ./bump_and_push.sh --set 0.1.3" in r.stdout
    assert "would run in s3Dgraphy: ./em.sh propagate --pins --yes" in r.stdout
    assert "would run in EMStudio: ./em.sh devrel --yes" in r.stdout
    assert "--dry-run: nothing written" in r.stdout
    assert world.snapshot() == before
    assert not (world.state / "pypi").exists()
    assert "workflow run" not in (world.state / "gh.log").read_text()


def test_the_round_goes_through_and_status_says_done(world):
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    assert f"refs/tags/v{V}" in world.origin_tags("s3Dgraphy")
    assert f"refs/tags/v{D}" in world.origin_tags("dtcstamp")
    s3d = world.ws / "s3Dgraphy"
    assert world.git(s3d, "log", "--format=%s", "-2").splitlines() == [
        f"Bump version: 1.6.0.dev27 → {V}", f"Require dtcstamp {D}"]
    assert f'"dtcstamp>={D}",  # 0.1.1 lacks stamp_description' in world.git(s3d, "show", f"v{V}:pyproject.toml")
    subjects = {n: world.git(world.ws / n, "log", "-1", "--format=%s") for n in
                ("stratigraph-templates", "stratigraph-chatbot", "stratigraph-server", "EM-blender-tools")}
    assert subjects == {
        "stratigraph-templates": f"Snapshot s3Dgraphy {V} from PyPI",
        "stratigraph-chatbot": f"Vendor the schede against s3Dgraphy {V} and require it",
        "stratigraph-server": f"Pin s3dgraphy {V} in one place and its two copies",
        "EM-blender-tools": f"Bundle s3dgraphy {V} and dtcstamp {D}"}
    assert f'"s3dgraphy>={V}"' in world.git(world.ws / "stratigraph-chatbot", "show", "HEAD:pyproject.toml")
    req = world.git(world.ws / "EM-blender-tools", "show", "HEAD:scripts/requirements_wheels.txt")
    assert req.splitlines() == [f"s3dgraphy>={V},<1.7.0", f"dtcstamp>={D}"]
    assert sorted(p.name for p in (world.ws / "EM-blender-tools" / "wheels" / "cp313").iterdir()) == [
        f"dtcstamp-{D}-py3-none-any.whl", f"s3dgraphy-{V}-py3-none-any.whl"]
    # the desktop: EMStudio's pin commit, pushed, then devrel's tag
    studio = world.ws / "EMStudio"
    assert world.git(studio, "log", "--format=%s", "-2").splitlines() == [
        "build: dev release 1.6.0-dev.1", f"Pin s3dgraphy {V}"]
    assert "https://example.invalid/releases/v1.6.0-dev.1" in r.stdout
    # every repository pushed
    for n in os.listdir(world.ws):
        assert world.git(world.ws / n, "status", "--porcelain") == "", n
        assert world.git(world.ws / n, "rev-list", "--count", "@{u}..HEAD") == "0", n
    # and status agrees, with its proofs
    st = world.release("status", *FULL)
    assert st.returncode == 0, _all(st)
    assert st.stdout.count(" done ") == 12, st.stdout       # 0 … 11
    assert f"s3dgraphy {V} is on PyPI" in st.stdout and f"dtcstamp {D} is on PyPI" in st.stdout
    assert "every step is done" in st.stdout
    # a second run does nothing and says so
    again = world.release(*FULL, "--yes")
    assert again.returncode == 0, _all(again)
    assert again.stdout.count("already done") == 10, again.stdout


@pytest.mark.skipif(not REAL_DTC_BUMP.exists(), reason="../dtcstamp/bump_and_push.sh is not next door")
def test_dtcstamp_step_dates_the_changelog_in_the_tagged_commit(world):
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    log = world.git(world.ws / "dtcstamp", "show", f"v{D}:CHANGELOG.md")
    assert f"## [{D}] — " in log and "YYYY-MM-DD" not in log


def test_resume_after_step_2(world):
    r = world.release(*FULL, "--yes", FAKE_FAIL="dispatch")
    assert r.returncode == 1, _all(r)
    assert f"refs/tags/v{D}" in world.origin_tags("dtcstamp")      # the tag went, the dispatch did not
    st = world.release("status", *FULL)
    assert "  →  2 to do" in st.stdout and f"tag v{D} on origin" in st.stdout
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    assert f"tag v{D} already on origin — skipped" in r.stdout
    assert world.git(world.ws / "dtcstamp", "tag", "-l").splitlines() == [f"v{D}"]


def test_resume_after_step_4(world):
    r = world.release(*FULL, "--yes", FAKE_FAIL="dispatch-s3d")
    assert r.returncode == 1, _all(r)
    assert f"refs/tags/v{V}" in world.origin_tags("s3Dgraphy")
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    out = r.stdout
    assert f"already done: dtcstamp {D} is on PyPI" in out
    assert "already done: dtcstamp>=" in out
    assert f"tag v{V} already on origin — skipped" in out
    assert world.git(world.ws / "s3Dgraphy", "log", "--format=%s").count("Bump version") == 1


def test_resume_after_a_push_refused_at_step_4(world):
    r = world.release(*FULL, "--yes", FAKE_FAIL="bump-push")
    assert r.returncode == 1, _all(r)
    assert f"refs/tags/v{V}" not in world.origin_tags("s3Dgraphy")
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    assert "./bump_and_push.sh --tag-only" in r.stdout          # the tag made, the push redone
    assert f"refs/tags/v{V}" in world.origin_tags("s3Dgraphy")


def test_resume_after_step_6(world):
    r = world.release(*FULL, "--yes", FAKE_FAIL="propagate")
    assert r.returncode == 1, _all(r)
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    for s in (f"already done: dtcstamp {D} is on PyPI", f"already done: s3dgraphy {V} is on PyPI",
              "already done: " + str(world.tmp / "t" / f"em-release-{V}")):
        assert s in r.stdout, r.stdout
    assert "./em.sh propagate --pins --yes" in r.stdout


def test_resume_after_step_9(world):
    # the first confirmation, then templates y, chatbot y, EMStudio N, server y, EMtools y
    r = world.release(*FULL, input="y\ny\ny\nn\ny\ny\n")
    assert r.returncode == 1, _all(r)
    assert "not committed: EMStudio" in _all(r)
    assert world.git(world.ws / "EMStudio", "status", "--porcelain")      # its pin still waits
    assert "git push" not in r.stdout                                     # step 10 was not reached
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    for n in ("stratigraph-templates", "stratigraph-chatbot", "stratigraph-server", "EM-blender-tools"):
        assert f"    {n}: committed (" in r.stdout, r.stdout
    assert f"EMStudio: " in r.stdout and f"Pin s3dgraphy {V}" in r.stdout
    assert world.git(world.ws / "EMStudio", "log", "--format=%s").count(f"Pin s3dgraphy {V}") == 1


def test_a_dirty_tree_stops_it_before_anything(world):
    (world.ws / "3D-survey-collection" / "notes.txt").write_text("unsaved")
    r = world.release(*FULL, "--yes")
    assert r.returncode == 1
    assert "3D-survey-collection: uncommitted changes the release did not make — notes.txt" in r.stderr
    assert "refs/tags" not in world.origin_tags("dtcstamp") + world.origin_tags("s3Dgraphy")
    st = world.release("status", *FULL)
    assert "  ·  1 blocked" in st.stdout and "after step 1" in st.stdout


def test_a_commit_not_pushed_stops_it(world):
    srv = world.ws / "stratigraph-server"
    (srv / "x.txt").write_text("x")
    world.git(srv, "add", "x.txt")
    world.git(srv, "commit", "-q", "-m", "Something of somebody")
    r = world.release(*FULL, "--yes")
    assert r.returncode == 1
    assert "stratigraph-server: 1 commit(s) not pushed that are not the release's" in r.stderr


def test_a_late_pypi_is_waited_for(world):
    r = world.release(*FULL, "--yes", FAKE_PYPI_DELAY=3)
    assert r.returncode == 0, _all(r)
    assert f"dtcstamp {D} on PyPI (pip download): look 1, not yet" in r.stdout
    assert f"s3dgraphy {V} on PyPI (pip download): look 3, not yet" in r.stdout


def test_a_pypi_later_than_the_cap_stops_with_the_command_that_resumes(world):
    r = world.release(*FULL, "--yes", FAKE_PYPI_DELAY=10 ** 6, EM_RELEASE_WAIT_PYPI=0.2)
    assert r.returncode == 75, _all(r)
    assert f"for dtcstamp {D} on PyPI (pip download) and it is not there yet" in r.stderr
    assert f"resume with:  ./em.sh release {V} --dtcstamp {D} --desktop" in r.stderr
    (world.state / "pypi" / f"dtcstamp=={D}").write_text("0")           # PyPI catches up
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    assert "not dispatched again" in r.stdout or f"already done: dtcstamp {D}" in r.stdout


def test_a_different_fingerprint_stops_it(world):
    r = world.release(*FULL, "--yes", FAKE_PYPI_DIGEST="sha256:bbb")
    assert r.returncode == 1
    assert "is NOT the working tree's" in r.stderr
    assert world.git(world.ws / "EMStudio", "status", "--porcelain") == ""   # step 6 not reached


def test_without_dtcstamp_and_desktop_those_steps_are_not_asked(world):
    r = world.release(V, "--dry-run")
    assert r.returncode == 0, _all(r)
    assert r.stdout.count("not asked") == 3
    assert "Bundle s3dgraphy 1.6.0.dev28\"" in r.stdout


def test_a_run_longer_than_the_cap_is_still_running_not_failed(world):
    r = world.release(*FULL, "--yes", FAKE_RUN_STATUS="in_progress", FAKE_WATCH_SLEEP=5,
                      EM_RELEASE_WAIT_BUILD=0.5, FAKE_PYPI_DELAY=10 ** 6)
    assert r.returncode == 75, _all(r)
    assert f"for publish.yml for v{D}" in r.stderr and "still running" in r.stderr
    (world.state / "pypi" / f"dtcstamp=={D}").write_text("4")             # the run uploads, PyPI is late
    r = world.release(*FULL, "--yes", FAKE_RUN_STATUS="in_progress")      # the run is watched, not redone
    assert r.returncode == 0, _all(r)
    assert "not dispatched again" in r.stdout


# ── dev29 (C1–C4), measured on the release of dev28 (2 Oct 2026) ──────────────

def test_no_subprocess_opens_a_pager(world):
    r = world.release(*FULL, "--yes")
    assert r.returncode == 0, _all(r)
    assert (world.state / "pager").read_text().split() == ["cat", "cat"]


def test_a_pip_install_right_after_the_publication_is_waited_for(world):
    r = world.release(*FULL, "--yes", FAKE_VENV_PIP_LATE=2)
    assert r.returncode == 0, _all(r)
    assert f"s3dgraphy[geo,rdf]=={V} installable from PyPI (pip install): look 1, not yet" in r.stdout
    assert "look 3, not yet" not in r.stdout


def test_a_pip_install_later_than_the_cap_stops_with_the_command_that_resumes(world):
    r = world.release(*FULL, "--yes", FAKE_VENV_PIP_LATE=10 ** 6, EM_RELEASE_WAIT_PYPI=0.3)
    assert r.returncode == 75, _all(r)
    assert "installable from PyPI (pip install) and it is not there yet" in r.stderr


def test_the_fingerprint_rewritten_at_step_7_is_the_release_s_own(world):
    r = world.release(*FULL, "--yes", FAKE_PYTEST_RC=1)          # stops at step 7
    assert r.returncode == 1, _all(r)
    et = world.ws / "EM-blender-tools"
    assert "em_setup/datamodel.fingerprint.json" in world.git(et, "status", "--porcelain")
    r = world.release(*FULL, "--yes")                            # the rerun is not blocked
    assert r.returncode == 0, _all(r)
    assert "uncommitted changes the release did not make" not in _all(r)
    files = world.git(et, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert sorted(files) == ["em_setup/datamodel.fingerprint.json",
                             "scripts/requirements_wheels.txt"]
    assert world.git(et, "status", "--porcelain") == ""


def test_a_draft_release_is_said_with_the_command_and_not_published(world):
    r = world.release(*FULL, "--yes", FAKE_DRAFT="true")
    assert r.returncode == 0, _all(r)
    assert "is a DRAFT" in r.stdout
    assert "gh release edit v1.6.0-dev.1 --draft=false" in r.stdout
    assert "release edit" not in (world.state / "gh.log").read_text()
    st = world.release("status", *FULL, FAKE_DRAFT="false")
    assert "v1.6.0-dev.1 is published (not a draft)" in st.stdout


# ── dev30 (R1, R2), measured on the release of dev29 (2 Oct 2026) ─────────────

RED = "FAILED tests/test_georef_roundtrip.py::test_push_without_epsg - AssertionError: 4326 written"


def test_step_0_runs_in_the_dry_run_and_is_green(world):
    before = world.snapshot()
    r = world.release(*FULL, "--dry-run")
    assert r.returncode == 0, _all(r)
    assert "0 · the downstream proof" in r.stdout
    assert "EM-blender-tools: green" in r.stdout
    assert "  ✓  0 done" in r.stdout
    assert world.snapshot() == before


def test_a_red_consumer_stops_the_release_before_any_tag(world):
    r = world.release(*FULL, "--yes", FAKE_DOWNSTREAM_RC=1, FAKE_DOWNSTREAM_SAYS=RED)
    assert r.returncode == 1, _all(r)
    err = _all(r)
    assert "step 0: a consumer is red" in err
    assert "EM-blender-tools: tests/test_georef_roundtrip.py::test_push_without_epsg" in err
    assert "AssertionError: 4326 written" in err
    assert world.origin_tags("dtcstamp") == "" and world.origin_tags("s3Dgraphy") == ""
    assert not (world.state / "pypi").exists()
    # and the dry-run says the same, red
    d = world.release(*FULL, "--dry-run", FAKE_DOWNSTREAM_RC=1, FAKE_DOWNSTREAM_SAYS=RED)
    assert d.returncode == 1 and "step 0: a consumer is red" in _all(d)


def test_a_known_failure_of_the_consumer_does_not_stop_it(world):
    (world.ws / "EM-blender-tools" / "known-test-failures.txt").write_text(
        "# known\ntests/test_georef_roundtrip.py::test_push_without_epsg\n")
    r = world.release(*FULL, "--dry-run", FAKE_DOWNSTREAM_RC=1, FAKE_DOWNSTREAM_SAYS=RED)
    assert r.returncode == 0, _all(r)
    assert "1 known failure(s) only" in r.stdout


def test_a_long_wait_says_the_jobs_and_their_step(world):
    r = world.release(*FULL, "--yes", FAKE_RUN_STATUS="in_progress", FAKE_VIEW_POLLS=2)
    assert r.returncode == 0, _all(r)
    out = r.stdout
    assert f"▸ 2 · publish.yml for v{D} · " in out
    assert f"▸ 4 · publish.yml for v{V} · " in out
    assert "▸ 11 · build desktop v1.6.0-dev.1 · " in out
    assert "macos-arm64  in progress · step «tauri build»" in out
    assert "linux        done ✓" in out
    # not a terminal: a new line per change of state, not one per look
    assert out.count(f"▸ 2 · publish.yml for v{D}") <= 3
