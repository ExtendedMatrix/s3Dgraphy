"""``import em`` — as ``import bpy`` in Blender (MICRO-API01).

The three places ``em`` lives, each with the short name:

* **a script / a notebook** (no application): ``import em`` is
  :mod:`s3dgraphy.em` itself — one module, one host — and ``python -m em``
  is ``python -m s3dgraphy.em``;
* **EMStudio** (console and plugins) and **EM Tools** (Blender): the
  application installs its host into ``s3dgraphy.em.host``; a plugin or a
  console line that writes ``import em`` must see THAT host, not a second
  copy of the module. Simulated here with a host installed before and after
  the import (the bridge and EM Tools do the same call).
* the distribution ships the top-level ``em`` package next to ``s3dgraphy``.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _py(code: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args] if not code else [sys.executable, "-c", code],
                          capture_output=True, text=True, env=_env(), cwd=str(ROOT))


def test_import_em_is_s3dgraphy_em():
    r = _py("import em, s3dgraphy.em as full; from s3dgraphy import em as other\n"
            "assert em is full is other, (em, full)\n"
            "import sys; assert not [m for m in sys.modules if m.startswith('em.')], 'a second copy'\n"
            "print(em.API_VERSION, em.app.available)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split()[1] == "False"            # no application: em.app says so


def test_script_opens_a_file_with_import_em(tmp_path):
    out = tmp_path / "demo.em.json"
    code = (
        "import em\n"
        "from s3dgraphy.graph import Graph\n"
        "from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit\n"
        "g = Graph('demo'); g.add_node(StratigraphicUnit('u1', 'US1', 'a layer'))\n"
        "em.use(g, author='https://orcid.org/0000-0002-1825-0097')\n"
        "with em.write('Describe US1') as tx:\n"
        "    tx.update('US1', 'description', 'a burnt layer')\n"
        f"em.save({str(out)!r})\n"
        f"em.open({str(out)!r})\n"
        "print(em.graph.node('US1').description)\n")
    r = _py(code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("a burnt layer")


def test_python_dash_m_em_runs_a_script(tmp_path):
    script = tmp_path / "s.py"
    script.write_text("import em, sys\nprint(em.help.__module__)\n"
                      "assert not [m for m in sys.modules if m.startswith('em.')]\n")
    r = _py("", "-m", "em", "run", str(script))
    assert r.returncode == 0, r.stderr + r.stdout
    assert "s3dgraphy.em" in r.stdout
    r = _py("", "-m", "em", "help")
    assert r.returncode == 0 and "em " in r.stdout


def test_an_application_host_is_seen_by_import_em():
    """EMStudio's bridge and EM Tools install a host; ``import em`` in the
    console, a plugin or a Blender script sees it (before or after import)."""
    code = (
        "from s3dgraphy import em as lib\n"
        "from s3dgraphy.em import host\n"
        "from s3dgraphy.graph import Graph\n"
        "class App(host.NoApp):\n"
        "    def selection(self): return ['u1']\n"
        "class Blender(host.ScriptHost):\n"
        "    name = 'blender'\n"
        "    def __init__(self, g):\n"
        "        super().__init__(g, author='https://orcid.org/0000-0002-1825-0097'); self.app = App('blender')\n"
        "host.install(Blender(Graph('from-the-app')))\n"
        "import em\n"
        "assert em is lib\n"
        "assert em.graph.id == 'from-the-app', em.graph.id\n"
        "assert em.app.available and em.app.selection() == ['u1']\n"
        "print(repr(em.app))\n")
    r = _py(code)
    assert r.returncode == 0, r.stderr
    assert "blender" in r.stdout


def test_the_distribution_ships_em():
    from setuptools import find_packages
    pkgs = find_packages(where=str(SRC))
    assert "em" in pkgs and "s3dgraphy.em" in pkgs
    init = (SRC / "em" / "__init__.py").read_text(encoding="utf-8")
    assert "sys.modules[__name__]" in init.replace("_sys.", "sys.")
