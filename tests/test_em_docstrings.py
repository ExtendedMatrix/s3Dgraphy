"""The reference of ``s3dgraphy.em`` is complete, and its examples run.

Two checks, so a Sphinx autodoc page of the scripting API has no holes:

* **every public name has a docstring** — in ``s3dgraphy.em`` and in its
  submodules ``graph``, ``write``, ``vocab``, ``stamps``, ``extensions``,
  ``plugins``, ``events``, ``errors``, ``messages``, ``host``. Public means
  ``__all__`` when the module has one, else every non-underscore name the
  module itself defines. For each function and class, its public methods and
  properties are checked too (and the nested ``em.app.space`` /
  ``em.app.commands`` classes). A dataclass's generated signature does not
  count as a docstring. ``em.graph`` is not checked: it is computed on access
  (PEP 562 ``__getattr__``) and documented in the module docstring.

* **every ``>>>`` example runs** — ``doctest`` over the same modules, each
  docstring as its own test, with ``ELLIPSIS`` on. Before each docstring the
  examples get a fresh session, as a script would have after::

      em.use(graph, author="0000-0002-1825-0097")

  on a «no application» host speaking English, where ``graph`` (id ``demo``)
  holds ``RM1`` (named ``RM head``), ``US1`` and ``US7``, the relation
  ``US1 is_after US7`` (id ``e1``), and on ``US1`` the property ``material``
  = ``"brick"``. The examples' globals are their module's, plus ``em`` (the
  :mod:`s3dgraphy.em` module). Listeners are cleared after each docstring.
  The machine's vocabularies, packages and plugins are the empty folders of
  ``tests/conftest.py``.
"""

import copy
import doctest
import importlib
import inspect

import pytest

from s3dgraphy import em
from s3dgraphy.em.host import ScriptHost
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

ORCID = "0000-0002-1825-0097"
SUBMODULES = ("graph", "write", "vocab", "catalogs", "stamps", "extensions", "plugins", "events", "errors",
              "messages", "host")
MODULES = ["s3dgraphy.em"] + [f"s3dgraphy.em.{m}" for m in SUBMODULES]
#: computed on access, documented in the module docstring
NOT_CHECKED = {("s3dgraphy.em", "graph")}


# ── (a) every public name has a docstring ───────────────────────────────────

def _ours(obj) -> bool:
    return str(getattr(obj, "__module__", "") or "").startswith("s3dgraphy.em")


def _has_doc(obj, owner=None) -> bool:
    doc = obj.__doc__ if not isinstance(obj, property) else obj.fget.__doc__
    if inspect.isclass(obj):
        doc = obj.__dict__.get("__doc__")
        # a dataclass with no docstring gets «Name(field: type, …)»
        if doc and doc.startswith(obj.__name__ + "("):
            doc = None
    return bool(doc and doc.strip())


def _public_names(module):
    names = getattr(module, "__all__", None)
    if names is None:
        names = [n for n, v in vars(module).items()
                 if not n.startswith("_") and (not hasattr(v, "__module__") or v.__module__ == module.__name__)]
    return list(names)


def _check_class(cls, where, missing, seen):
    if cls in seen:
        return
    seen.add(cls)
    if not _has_doc(cls):
        missing.append(where)
    for name, member in vars(cls).items():
        if name.startswith("_"):
            continue
        if isinstance(member, (staticmethod, classmethod)):
            member = member.__func__
        if isinstance(member, property) or inspect.isfunction(member):
            if not _has_doc(member):
                missing.append(f"{where}.{name}")
        elif inspect.isclass(member) and _ours(member):
            _check_class(member, f"{where}.{name}", missing, seen)


def _missing_docstrings():
    missing, seen = [], set()
    for mod_name in MODULES:
        module = importlib.import_module(mod_name)
        for name in _public_names(module):
            if (mod_name, name) in NOT_CHECKED:
                continue
            obj = getattr(module, name)
            where = f"{mod_name}.{name}"
            if inspect.ismodule(obj):
                continue
            if inspect.isclass(obj):
                if _ours(obj):
                    _check_class(obj, where, missing, seen)
            elif inspect.isfunction(obj):
                if _ours(obj) and not _has_doc(obj):
                    missing.append(where)
            elif _ours(type(obj)) and not isinstance(obj, (str, tuple, dict, list)):
                _check_class(type(obj), f"{where} ({type(obj).__name__})", missing, seen)
    # the application half's nested helpers: em.app.space, em.app.commands
    _check_class(em._App, "s3dgraphy.em._App", missing, seen)
    _check_class(em._App._Space, "s3dgraphy.em._App._Space", missing, seen)
    _check_class(em._App._Commands, "s3dgraphy.em._App._Commands", missing, seen)
    return missing


def test_every_public_name_has_a_docstring():
    missing = _missing_docstrings()
    assert not missing, f"{len(missing)} public names without a docstring:\n  " + "\n  ".join(missing)


def test_the_checker_sees_a_missing_docstring():
    class Bare:
        def method(self):
            pass

    Bare.__module__ = "s3dgraphy.em.fake"
    out = []
    _check_class(Bare, "Bare", out, set())
    assert out == ["Bare", "Bare.method"]


# ── (b) the examples run ────────────────────────────────────────────────────

def example_graph() -> Graph:
    """The graph the examples read (see the module docstring)."""
    g = Graph(graph_id="demo")
    g.add_node(RepresentationModelNode("RM1", name="RM head"))
    for n in ("US1", "US7"):
        g.add_node(StratigraphicUnit(n, n))
    g.add_edge("e1", "US1", "US7", "is_after")
    g.add_node(PropertyNode("P1", "material", value="brick", property_type="material"))
    g.add_edge("e2", "US1", "P1", "has_property")
    return g


def _doctests():
    finder = doctest.DocTestFinder(exclude_empty=True)
    tests = []
    for mod_name in MODULES:
        module = importlib.import_module(mod_name)
        for t in finder.find(module, mod_name):
            if t.examples:
                tests.append(t)
    return sorted(tests, key=lambda t: t.name)


DOCTESTS = _doctests()


def test_there_are_examples():
    names = {t.name for t in DOCTESTS}
    for wanted in ("s3dgraphy.em.use", "s3dgraphy.em.open", "s3dgraphy.em.save", "s3dgraphy.em.help",
                   "s3dgraphy.em.write.write", "s3dgraphy.em.graph.GraphView.node",
                   "s3dgraphy.em.graph.NodeView.prop", "s3dgraphy.em.vocab.Vocab.concept",
                   "s3dgraphy.em.stamps.stamp_artifact", "s3dgraphy.em.events.on",
                   "s3dgraphy.em._App._Commands.run", "s3dgraphy.em._App._Space.camera"):
        assert wanted in names, wanted


@pytest.fixture
def session():
    em.host.uninstall()
    em.events.clear()
    em.host.install(ScriptHost(language="en"))
    em.use(example_graph(), author=ORCID)
    yield
    em.host.uninstall()
    em.events.clear()


@pytest.mark.parametrize("test", DOCTESTS, ids=[t.name for t in DOCTESTS])
def test_docstring_examples(test, session):
    test = copy.copy(test)
    test.globs = dict(test.globs, em=em)          # a copy: the module's globals stay as they are
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    out = []
    runner.run(test, out=out.append)
    assert runner.failures == 0, "".join(out)
