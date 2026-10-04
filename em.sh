#!/usr/bin/env bash
# s3Dgraphy — one entry point, the same ergonomics as EMtools' and EMStudio's
# `em.sh`. Every command calls what the repository already has:
#
#   setup/test/check   .venv + pytest + the `--check` modes of s3dgraphy.tools
#   docs               sphinx-build, as the Makefile's check-docs does
#   bump               ./bump_and_push.sh --set <version>
#   publish            gh workflow run publish.yml + scripts/verifica-provenance.sh
#   drift/propagate    s3dgraphy.tools.consumer_drift / wheel_drift, and the
#                      em.sh of the repositories next door
#   release            scripts/release.py: the whole round (dtcstamp → bump →
#                      publish → proof → propagate → EMtools → pin commits →
#                      the development node → push → desktop), each step
#                      skipped when already done
#
# The reports both shells print (fingerprint, PyPI, known failures, StratiField's
# schede) are scripts/em_report.py, shared with em.bat.
#
# THE INTERPRETER. `.venv` is the one `bump_and_push.sh` creates (it installs
# bump2version there). Measured on 2026-10-01 it is the Xcode Python 3.9 with
# every test dependency, but WITHOUT s3dgraphy itself — so a bare
# `.venv/bin/python -m pytest` stops at collection. Every command here runs with
# PYTHONPATH=src, which is how the 29 known failures were measured: the tests
# always read this source tree, never an installed copy.
#
# Start with:  ./em.sh help
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT="$(cd "$ROOT/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
REPORT=("$PY" "$ROOT/scripts/em_report.py")
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
#: the extras the test suite imports (measured: rdflib, sqlalchemy, pyproj, pypdf,
#: python-docx) + dev (pytest, build, bump2version) + docs (sphinx)
EXTRAS="dev,docs,rdf,sync,geo,pdf,docx"

log()  { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m⚠  %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

need_venv() {
  [[ -x "$PY" ]] || die "no .venv here. Run: ./em.sh setup"
  "$PY" -c 'import pytest, pandas, lxml' 2>/dev/null \
    || die "the .venv lacks the test dependencies. Run: ./em.sh setup"
}

source_version() { sed -n 's/^version = "\([^"]*\)".*/\1/p' "$ROOT/pyproject.toml" | head -1; }

#: `--dry-run` / `--yes` anywhere among the arguments; the rest stays in ARGS
DRY=0; YES=0; ARGS=()
parse_flags() {
  ARGS=()
  local a
  for a in "$@"; do
    case "$a" in
      --dry-run|-n) DRY=1 ;;
      --yes|-y)     YES=1 ;;
      *)            ARGS+=("$a") ;;
    esac
  done
}

#: in --dry-run: print the command; otherwise run it
run() {
  if [[ "$DRY" == 1 ]]; then printf '    would run: %s\n' "$*"; else "$@"; fi
}

confirm() {
  [[ "$YES" == 1 ]] && return 0
  local r
  read -r -p "$1 [y/N] " r
  [[ "$r" =~ ^[Yy]$ ]] || die "stopped: nothing was done"
}

# ══ help ══════════════════════════════════════════════════════════════════════

help_overview() {
  cat <<'EOF'
s3Dgraphy — ./em.sh <command> [args]

One entry point for the library's daily work. Every command calls what the
repository already has (pytest, the s3dgraphy.tools --check modes, sphinx,
bump_and_push.sh, publish.yml, verifica-provenance.sh). Commands that touch the
REMOTE or OTHER REPOSITORIES ask for confirmation and take --dry-run.

  setup                 Create or repair .venv: pip install -e '.[dev,docs,rdf,sync,geo,pdf,docx]'.
                          ./em.sh setup
  test [pytest args…]   pytest on this source; names any failure not in the known list.
                          ./em.sh test
  check                 Every --check: i18n, glyphs, node registry, JSON, em.ttl, consumer_drift.
                          ./em.sh check
  fingerprint [--json]  The datamodel fingerprint: one digest, and per file with versions.
                          ./em.sh fingerprint
  drift                 Which consumer next door is behind, and the command that syncs it.
                          ./em.sh drift
  docs [--strict]       Build the documentation, count the warnings (--strict = -W).
                          ./em.sh docs
  wheel                 Build the wheel from this tree; prove the fingerprint from the install.
                          ./em.sh wheel
  bump <version> [--dry-run] [--yes]
                        bump_and_push.sh --set <version>: commit, tag, PUSH. Asks first.
                          ./em.sh bump 1.6.0.dev26 --dry-run
  publish <version> [--dry-run] [--yes] [--testpypi]
                        Run publish.yml for tag v<version>, wait for PyPI, check provenance.
                          ./em.sh publish 1.6.0.dev26 --dry-run
  propagate [--pins] [--dry-run] [--yes]
                        After a publication: templates after-bump → StratiField sync-schede
                        → EMStudio sync + check:datamodel → (EMtools: printed only).
                          ./em.sh propagate --dry-run
  status                Branch, distance from origin, version here and on PyPI, fingerprint.
                          ./em.sh status
  release <V> [--dtcstamp X] [--desktop] [--dry-run] [--yes]
                        The whole round in one command, resumable: each step looks first
                        whether it is done. `release status [<V>]` = where it stands.
                          ./em.sh release 1.6.0.dev28 --dtcstamp 0.1.3 --desktop --dry-run
  metashape <progetto.psx> [--chunk N] [--out file.em.json]
                        Read a Metashape project without Metashape: its sheet (sensors,
                        photos, operations, CRS, warnings); --out writes its DTC chain.
                          ./em.sh metashape ../_datasets/x/progetto.psx --out x.em.json
  help [command]        This list, or the long help of one command.
                          ./em.sh help bump      (the five version paths are there)

A datamodel change, end to end (docs/DATAMODEL_PROPAGATION.md has the 14 steps;
`./em.sh release` runs the last ones in a row):
    ./em.sh check && ./em.sh test          # green, or only the known failures
    # update CHANGELOG.md, commit
    ./em.sh bump 1.6.0.dev26               # commit + tag + push
    ./em.sh publish 1.6.0.dev26            # PyPI + provenance
    ./em.sh propagate                      # the consumers next door; then commit each

--dry-run, everywhere it exists: shows, step by step, the commands that would be
run and the files that would change, and runs nothing.
EOF
}

help_setup() {
  cat <<'EOF'
./em.sh setup [--recreate]

WHAT IT DOES
  Makes .venv able to run every command here:
      .venv/bin/python -m pip install -e '.[dev,docs,rdf,sync,geo,pdf,docx]'
  and, when ../dtcstamp exists, pip install -e ../dtcstamp — the stamp tests
  import dtcstamp.stamp_description, which the PyPI release (0.1.1) does not
  have yet (measured 2026-10-01; StratiField's venv has 0.1.1 and fails there).
  A .venv that exists is kept (it is also bump_and_push.sh's, with bump2version);
  --recreate deletes it first. A new one is made with $PYTHON, else python3
  (requires-python >= 3.9; publish.yml builds on 3.9).

WHAT IT DOES NOT DO
  No git, no system packages. It does not change what tests read: every
  command runs with PYTHONPATH=src anyway.

WHEN
  After cloning; when a command says "Run: ./em.sh setup"; after
  bump_and_push.sh has created a bare .venv (it does when .venv is missing).

EXAMPLE
  $ ./em.sh setup
  ▸ keeping .venv (Python 3.9.6)
  ▸ pip install 'setuptools>=61' wheel   (pyproject [build-system])
  ▸ pip install -e '.[dev,docs,rdf,sync,geo,pdf,docx]'
  ▸ pip install -e ../dtcstamp
  ✓ .venv ready: s3dgraphy 1.6.0.dev25 from src/, pytest, sphinx, build

IF IT FAILS
  A wheel that will not build for 3.9 → PYTHON=python3.12 ./em.sh setup --recreate.
  Offline → pip cannot resolve; nothing else changed.
EOF
}

help_test() {
  cat <<'EOF'
./em.sh test [pytest args…]

WHAT IT DOES
  PYTHONPATH=src .venv/bin/python -m pytest tests [args], output saved to
  .venv/last-pytest.txt, then compares the FAILED tests with
  scripts/known-test-failures.txt (29 on 2026-10-01, all in sync/ GraphML
  projection, lossless round-trip, narrative fixtures, wheel_drift and the
  old-owner scan). It names every failure NOT in the list, and every listed
  test that now passes.

WHAT IT DOES NOT DO
  It does not edit the list: a fixed test is for you to remove, a new failure
  is for you to fix (or, if it is accepted, to add with a reason).

WHEN
  Before every commit that touches src/, and before bump.

EXAMPLE
  $ ./em.sh test
  29 failed, 2387 passed, 39 skipped, 792 warnings in 22.29s
  failed 29 · known 29 · new 0 · known-and-now-passing 0
  ✓ no new failure

IF IT FAILS
  "NEW tests/test_x.py::test_y" → that failure is yours: run it alone,
  ./em.sh test tests/test_x.py::test_y -x. Exit 1 means at least one NEW
  failure; the known ones never fail the command. With extra arguments (a
  subset) only new failures are reported, never "now passing".
EOF
}

help_check() {
  cat <<'EOF'
./em.sh check

WHAT IT DOES
  Every guard that is not the whole test suite, each with ✓/✗, all of them
  even after a failure, exit 1 if any failed:
    1. python -m s3dgraphy.tools.datamodel_i18n --check   (English column of the translations)
    2. python -m s3dgraphy.tools.glyphs_from_svg --check  (2d_glyphs vs the SVGs)
    3. python -m s3dgraphy.tools.sync_node_datamodel --check
                                                          (the node registry vs the classes)
    4. every *.json under src/s3dgraphy parses
    5. pytest tests/test_em_ttl_matches_the_datamodels.py (em.ttl vs the datamodels)
    6. python -m s3dgraphy.tools.consumer_drift --check   (EMStudio / templates not behind)

WHAT IT DOES NOT DO
  It rewrites nothing. The fix for each red line is printed by the tool:
  sync_node_datamodel (no flag), glyphs_from_svg --write, datamodel_i18n seed.

WHEN
  After editing a datamodel JSON, an SVG, em.ttl or a node class.

EXAMPLE
  $ ./em.sh check
  ✓ i18n · ✓ glyphs · ✓ node registry · ✓ JSON · ✓ em.ttl
  ✗ consumer_drift — EMStudio behind (nodes 1.6.17 vs 1.6.18) → ../EMStudio: ./em.sh sync

IF IT FAILS
  Read the tool's lines above the ✗. consumer_drift red is a task in another
  repository (./em.sh propagate), not a defect here.
EOF
}

help_fingerprint() {
  cat <<'EOF'
./em.sh fingerprint [--json]

WHAT IT DOES
  Prints api.datamodel_fingerprint() of this source: the one digest over the
  six datamodel JSONs, and per file its name, version and digest, plus the
  s3dgraphy version and em.ttl's owl:versionInfo. --json prints the raw
  {digest, versions, digests, files}.

WHAT IT DOES NOT DO
  Writes nothing; compares nothing (drift and status do).

EXAMPLE
  $ ./em.sh fingerprint
  s3dgraphy 1.6.0.dev25 (source: …/s3Dgraphy/src)
  datamodel sha256:aab44dda…3260
    nodes          1.6.18   s3Dgraphy_node_datamodel.json   sha256:23f00ba1…
    …
EOF
}

help_drift() {
  cat <<'EOF'
./em.sh drift

WHAT IT DOES
  1. python -m s3dgraphy.tools.consumer_drift — every consumer next door, per
     datamodel file, by version AND content: EMStudio, stratigraph-templates
     (ours, tracked), Heriverse (third party), local venvs.
  2. python -m s3dgraphy.tools.wheel_drift — the s3dgraphy wheel bundled in
     EM-blender-tools vs this source, by content.
  3. StratiField's vendored schede vs this fingerprint (scripts/em_report.py).
  Then a summary: who must sync, and the em.sh command that does it.

WHAT IT DOES NOT DO
  It changes no repository (propagate does). Exit 0 always: drift is news.

EXAMPLE
  $ ./em.sh drift
  …
  to sync:
    EMStudio            cd ../EMStudio && ./em.sh sync && (cd frontend && npm run check:datamodel)
    EM-blender-tools    cd ../EM-blender-tools && ./em.sh rebundle
EOF
}

help_docs() {
  cat <<'EOF'
./em.sh docs [--strict]

WHAT IT DOES
  sphinx-build -b html docs docs/_build/html (the Makefile's `html` target,
  with .venv's sphinx and PYTHONPATH=src), then counts the WARNING lines.
  --strict adds -W, like `make check-docs`: the first warning is an error.
  The full log is docs/_build/sphinx.log.

WHAT IT CHANGES
  docs/_build/ (ignored) — and docs/generated-report.md, which is TRACKED:
  conf.py regenerates it on builder-inited from the datamodels
  (s3dgraphy.tools.deliverable_report). A diff there after a datamodel change
  is expected; review and commit it with the change.

EXAMPLE
  $ ./em.sh docs
  ✓ docs built: docs/_build/html/index.html — 12 warning(s) (log: docs/_build/sphinx.log)

IF IT FAILS
  "No module named sphinx" → ./em.sh setup. A warning count that grew → read
  the log; ./em.sh docs --strict stops at the first one.
EOF
}

help_wheel() {
  cat <<'EOF'
./em.sh wheel

WHAT IT DOES
  1. copies this working tree (tracked + untracked-not-ignored files, i.e.
     what the next commit would hold; build/ and dist/ never) to a temp dir;
  2. python -m build --wheel --no-isolation there (no network);
  3. lists that the wheel holds s3dgraphy/datamodel.py and the six datamodel
     JSONs;
  4. a THROWAWAY venv: pip install --no-deps --no-index <wheel>, dependencies
     borrowed from .venv by a .pth, run from / so the source tree cannot leak
     in; s3dgraphy.__file__ must be in the throwaway venv, and the fingerprint
     computed from the INSTALLED package must equal this source's.

WHAT IT DOES NOT DO
  It does not publish, and it leaves nothing behind (the temp dir is removed;
  the wheel's path is printed before). This repo's build/ and dist/ untouched.

WHEN
  Before bump/publish, when package-data changed (a new JSON, a new data dir).

EXAMPLE
  $ ./em.sh wheel
  ▸ build s3dgraphy-1.6.0.dev25-py3-none-any.whl (2.4 MB)
  ✓ the wheel holds datamodel.py and the 6 datamodel JSONs
  ✓ installed fingerprint sha256:aab44dda… = source fingerprint

IF IT FAILS
  A missing JSON → pyproject.toml [tool.setuptools.package-data].
  Fingerprints differ → a datamodel file is not packaged, or packaged stale.
EOF
}

help_bump() {
  cat <<'EOF'
./em.sh bump <version> [--dry-run] [--yes]
./em.sh bump dev [--dry-run] [--yes]        (the next .devN: 1.6.0.dev25 → 1.6.0.dev26)

WHAT IT DOES
  Checks, then runs  ./bump_and_push.sh --set <version>,  which:
    · writes <version> into pyproject.toml, src/s3dgraphy/__init__.py and
      .bumpversion.cfg;
    · git commit -m "Bump version: <old> → <version>" (those three files);
    · git tag -a v<version>;
    · git push  &&  git push --tags   ← the REMOTE. Asks before this script runs.
  The checks: a PEP 440 version after the current one; tag v<version> absent
  here and on origin; the version named in CHANGELOG.md (a warning, not a stop:
  you are reminded to write what it carries).

WHAT IT DOES NOT DO
  It does not publish to PyPI (./em.sh publish does), does not edit the
  CHANGELOG, does not touch the consumers. NOTE: `git push --tags` pushes EVERY
  local tag, not only the new one — look at `git tag` if you keep local ones.

--dry-run
  Shows, step by step, the commands that would be run and the files that would
  change (old → new version line by line), and runs nothing.

WHICH VERSION NUMBER?
  s3Dgraphy writes PEP 440 (1.6.0.dev25). EMStudio writes SemVer (1.6.0-dev.12):
  same idea, different spelling — never copy one into the other.

  Measured on 2026-10-01 — what the existing tools do with a .devN:
    · bump_and_push.sh takes patch | minor | major (through bump2version),
      --tag-only/-t, or --set <VERSION>. Its patch/minor/major use the default
      bump2version parse (major.minor.patch) and DROP the .devN: from
      1.6.0.dev25, `patch` gives 1.6.1 (not 1.6.0), `minor` 1.7.0, `major`
      2.0.0 (bump2version --dry-run, on a copy). So on a dev line every path
      below goes through --set, and this command only uses --set.
    · setup_versioning.py reads the whole string (`version = "…"`), copies it
      into .bumpversion.cfg, and tests `bump2version --dry-run patch`; it knows
      nothing about .devN.
  The consumers' pins, measured the same day:
    EMStudio tools/requirements.txt        s3dgraphy[geo,rdf]==1.6.0.dev22   exact
    EM-blender-tools requirements_wheels   s3dgraphy>=1.6.0.dev23,<1.7.0     range + a bundled wheel
    StratiField pyproject                  s3dgraphy>=1.6.0.dev22            floor
    StratiGraph Server pyproject           s3dgraphy[geo,rdf]==1.6.0.dev12   exact (./bump-s3dgraphy.sh)
  PEP 440: `<1.7.0` also excludes 1.7.0's pre-releases (1.7.0.dev1), and a
  specifier that names a .devN lets pip pick pre-releases.

  1. dev → dev        1.6.0.dev25 → 1.6.0.dev26
     Every day: any change the consumers must see.
       ./em.sh bump dev            (or ./em.sh bump 1.6.0.dev26)
       ./em.sh publish 1.6.0.dev26
       ./em.sh propagate
     Pins: EMtools' range takes it (rebundle the wheel); StratiField's floor
     takes it; EMStudio's exact pin does NOT move by itself:
     ../EMStudio: ./em.sh s3d pin 1.6.0.dev26. propagate: yes, when the
     datamodel or anything a consumer vendors changed.

  2. dev → release    1.6.0.dev26 → 1.6.0
     When 1.6 is closed: drop the .devN.
       ./em.sh bump 1.6.0          (NOT `bump_and_push.sh patch`: that gives 1.6.1)
       ./em.sh publish 1.6.0
     Pins: 1.6.0 satisfies >=1.6.0.devN,<1.7.0 (EMtools: rebundle) and the
     floors; EMStudio: ./em.sh s3d pin 1.6.0. propagate: yes (the snapshot and
     the compiled schede record the s3dgraphy version).
     MEASURED 2026-10-01: tag v1.6.0 ALREADY EXISTS, here and on origin
     (c1d2a18, 2026-05-17, "Bump version: 0.1.42 → 1.6.0"), and 1.6.0 is NOT
     on PyPI. So `./em.sh bump 1.6.0` stops at "tag v1.6.0 already exists".
     Before closing 1.6, decide what that old tag is (move it — a tag others
     may have fetched — or release as 1.6.1); this command will not decide it.

  3. patch            1.6.0 → 1.6.1
     A fix on a published version, no breaking datamodel change.
       ./em.sh bump 1.6.1          (from a final release, bump_and_push.sh patch does the same)
       ./em.sh publish 1.6.1
     Pins: inside every range; EMStudio pin by hand. propagate: only if a
     datamodel file changed (./em.sh drift says).

  4. minor            1.6.x → 1.7.0.dev1
     A new line of development.
       ./em.sh bump 1.7.0.dev1     (NOT `minor`: that gives 1.7.0, a final release)
       ./em.sh publish 1.7.0.dev1
     Pins: <1.7.0 EXCLUDES it — EMtools stays on 1.6 until you raise its pin to
     >=1.7.0.dev1,<1.8.0 (scripts/requirements_wheels.txt) and rebundle;
     EMStudio: ./em.sh s3d pin 1.7.0.dev1. propagate: yes, once the pins allow it.

  5. major            1.x → 2.0.0.dev1
     A change that breaks the format (em.json, the datamodel's shape).
       ./em.sh bump 2.0.0.dev1
     Pins: every range excludes it; each consumer moves on purpose, with its
     own migration. propagate: repository by repository, never in one go.

EXAMPLE
  $ ./em.sh bump 1.6.0.dev26 --dry-run
  bump 1.6.0.dev25 → 1.6.0.dev26 on s3dgraphy_v1.6dev
    pyproject.toml               version = "1.6.0.dev25" → "1.6.0.dev26"
    src/s3dgraphy/__init__.py    __version__ = "1.6.0.dev25" → "1.6.0.dev26"
    .bumpversion.cfg             current_version = 1.6.0.dev25 → 1.6.0.dev26
    would run: ./bump_and_push.sh --set 1.6.0.dev26
      = git add …; git commit; git tag -a v1.6.0.dev26; git push; git push --tags

IF IT FAILS
  "tag v… already exists" → that version is taken: choose the next. A push
  refused (behind origin) → the commit and tag exist locally only: git pull
  --rebase, then git push && git push --tags (by hand), or delete the local tag
  (git tag -d v…) and start over.
EOF
}

help_publish() {
  cat <<'EOF'
./em.sh publish <version> [--dry-run] [--yes] [--testpypi]

WHAT IT DOES
  1. checks that tag v<version> exists on origin (git ls-remote) and that the
     version is not on PyPI already;
  2. asks, then: gh workflow run publish.yml --ref <this branch>
                   -f target=pypi -f version_tag=v<version>
     (Trusted Publisher: no token; the workflow builds from the TAG);
  3. prints the run's URL;
  4. ./scripts/verifica-provenance.sh <version> — the SAME script the workflow
     runs, with the same wait: it polls PyPI until the version is visible
     (up to ATTESA_TOTALE seconds, 300 by default, one line per attempt),
     then checks each file's attestation names ExtendedMatrix/s3Dgraphy.
  --testpypi publishes to TestPyPI instead and skips step 4 (provenance is
  checked on PyPI only, as in the workflow).

WHAT IT DOES NOT DO
  It does not bump or tag (./em.sh bump), and cannot unpublish: a version on
  PyPI is there for good.

--dry-run
  Shows the checks' results and the commands that would run; runs nothing.

EXAMPLE
  $ ./em.sh publish 1.6.0.dev26
  ✓ tag v1.6.0.dev26 is on origin · 1.6.0.dev26 is not on PyPI yet
  Run publish.yml (pypi, v1.6.0.dev26)? [y/N] y
  ▸ https://github.com/ExtendedMatrix/s3Dgraphy/actions/runs/…
  ▶ provenance di s3dgraphy 1.6.0.dev26
      indice s3dgraphy 1.6.0.dev26: tentativo 1/8, HTTP 404 — prossimo fra 5 s
  …
  ── 2 file su 2 con provenance ──

IF IT FAILS (verifica-provenance's exit codes)
  75 «pubblicata? non ancora visibile» → PyPI is slow, nothing is wrong yet:
     ATTESA_TOTALE=600 ./scripts/verifica-provenance.sh <version>
  1  a file without provenance → the Trusted Publisher (README «Pubblicare su PyPI»)
  3  provenance from another repository → stop and find out who published
  The workflow failing before upload → gh run view <id> --log-failed.
EOF
}

help_propagate() {
  cat <<'EOF'
./em.sh propagate [--pins] [--dry-run] [--yes]

WHAT IT DOES
  The chain after a publication (docs/DATAMODEL_PROPAGATION.md, steps 9–14),
  in the repositories next door that exist, in this order — templates before
  StratiField, because StratiField vendors what templates builds:
    1. stratigraph-templates   ./em.sh after-bump   (snapshot → validate → build)
    2. stratigraph-chatbot     ./em.sh sync-schede  (StratiField vendors the schede)
    3. EMStudio                ./em.sh sync ../s3Dgraphy, then
                               (cd frontend && npm run check:datamodel)
    4. EM-blender-tools        PRINTED, not run: ./em.sh rebundle (it rebuilds
                               the bundled wheels), then ./em.sh manifest 3.11|3.13
                               if the wheel's name changed
  Before: whether the source version is on PyPI (the pins point there). After
  each step: what THAT step changed in that repository (`git status --short`
  after, minus before). At the end: the
  repositories with changes to review and commit, and the pins to move by hand
  (EMStudio ./em.sh s3d pin <v>; StratiGraph Server ./bump-s3dgraphy.sh <v>).
  A step that fails stops the steps that depend on it (templates → StratiField).

--pins
  Also MOVES those two pins: runs ./em.sh s3d pin <v> in EMStudio (it refuses a
  version PyPI cannot install) and ./bump-s3dgraphy.sh <v> in stratigraph-server
  (pyproject, Dockerfile, compose), each only when it is not already <v>, and
  lists what each changed. Nothing is committed. EMtools' wheels stay printed.

WHAT IT DOES NOT DO
  It commits nothing, pushes nothing, rebuilds no wheel; without --pins it moves
  no pin.

--dry-run
  Shows, step by step, the commands that would be run in each repository and
  which repositories are present; runs nothing.

WHEN
  After ./em.sh publish, or whenever ./em.sh drift lists consumers behind.

EXAMPLE
  $ ./em.sh propagate --dry-run
  ▸ 1/4 stratigraph-templates   would run: ./em.sh after-bump
  ▸ 2/4 stratigraph-chatbot     would run: ./em.sh sync-schede
  ▸ 3/4 EMStudio                would run: ./em.sh sync …; npm run check:datamodel
  ▸ 4/4 EM-blender-tools        to run by hand: ./em.sh rebundle

IF IT FAILS
  It says which repository and step; that repository's own `./em.sh help`
  covers the failure. Nothing already done is undone: review with git diff.
EOF
}

help_metashape() {
  cat <<'EOF'
./em.sh metashape <progetto.psx> [--chunk N] [--out file.em.json] [--author ORCID]
                  [--no-digests] [--json]

WHAT IT DOES
  python -m s3dgraphy.importer.metashape_project: reads the .psx and the zips in
  <progetto>.files/ (doc.xml of project, chunks, frame and assets; the header of
  each mesh.ply) with the stdlib only — Metashape is not needed and not called.
  Prints a sheet: per chunk the sensors (resolution, EXIF make/model, photos,
  enabled, aligned, dates), the CRS (EPSG and kind), the markers, the assets
  with their counts, and the OPERATIONS in order with their parameters
  (MatchPhotos, AlignCameras, OptimizeCameras, BuildDepthMaps, BuildModel…,
  and 3DSC's LOD0), then every warning.
  --chunk N   a chunk by id or label (the sheet shows every chunk without it).
  --out F     writes the DTC chain of that chunk (default: the active one) as an
              em.json: one acquisition per sensor, one act per operation, the
              outputs as psx:// resources, the placement of each mesh. It hashes
              the photographs and each mesh.ply (about 3 s on San Pietro,
              2.7 GB); --no-digests skips it, and then writes no placement.
  --json      the reading as JSON instead of the sheet.

WHAT IT DOES NOT DO
  It writes nothing inside the project and launches nothing. No operator is
  invented: the project does not record one (--author is who ran the reading).

EXAMPLE
  $ ./em.sh metashape ../_datasets/SegniSanPietro/metashape-2026/sanpietro_LOD0.psx --chunk 1
  sanpietro_LOD0.psx — Agisoft Metashape 2.3.0.21954 (document 1.2.0)
  chunk 1 «Chunk 1_LOD0»  [active]
    photographs 273 · aligned 217
    …
    6. 3DSC LOD0 → model 2  (from model 1)  kind lod_generation

IF IT FAILS
  "no project at …" → the path. Anything the reader cannot read is a warning at
  the bottom of the sheet, never a stop.
EOF
}

help_status() {
  cat <<'EOF'
./em.sh status

WHAT IT DOES
  Branch; distance from its upstream as of the last fetch (ahead/behind — it
  does not fetch); uncommitted files; version in pyproject.toml and whether tag
  v<version> exists here and on origin; latest s3dgraphy on PyPI and whether
  this version is there; the datamodel digest.

WHAT IT DOES NOT DO
  Writes nothing, fetches nothing (git ls-remote and PyPI are read-only).

EXAMPLE
  $ ./em.sh status
  branch    s3dgraphy_v1.6dev · 0 ahead, 0 behind origin/s3dgraphy_v1.6dev
  version   1.6.0.dev25 · tag v1.6.0.dev25 here and on origin
  PyPI      latest 1.6.0.dev25 · 1.6.0.dev25 is on PyPI
  datamodel sha256:aab44dda…3260
EOF
}

help_release() {
  cat <<'EOF'
./em.sh release <V> [--dtcstamp X] [--desktop] [--dry-run] [--yes]
./em.sh release status [<V>] [--dtcstamp X] [--desktop]

WHAT IT DOES
  The steps of a dev round, in a row (scripts/release.py). Each one FIRST LOOKS
  whether it is already done and then skips it saying so: rerun the same
  command after an interruption and it resumes at the first step not done. No
  state file: the state is read from the repositories and from PyPI.
     0  the downstream proof, BEFORE any bump (writes nothing in a repository):
        the wheels of this tree (and of dtcstamp with --dtcstamp) built in
        /tmp/em-release-V-prova/, each consumer's tests run on them in a
        temporary venv — EM-blender-tools (pytest), stratigraph-server
        (pytest), EMStudio (sync + check:datamodel on a scratch copy, then
        graphml2em.py), stratigraph-templates (registry-snapshot + validate on
        a scratch copy). A failure not in that repository's
        known-test-failures.txt stops it with the repository, the test and the
        first line of the error. --dry-run runs it for real.
     1  preconditions: the 8 repositories clean (or dirty only where the release
        itself writes, once V is on PyPI), nothing foreign to push, gh logged in
     2  (--dtcstamp X) dtcstamp: ./bump_and_push.sh --set X (it dates the
        CHANGELOG) → the tag on origin (waits) → gh workflow run publish.yml →
        the run watched → pip download dtcstamp==X works (waits: PyPI's CDN is late)
     3  (--dtcstamp X) dtcstamp>=X in pyproject.toml and in EMtools'
        requirements_wheels.txt, each committed: "Require dtcstamp X"
     4  ./em.sh bump V → gh workflow run publish.yml, watched →
        verifica-provenance.sh (a run already dispatched is watched, never
        dispatched twice)
     5  the proof: venv in /tmp/em-release-V, pip install s3dgraphy[geo,rdf]==V,
        its fingerprint = ./em.sh fingerprint of this tree, or it stops
     6  ./em.sh propagate --pins
     7  EM-blender-tools: s3dgraphy>=V,<next minor · ./em.sh rebundle · the
        dtcstamp wheel · ./em.sh manifest 3.11 and 3.13 · .venv · pytest -q
     8  StratiField: "s3dgraphy>=V" in stratigraph-chatbot/pyproject.toml
     9  the pin commits: per repository git diff --stat, the message, [y/N]
    10  the development node: if the em-dev stack is up (em-dev-server running),
        [Y/n] → ./bump-s3dgraphy.sh V --build in stratigraph-server → /v1/health
        until it says "s3dgraphy": "V" (EM_RELEASE_WAIT_NODE); stack down: said,
        and the row goes on
    11  the push of what is ahead of origin: the list, one [y/N]
    12  (--desktop) EMStudio: ./em.sh s3d status --check → ./em.sh devrel --yes →
        release.yml watched → the release's URL, its assets and sizes, draft
        or published
    13  (--desktop) the EM site: [Y/n] → gh workflow run build.yml -R
        zalmoxes-laran/ExtendedMatrix-site --ref main, its jobs watched → GET
        https://extendedmatrix.org/tools/emstudio/ until it links the new tag's
        installers (EM_RELEASE_WAIT_SITE). The site reads the newest release
        that is NOT a draft when it is built: with a draft, it says so and
        builds nothing
  Every long wait SAYS what is happening: every 30 s (EM_RELEASE_PROGRESS) the
  jobs, their state, the step in progress and the times, with the expected end
  from the mean of the last three successful runs — one line rewritten in a
  terminal, a new line per change of state otherwise; GitHub's annotations
  after, as «GitHub's warnings». Every wait has a cap; past it, it says what it waited for and the command
  that resumes (exit 75). Caps and poll: EM_RELEASE_WAIT_TAG/_RUN/_PYPI/_BUILD,
  EM_RELEASE_POLL (scripts/release.py's docstring).

  status    The table of the steps — done / to do / blocked — with the proof
            (the tag, the version on PyPI, the hash of the pin's commit). Writes
            nothing. Without <V>: the version in pyproject.toml.

WHAT IT DOES NOT DO
  No credentials, no sudo, no deploy: only the gh login already there. It asks
  ONCE before anything goes to PyPI or GitHub (unless --yes), and again at the
  commits (per repository) and at the push.

--dry-run
  Step 0 for real (it writes nothing), then the steps with their verdict, the
  folder and the exact commands; writes nothing. Before the END of a round:
  ./em.sh release <V> --dry-run must reach step 0 green.

EXAMPLE
  ./em.sh release 1.6.0.dev28 --dtcstamp 0.1.3 --desktop --dry-run
  ./em.sh release 1.6.0.dev28 --dtcstamp 0.1.3 --desktop
  ./em.sh release status 1.6.0.dev28 --dtcstamp 0.1.3 --desktop
EOF
}

do_help() {
  case "${1:-}" in
    "") help_overview ;;
    setup|test|check|fingerprint|drift|docs|wheel|bump|publish|propagate|status|release|metashape) "help_$1" ;;
    *) die "no command '$1'. ./em.sh help lists them." ;;
  esac
}

# ══ setup / test / check ══════════════════════════════════════════════════════

do_setup() {
  local recreate=0
  [[ "${1:-}" == "--recreate" ]] && recreate=1
  if [[ "$recreate" == 1 && -d "$VENV" ]]; then
    warn "removing .venv (--recreate)"; rm -rf "$VENV"
  fi
  if [[ -x "$PY" ]] && "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    log "keeping .venv ($("$PY" --version 2>&1))"
  else
    local base="${PYTHON:-python3}"
    command -v "$base" >/dev/null || die "no $base on PATH: PYTHON=/path/to/python3 ./em.sh setup"
    log "creating .venv with $base ($("$base" --version 2>&1))"
    rm -rf "$VENV"; "$base" -m venv "$VENV"
  fi
  "$PY" -m pip install --quiet --upgrade pip
  #: [build-system] requires — `wheel` builds with --no-isolation, so they must
  #: be HERE (measured: the bump2version .venv had setuptools < 61 and no wheel)
  log "pip install 'setuptools>=61' wheel   (pyproject [build-system])"
  "$PY" -m pip install --quiet 'setuptools>=61' wheel
  log "pip install -e '.[$EXTRAS]'"
  (cd "$ROOT" && "$PY" -m pip install --quiet -e ".[$EXTRAS]")
  if [[ -f "$PARENT/dtcstamp/pyproject.toml" ]]; then
    log "pip install -e ../dtcstamp (the stamp tests need the source's stamp_description)"
    "$PY" -m pip install --quiet -e "$PARENT/dtcstamp"
  fi
  #: from / — in the repository root `import build` finds the build/ DIRECTORY
  #: and succeeds without the package (measured: it fooled this check once)
  (cd / && "$PY" -c 'import s3dgraphy, pytest, sphinx, build.util; print("  s3dgraphy", s3dgraphy.__version__, "from", s3dgraphy.__file__)')
  ok ".venv ready"
}

do_test() {
  need_venv
  local out="$VENV/last-pytest.txt" rc=0
  (cd "$ROOT" && "$PY" -m pytest "${@:-tests}" -p no:cacheprovider 2>&1) | tee "$out" | tail -n 3 || true
  echo
  "${REPORT[@]}" failures "$out" > "$out.cmp" || rc=$?
  if [[ $# -gt 0 ]]; then
    # a subset: "now passing" means nothing, only new failures do
    grep -v '^  fixed ' "$out.cmp" | sed 's/ · known-and-now-passing [0-9]*//'
  else
    cat "$out.cmp"
  fi
  rm -f "$out.cmp"
  [[ $rc == 0 ]] && ok "no new failure" || die "new failure(s) above — not in scripts/known-test-failures.txt"
}

do_check() {
  need_venv
  local failed=() name
  step() {
    name="$1"; shift
    log "$name"
    if (cd "$ROOT" && "$@"); then ok "$name"; else failed+=("$name"); printf '\033[1;31m✗ %s\033[0m\n' "$name"; fi
  }
  step "i18n (datamodel_i18n --check)"           "$PY" -m s3dgraphy.tools.datamodel_i18n --check
  step "glyphs (glyphs_from_svg --check)"        "$PY" -m s3dgraphy.tools.glyphs_from_svg --check
  step "node registry (sync_node_datamodel --check)" "$PY" -m s3dgraphy.tools.sync_node_datamodel --check
  step "JSON (every *.json under src/s3dgraphy)" "${REPORT[@]}" json-valid
  step "em.ttl (test_em_ttl_matches_the_datamodels)" "$PY" -m pytest -q -p no:cacheprovider tests/test_em_ttl_matches_the_datamodels.py
  step "consumer_drift --check"                  "$PY" -m s3dgraphy.tools.consumer_drift --check --root "$PARENT"
  echo
  if [[ ${#failed[@]} -eq 0 ]]; then ok "check: all 6 green"; return 0; fi
  printf '\033[1;31m✗ check: %d of 6 red — %s\033[0m\n' "${#failed[@]}" "$(IFS=';'; echo "${failed[*]}")" >&2
  return 1
}

# ══ fingerprint / drift / docs / wheel ════════════════════════════════════════

do_drift() {
  need_venv
  local out sf=0
  log "consumer_drift (datamodel copies, by version and content)"
  out="$("$PY" -m s3dgraphy.tools.consumer_drift --root "$PARENT" 2>&1 || true)"
  printf '%s\n' "$out"
  log "wheel_drift (the s3dgraphy bundled in EM-blender-tools, by content)"
  local wout; wout="$("$PY" -m s3dgraphy.tools.wheel_drift --root "$PARENT" 2>&1 || true)"
  printf '%s\n' "$wout"
  if [[ -d "$PARENT/stratigraph-chatbot/schede" ]]; then
    log "StratiField's vendored schede vs this datamodel"
    "${REPORT[@]}" stratifield "$PARENT/stratigraph-chatbot" || sf=$?
  fi
  echo
  echo "to sync (the em.sh of each repository; ./em.sh propagate runs the first three):"
  local any=0
  if grep -qE '→ EMStudio .* behind|→ EMStudio .*edited' <<<"$out"; then
    echo "  EMStudio            cd ../EMStudio && ./em.sh sync ../s3Dgraphy && (cd frontend && npm run check:datamodel)"; any=1
  fi
  if grep -qE '→ stratigraph-templates .* behind|→ stratigraph-templates .*edited' <<<"$out"; then
    echo "  stratigraph-templates  cd ../stratigraph-templates && ./em.sh after-bump"; any=1
  fi
  if [[ $sf == 1 ]]; then
    echo "  StratiField         cd ../stratigraph-chatbot && ./em.sh sync-schede   (after templates' build)"; any=1
  fi
  if grep -qiE 'stale|differ|behind' <<<"$wout"; then
    echo "  EM-blender-tools    cd ../EM-blender-tools && ./em.sh rebundle   (rebuilds the bundled wheels)"; any=1
  fi
  [[ $any == 1 ]] || echo "  nobody we own"
  echo "  (third-party copies — Heriverse — are news to send, not a task here)"
}

do_docs() {
  need_venv
  "$PY" -c 'import sphinx' 2>/dev/null || die "no sphinx in .venv. Run: ./em.sh setup"
  local strict=() log_file="$ROOT/docs/_build/sphinx.log" rc=0 n
  [[ "${1:-}" == "--strict" ]] && strict=(-W)
  mkdir -p "$ROOT/docs/_build"
  log "sphinx-build ${strict[*]:-} -b html docs docs/_build/html"
  (cd "$ROOT" && "$PY" -m sphinx ${strict[@]+"${strict[@]}"} -b html docs docs/_build/html) > "$log_file" 2>&1 || rc=$?
  n="$(grep -c 'WARNING' "$log_file" || true)"
  grep 'WARNING' "$log_file" | sed 's/^/  /' | head -20 || true
  [[ "$n" -gt 20 ]] && echo "  … $((n - 20)) more in $log_file"
  git -C "$ROOT" status --short -- docs/generated-report.md
  if [[ $rc == 0 ]]; then
    ok "docs built: docs/_build/html/index.html — $n warning(s) (log: docs/_build/sphinx.log)"
  else
    die "sphinx-build failed (exit $rc) — $n warning(s); tail of docs/_build/sphinx.log:
$(tail -5 "$log_file")"
  fi
}

do_wheel() {
  need_venv
  (cd / && env -u PYTHONPATH "$PY" -c '
import build.util, wheel, setuptools, sys
sys.exit(0 if int(setuptools.__version__.split(".")[0]) >= 61 else 1)' 2>/dev/null) \
    || die "the .venv cannot build a wheel without isolation (needs build, wheel, setuptools>=61). Run: ./em.sh setup"
  local tmp; tmp="$(mktemp -d "${TMPDIR:-/tmp}/s3d-wheel.XXXXXX")"
  trap 'rm -rf "$tmp"' RETURN
  log "copy the working tree (tracked + untracked-not-ignored) to $tmp/src-tree"
  mkdir -p "$tmp/src-tree"
  (cd "$ROOT" && git ls-files -z -co --exclude-standard | xargs -0 tar -cf - 2>/dev/null) | tar -xf - -C "$tmp/src-tree"
  log "python -m build --wheel --no-isolation"
  (cd "$tmp/src-tree" && env -u PYTHONPATH "$PY" -m build --wheel --no-isolation --outdir "$tmp/dist" > "$tmp/build.log" 2>&1) \
    || die "the build failed; last lines:
$(tail -15 "$tmp/build.log")"
  local whl; whl="$(ls "$tmp"/dist/*.whl)"
  log "built $(basename "$whl") ($(du -h "$whl" | cut -f1 | tr -d ' '))"
  "$PY" - "$whl" <<'EOF'
import sys, zipfile
names = set(zipfile.ZipFile(sys.argv[1]).namelist())
need = ["s3dgraphy/datamodel.py"] + ["s3dgraphy/JSON_config/" + f for f in (
    "s3Dgraphy_node_datamodel.json", "node_registry.generated.json",
    "s3Dgraphy_connections_datamodel.json", "em_visual_rules.json",
    "em_qualia_types.json", "datamodel_translations.json")]
missing = [n for n in need if n not in names]
if missing:
    print("  missing from the wheel: " + ", ".join(missing)); raise SystemExit(1)
print(f"  ✓ the wheel holds datamodel.py and the 6 datamodel JSONs ({len(names)} files)")
EOF
  log "throwaway venv: pip install --no-deps --no-index the wheel"
  env -u PYTHONPATH "$PY" -m venv "$tmp/venv"
  #: without PYTHONPATH: with src/ on it pip sees src/s3dgraphy.egg-info (left
  #: by setup's editable install), says "already satisfied" and installs nothing
  env -u PYTHONPATH "$tmp/venv/bin/python" -m pip install --quiet --no-deps --no-index "$whl"
  #: the dependencies, borrowed from .venv — but NOT its s3dgraphy (if setup
  #: installed one editable, that .pth would shadow the wheel; checked below)
  local site deps
  site="$("$tmp/venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  deps="$(env -u PYTHONPATH "$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  echo "$deps" > "$site/zz-borrowed-deps.pth"
  local src_fp inst
  src_fp="$("$PY" -c 'from s3dgraphy.datamodel import datamodel_fingerprint as f; print(f()["digest"])')"
  inst="$(cd / && env -u PYTHONPATH "$tmp/venv/bin/python" -c '
import s3dgraphy, sys
from s3dgraphy.datamodel import datamodel_fingerprint as f
print(s3dgraphy.__file__); print(s3dgraphy.__version__); print(f()["digest"])')"
  local file ver digest
  file="$(sed -n 1p <<<"$inst")"; ver="$(sed -n 2p <<<"$inst")"; digest="$(sed -n 3p <<<"$inst")"
  echo "  installed s3dgraphy $ver from $file"
  [[ "$file" == "$(cd "$tmp" && pwd -P)/venv/"* || "$file" == "$tmp/venv/"* ]] || die "s3dgraphy was imported from outside the throwaway venv ($file): the test proves nothing"
  echo "  installed fingerprint $digest"
  echo "  source    fingerprint $src_fp"
  [[ "$digest" == "$src_fp" ]] || die "the installed datamodel is NOT the source's"
  ok "installed fingerprint = source fingerprint (the wheel and temp dir are removed now)"
}

# ══ bump / publish ════════════════════════════════════════════════════════════

origin_has_tag() { git -C "$ROOT" ls-remote --exit-code --tags origin "refs/tags/$1" >/dev/null 2>&1; }

do_bump() {
  parse_flags "$@"
  local v="${ARGS[0]:-}" cur branch
  [[ -n "$v" ]] || die "which version? ./em.sh bump 1.6.0.dev26  (./em.sh help bump: the five paths)"
  cur="$(source_version)"
  if [[ "$v" == "dev" ]]; then v="$("${REPORT[@]}" next-dev)" || exit 1; fi
  case "$v" in patch|minor|major)
    die "'$v' is bump_and_push.sh's bump2version mode, and it drops .devN ($cur → patch gives 1.6.1). Say the version: ./em.sh help bump";;
  esac
  "${REPORT[@]}" check-version "$v" || exit 1
  branch="$(git -C "$ROOT" branch --show-current)"
  echo "bump $cur → $v on $branch"
  printf '  %-28s version = "%s" → "%s"\n' pyproject.toml "$cur" "$v"
  printf '  %-28s __version__ = "%s" → "%s"\n' src/s3dgraphy/__init__.py "$cur" "$v"
  printf '  %-28s current_version = %s → %s\n' .bumpversion.cfg "$cur" "$v"
  git -C "$ROOT" rev-parse -q --verify "refs/tags/v$v" >/dev/null && die "tag v$v already exists here"
  origin_has_tag "v$v" && die "tag v$v already exists on origin"
  echo "  ✓ tag v$v is free here and on origin"
  if grep -q "$v" "$ROOT/CHANGELOG.md"; then
    echo "  ✓ CHANGELOG.md names $v"
  else
    warn "CHANGELOG.md does not name $v — write what it carries before you publish"
  fi
  local dirty; dirty="$(git -C "$ROOT" status --porcelain --untracked-files=no)"
  [[ -n "$dirty" ]] && warn "uncommitted changes (bump_and_push.sh commits only the three version files):
$dirty"
  echo "  steps:"
  echo "    ./bump_and_push.sh --set $v"
  echo "      = git add pyproject.toml src/s3dgraphy/__init__.py .bumpversion.cfg"
  echo "        git commit -m \"Bump version: $cur → $v\""
  echo "        git tag -a v$v -m v$v"
  echo "        git push && git push --tags      (the remote: origin/$branch, and EVERY local tag)"
  if [[ "$DRY" == 1 ]]; then echo "  --dry-run: nothing done"; return 0; fi
  confirm "Commit, tag v$v and PUSH to origin?"
  (cd "$ROOT" && ./bump_and_push.sh --set "$v")
  ok "v$v pushed. Next: ./em.sh publish $v"
}

do_publish() {
  parse_flags "$@"
  local v="" target=pypi a
  for a in "${ARGS[@]+"${ARGS[@]}"}"; do
    case "$a" in --testpypi) target=testpypi ;; *) v="$a" ;; esac
  done
  [[ -n "$v" ]] || die "which version? ./em.sh publish 1.6.0.dev26"
  command -v gh >/dev/null || die "the GitHub CLI (gh) is needed: brew install gh && gh auth login"
  local branch; branch="$(git -C "$ROOT" branch --show-current)"
  echo "publish s3dgraphy $v → $target"
  if origin_has_tag "v$v"; then echo "  ✓ tag v$v is on origin"; else
    [[ "$DRY" == 1 ]] && warn "tag v$v is NOT on origin (./em.sh bump $v first)" || die "tag v$v is not on origin: ./em.sh bump $v first"
  fi
  local rc=0; "${REPORT[@]}" pypi "$v" >/dev/null || rc=$?
  case "$rc" in
    0) [[ "$target" == pypi ]] && die "$v is already on PyPI: a version is published once. To re-check it: ./scripts/verifica-provenance.sh $v" ;;
    1) echo "  ✓ $v is not on PyPI yet" ;;
    *) warn "cannot reach PyPI to check whether $v is there" ;;
  esac
  echo "  steps:"
  echo "    gh workflow run publish.yml --ref $branch -f target=$target -f version_tag=v$v"
  [[ "$target" == pypi ]] && echo "    ./scripts/verifica-provenance.sh $v   (waits up to \${ATTESA_TOTALE:-300} s for PyPI)"
  if [[ "$DRY" == 1 ]]; then echo "  --dry-run: nothing done"; return 0; fi
  confirm "Run publish.yml ($target, v$v)? A published version cannot be withdrawn."
  (cd "$ROOT" && gh workflow run publish.yml --ref "$branch" -f target="$target" -f version_tag="v$v")
  sleep 5
  gh run list -R "$(cd "$ROOT" && gh repo view --json nameWithOwner -q .nameWithOwner)" \
     --workflow publish.yml -L 1 --json url,status -q '.[0] | "  ▸ \(.url) (\(.status))"' 2>/dev/null || true
  if [[ "$target" == testpypi ]]; then
    ok "dispatched to TestPyPI — provenance is checked on PyPI only"; return 0
  fi
  (cd "$ROOT" && ./scripts/verifica-provenance.sh "$v")
  ok "s3dgraphy $v is on PyPI with its provenance. Next: ./em.sh propagate"
}

# ══ propagate ═════════════════════════════════════════════════════════════════

do_propagate() {
  parse_flags "$@"
  local PINS=0 a
  for a in "${ARGS[@]+"${ARGS[@]}"}"; do
    case "$a" in
      --pins) PINS=1 ;;
      *) die "propagate: unknown argument '$a' (known: --pins, --dry-run, --yes)" ;;
    esac
  done
  local v; v="$(source_version)"
  local to_commit=() failed=() rc=0
  echo "propagate s3dgraphy $v (source: $ROOT) to the repositories in $PARENT"
  rc=0; "${REPORT[@]}" pypi "$v" || rc=$?
  [[ $rc == 1 ]] && warn "$v is not on PyPI: the vendored copies will follow the SOURCE, the pins cannot point at it yet"
  if [[ "$DRY" == 0 ]]; then confirm "Run the sync in the repositories next door (no commit, no push)?"; fi

  # one step: <n> <repo dir> <label> <command…>
  prop_step() {
    local n="$1" dir="$2" label="$3"; shift 3
    log "$n $label  ($dir)"
    if [[ ! -d "$PARENT/$dir" ]]; then echo "    not here — skipped"; return 2; fi
    if [[ "$DRY" == 1 ]]; then printf '    would run (in %s): %s\n' "$dir" "$*"; return 0; fi
    local before st
    before="$(git -C "$PARENT/$dir" status --short)"
    if (cd "$PARENT/$dir" && bash -c "$*"); then
      #: what THIS step changed: lines of `git status --short` that were not
      #: there before it (a file already dirty and dirtied again shows once)
      st="$(git -C "$PARENT/$dir" status --short | grep -vxF -f <(printf '%s\n' "$before") || true)"
      echo "    changed in $dir by this step:"
      if [[ -n "$st" ]]; then printf '%s\n' "$st" | sed 's/^/      /'; to_commit+=("$dir")
      else echo "      (nothing)"; fi
      [[ -n "$before" ]] && echo "    (already uncommitted there before: $(printf '%s\n' "$before" | wc -l | tr -d ' ') path(s))"
      return 0
    fi
    failed+=("$dir: $label"); printf '\033[1;31m✗ %s failed in %s\033[0m\n' "$label" "$dir"; return 1
  }

  local t=0
  if [[ -x "$PARENT/stratigraph-templates/em.sh" || "$DRY" == 1 ]]; then
    prop_step "1/4" stratigraph-templates "after-bump (snapshot → validate → build)" "./em.sh after-bump" || t=$?
  else
    echo "▸ 1/4 stratigraph-templates: no em.sh there — run the CLI by hand (DATAMODEL_PROPAGATION step 11)"; t=2
  fi
  if [[ $t == 1 ]]; then
    echo "▸ 2/4 stratigraph-chatbot: SKIPPED — templates' build failed, there is nothing new to vendor"
  elif [[ -x "$PARENT/stratigraph-chatbot/em.sh" || "$DRY" == 1 ]]; then
    prop_step "2/4" stratigraph-chatbot "sync-schede (StratiField vendors the compiled schede)" "./em.sh sync-schede" || true
  else
    prop_step "2/4" stratigraph-chatbot "sync-schede.sh" "./sync-schede.sh" || true
  fi
  prop_step "3/4" EMStudio "sync + check:datamodel" \
    "./em.sh sync '$ROOT' && (cd frontend && npm run check:datamodel)" || true
  log "4/4 EM-blender-tools — printed, not run (it rebuilds the wheels it ships):"
  if [[ -d "$PARENT/EM-blender-tools" ]]; then
    echo "    cd ../EM-blender-tools && ./em.sh rebundle"
    echo "    then, if the wheel's file name changed: ./em.sh manifest 3.11 && ./em.sh manifest 3.13"
    echo "    pin: scripts/requirements_wheels.txt $(grep -h '^s3dgraphy' "$PARENT/EM-blender-tools/scripts/requirements_wheels.txt" 2>/dev/null || echo '?')"
  else
    echo "    not here"
  fi
  echo
  local studio_pin="" server_pin=""
  [[ -f "$PARENT/EMStudio/tools/requirements.txt" ]] && \
    studio_pin="$(grep -h '^s3dgraphy' "$PARENT/EMStudio/tools/requirements.txt")"
  [[ -f "$PARENT/stratigraph-server/pyproject.toml" ]] && \
    server_pin="$(grep -m1 -o 's3dgraphy\[[^]]*\]==[^"]*' "$PARENT/stratigraph-server/pyproject.toml")"
  if [[ "$PINS" == 1 ]]; then
    #: --pins (dev27): the two pins that are a command each are MOVED here, and
    #: committed nowhere — EMStudio's `s3d pin` refuses a version PyPI cannot
    #: install, the server's script checks its three lines are one. EMtools'
    #: wheels stay printed (step 4/4): rebuilding a wheel is not a pin.
    echo "pins (--pins: moved, not committed):"
    if [[ -n "$studio_pin" && "$studio_pin" != *"==$v" ]]; then
      prop_step "pin" EMStudio "s3d pin $v (tools/requirements.txt)" "./em.sh s3d pin $v" || true
    elif [[ -n "$studio_pin" ]]; then echo "  EMStudio            $studio_pin (already $v)"; fi
    if [[ -n "$server_pin" && "$server_pin" != *"==$v" ]]; then
      prop_step "pin" stratigraph-server "bump-s3dgraphy.sh $v (pyproject + Dockerfile + compose)" "./bump-s3dgraphy.sh $v" || true
    elif [[ -n "$server_pin" ]]; then echo "  StratiGraph Server  $server_pin (already $v)"; fi
  else
    echo "pins to move by hand (not done here; ./em.sh propagate --pins moves them):"
    pin_line() {  # <label> <pin> <command>
      if [[ "$2" == *"==$v" ]]; then echo "  $1 $2 (already $v)"; else echo "  $1 $2 → $3"; fi
    }
    [[ -n "$studio_pin" ]] && pin_line "EMStudio           " "$studio_pin" "cd ../EMStudio && ./em.sh s3d pin $v"
    [[ -n "$server_pin" ]] && pin_line "StratiGraph Server " "$server_pin" "cd ../stratigraph-server && ./bump-s3dgraphy.sh $v"
  fi
  echo
  if [[ "$DRY" == 1 ]]; then echo "--dry-run: nothing done"; return 0; fi
  if [[ ${#to_commit[@]} -gt 0 ]]; then
    echo "to review and commit (nothing was committed):"; printf '  %s\n' "${to_commit[@]}"
  else
    echo "no repository changed"
  fi
  if [[ ${#failed[@]} -gt 0 ]]; then
    printf '\033[1;31m✗ failed: %s\033[0m\n' "$(IFS=';'; echo "${failed[*]}")" >&2; return 1
  fi
  ok "propagate done"
}

# ══ status ════════════════════════════════════════════════════════════════════

do_status() {
  need_venv
  local branch up v
  branch="$(git -C "$ROOT" branch --show-current)"
  up="$(git -C "$ROOT" rev-parse --abbrev-ref '@{u}' 2>/dev/null || true)"
  if [[ -n "$up" ]]; then
    read -r behind ahead < <(git -C "$ROOT" rev-list --left-right --count "$up...HEAD")
    echo "branch    $branch · $ahead ahead, $behind behind $up (as of the last fetch)"
  else
    echo "branch    $branch · no upstream"
  fi
  echo "changes   $(git -C "$ROOT" status --porcelain | wc -l | tr -d ' ') uncommitted path(s)"
  v="$(source_version)"
  local here="no" there="no"
  git -C "$ROOT" rev-parse -q --verify "refs/tags/v$v" >/dev/null && here="yes"
  origin_has_tag "v$v" && there="yes"
  echo "version   $v · tag v$v here: $here, on origin: $there"
  echo "PyPI      latest $("${REPORT[@]}" pypi 2>/dev/null || echo '?') · $("${REPORT[@]}" pypi "$v" 2>/dev/null | sed 's/ (latest.*//' || true)"
  echo "datamodel $("$PY" -c 'from s3dgraphy.datamodel import datamodel_fingerprint as f; print(f()["digest"])')"
}

# ══ dispatch ══════════════════════════════════════════════════════════════════

cmd="${1:-help}"; shift || true
case "$cmd" in
  help|-h|--help) do_help "${1:-}" ;;
  setup)       do_setup "$@" ;;
  test)        do_test "$@" ;;
  check)       do_check ;;
  fingerprint) need_venv; "${REPORT[@]}" fingerprint "$@" ;;
  drift)       do_drift ;;
  docs)        do_docs "$@" ;;
  wheel)       do_wheel ;;
  bump)        do_bump "$@" ;;
  publish)     do_publish "$@" ;;
  propagate)   do_propagate "$@" ;;
  status)      do_status ;;
  metashape)   [[ $# -ge 1 ]] || die "usage: ./em.sh metashape <progetto.psx> [--chunk N] [--out file.em.json]"
               if [[ -x "$PY" ]]; then "$PY" -m s3dgraphy.importer.metashape_project "$@"
               else python3 -m s3dgraphy.importer.metashape_project "$@"; fi ;;
  release)     if [[ -x "$PY" ]]; then "$PY" "$ROOT/scripts/release.py" "$@"; else python3 "$ROOT/scripts/release.py" "$@"; fi ;;
  *)           echo "unknown command '$cmd'" >&2; echo >&2; help_overview >&2; exit 2 ;;
esac
