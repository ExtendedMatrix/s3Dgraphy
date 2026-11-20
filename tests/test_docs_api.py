"""The API site (``docs-api/``, MICRO-API01): its examples run, its generated
reference is current.

* the Quickstart's examples (``docs-api/examples/*.py``) run with
  ``python -m em run`` on a COPY of Templu Mare — the file named by
  ``EM_TEMPLU`` or, on E.D.'s machine, the copy in ``_datasets``; skipped
  where there is none (the docstring examples are doctests:
  ``test_em_docstrings.py``);
* the types and slots pages are what the generators write today from the
  datamodels and the slot table (a datamodel changed → regenerate).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs-api"
TEMPLU = Path(os.environ.get("EM_TEMPLU") or Path.home() / "Documents/GitHub/_datasets/templu-mare-prove/TempluMare_geometry_declared_CLAUDE.em.json")
AUTHOR = "https://orcid.org/0000-0002-1825-0097"


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


@pytest.fixture
def templu(tmp_path):
    if not TEMPLU.exists():
        pytest.skip("no copy of Templu Mare here (set EM_TEMPLU)")
    copy = tmp_path / "templu-mare.em.json"
    shutil.copyfile(TEMPLU, copy)                  # the original is never written
    return copy


@pytest.mark.parametrize("name", ["quickstart_read", "quickstart_find", "quickstart_write"])
def test_quickstart_examples_run_on_templu_mare(templu, name):
    r = subprocess.run([sys.executable, "-m", "em", "run", str(DOCS / "examples" / f"{name}.py"),
                        "--file", str(templu), "--author", AUTHOR],
                       capture_output=True, text=True, env=_env(), cwd=str(ROOT))
    assert r.returncode == 0, r.stderr + r.stdout
    assert "SU002" in r.stdout or "units" in r.stdout


def test_notebook_example_saves_a_new_file(templu, tmp_path):
    out = tmp_path / "new.em.json"
    env = _env()
    env.update(EM_FILE=str(templu), EM_OUT=str(out))
    r = subprocess.run([sys.executable, str(DOCS / "examples" / "notebook.py")],
                       capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert out.exists() and "Foundation of the colonnade" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("tool,out", [("gen_types.py", "reference/types"), ("gen_slots.py", "reference/slots.rst")])
def test_generated_reference_is_current(tmp_path, tool, out):
    """Regenerating writes the same files that are committed."""
    target = DOCS / out
    before = {p.relative_to(DOCS): p.read_bytes() for p in ([target] if target.is_file() else target.rglob("*")) if p.is_file()}
    r = subprocess.run([sys.executable, str(DOCS / "_tools" / tool)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    after = {p.relative_to(DOCS): p.read_bytes() for p in ([target] if target.is_file() else target.rglob("*")) if p.is_file()}
    assert before == after, "regenerate: python docs-api/_tools/" + tool


def test_every_em_module_has_a_reference_page():
    pages = {p.stem for p in (DOCS / "reference" / "em").glob("*.rst")}
    mods = {p.stem for p in (ROOT / "src/s3dgraphy/em").glob("*.py")} - {"__init__", "__main__"}
    assert mods <= pages, mods - pages
