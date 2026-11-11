"""The core of s3Dgraphy imports no numpy (MICRO-FIT-AFFINE-SENZA-NUMPY,
11 Nov 2026).

``geometry.frame._fit_affine`` was the one numpy of the core
(``np.linalg.lstsq``): the frozen bridge — built with ``--exclude-module
numpy`` — and whoever uses s3Dgraphy without numpy fell on
``/geo/tileset-frame``. It is now pure Python (ported from EMStudio's
``em_gis.fit_affine``). Defended here:

* the same numbers as ``numpy.linalg.lstsq(rcond=None)`` on random cases and on
  degenerate ones (a flat volume, aligned points, one point): skipped without
  numpy;
* the guard: no module of the core imports numpy, at import time (the package
  walked in a subprocess with ``sys.modules['numpy'] = None``) or inside a
  function (the sources read).

pandas is still an optional dependency that some importers load at the top:
those modules are named below and fail on pandas, never on numpy itself.
Taking pandas out of the core is a later round.
"""
import ast
import json
import pathlib
import random
import subprocess
import sys

import pytest

from s3dgraphy.geometry.frame import _fit_affine

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
PKG = SRC / "s3dgraphy"

#: the modules that import pandas at the top (pandas needs numpy): a later round
PANDAS_AT_THE_TOP = {
    "s3dgraphy.importer.mapped_xlsx_importer",
    "s3dgraphy.importer.qualia_importer",
    "s3dgraphy.importer.unified_xlsx_importer",
}


def _numpy_fit(src, dst):
    """The old ``_fit_affine``, verbatim: the reference."""
    import numpy as np
    S = np.asarray(src, dtype=float)
    D = np.asarray(dst, dtype=float)
    cs, cd = S.mean(axis=0), D.mean(axis=0)
    A, *_ = np.linalg.lstsq(S - cs, D - cd, rcond=None)
    L = A.T
    t = cd - L @ cs
    return [[float(L[r][0]), float(L[r][1]), float(L[r][2]), float(t[r])] for r in range(3)]


def _gap(a, b):
    """The largest difference: absolute on the 3×3, relative to the size on
    the translation (ECEF millions carry 1e-9 m only as their last digits)."""
    worst = 0.0
    for ra, rb in zip(a, b):
        for k in range(3):
            worst = max(worst, abs(ra[k] - rb[k]))
        worst = max(worst, abs(ra[3] - rb[3]) / max(1.0, abs(rb[3])))
    return worst


def _cases():
    rnd = random.Random(20261111)
    out = []
    for i in range(40):                                         # random, full rank
        n = rnd.randint(4, 64)
        off = [rnd.uniform(-7e6, 7e6) for _ in range(3)] if i % 2 else [0.0, 0.0, 0.0]
        L = [[rnd.uniform(-2, 2) for _ in range(3)] for _ in range(3)]
        t = [rnd.uniform(-7e6, 7e6) for _ in range(3)]
        src = [[off[k] + rnd.uniform(-50, 50) for k in range(3)] for _ in range(n)]
        dst = [[sum(L[r][k] * p[k] for k in range(3)) + t[r] + rnd.gauss(0, 0.01) for r in range(3)]
               for p in src]
        out.append((f"random-{i}", src, dst))
    # a flat volume (z = const): coplanar, rank 2
    src = [[3 + 40 * u, -4 + 25 * v, 1.0] for u in (-1, 0, 1) for v in (-1, 0, 1) for _ in (0, 1, 2)]
    dst = [[0.3 * p[0] - 0.9 * p[1] + 4127760.9, 0.9 * p[0] + 0.3 * p[1] + 1734113.5, p[2] + 4528084.8]
           for p in src]
    out.append(("flat", src, dst))
    # a tilted plane
    src = [[u, v, 0.5 * u - 0.25 * v + 10] for u in range(-3, 4) for v in range(-2, 3)]
    dst = [[2 * p[0] + 1, p[1] - p[2], 3 * p[2]] for p in src]
    out.append(("tilted-plane", src, dst))
    # aligned points: rank 1
    src = [[1 + 2 * s, 5 - s, 0.5 * s] for s in range(-5, 6)]
    dst = [[p[0] + 6378137.0, 2 * p[1], -p[2]] for p in src]
    out.append(("aligned", src, dst))
    # one point, and the same point repeated: rank 0, the translation alone
    out.append(("one-point", [[10.0, 20.0, 30.0]], [[6378137.0, 1.0, 2.0]]))
    out.append(("same-point", [[10.0, 20.0, 30.0]] * 5, [[6378137.0, 1.0, 2.0]] * 5))
    # a box of the size of the Basilica Iulia's, in ECEF
    src = [[x, y, z] for x in (-94, 0, 94) for y in (-49, 0, 49) for z in (-12, 0, 12)]
    dst = [[-0.18 * p[0] + 0.98 * p[1] + 6271099.97, 0.98 * p[0] + 0.18 * p[1] + 1163587.24, p[2] + 12.3]
           for p in src]
    out.append(("basilica-box", src, dst))
    return out


@pytest.mark.parametrize("name,src,dst", _cases(), ids=[c[0] for c in _cases()])
def test_the_fit_gives_numpys_numbers(name, src, dst):
    pytest.importorskip("numpy")
    mine, ref = _fit_affine(src, dst), _numpy_fit(src, dst)
    assert _gap(mine, ref) < 1e-9, (name, mine, ref)


def test_the_fit_refuses_what_it_cannot_fit():
    with pytest.raises(ValueError):
        _fit_affine([], [])
    with pytest.raises(ValueError):
        _fit_affine([[0, 0, 0], [1, 1, 1]], [[0, 0, 0]])


def test_the_fit_recovers_an_exact_affine_without_numpy():
    src = [[x, y, z] for x in (-1, 1) for y in (-2, 2) for z in (-3, 3)]
    dst = [[2 * p[0] - p[1] + 5, p[1] + 0.5 * p[2] - 7, -p[0] + 3 * p[2] + 6378137.0] for p in src]
    want = [[2, -1, 0, 5], [0, 1, 0.5, -7], [-1, 0, 3, 6378137.0]]
    got = _fit_affine(src, dst)
    assert _gap(got, want) < 1e-12


_WALK = """
import importlib, json, pkgutil, sys, traceback
sys.modules["numpy"] = None
sys.path.insert(0, %r)
import s3dgraphy
failed = {}
for m in pkgutil.walk_packages(s3dgraphy.__path__, "s3dgraphy."):
    try:
        importlib.import_module(m.name)
    except BaseException as exc:
        failed[m.name] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
print(json.dumps(failed))
"""


def test_no_module_of_the_core_imports_numpy_at_import_time():
    run = subprocess.run([sys.executable, "-c", _WALK % str(SRC)], capture_output=True, text=True,
                         timeout=600)
    assert run.returncode == 0, run.stderr
    failed = json.loads(run.stdout.strip().splitlines()[-1])
    strangers = {m: tb for m, tb in failed.items() if m not in PANDAS_AT_THE_TOP}
    assert not strangers, "modules of the core that need numpy:\n" + "\n".join(
        f"{m}\n{tb}" for m, tb in strangers.items())
    for m, tb in failed.items():              # the known ones fail on pandas, not on numpy
        assert "pandas" in tb, (m, tb)


def test_no_module_of_the_core_imports_numpy_inside_a_function():
    found = []
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            if any(n == "numpy" or n.startswith("numpy.") for n in names):
                found.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not found, "numpy imported in the core: " + ", ".join(found)
