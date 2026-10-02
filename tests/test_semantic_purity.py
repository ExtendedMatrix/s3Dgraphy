"""s3Dgraphy is the SEMANTIC library. This measures that it stayed one.

The pyproject calls it a "3D Stratigraphic Graph Management Library": Extended
Matrix, the property graph, the CIDOC mapping, the importers and exporters. A
concrete driver for a photogrammetric engine — REST endpoints, a task queue, an
archive — is none of those, and one lived here for a day (2026-08-29) before
moving to StratiGraph Server. The property is easy to lose again by accident, so
it is a test rather than a note in a report.

**What this does NOT forbid.** Optional backends that the library legitimately
speaks to are declared exceptions, by module: the MinIO resource backend and the
authority resolvers reach the network *by design*, behind a guard, and they are
the reason "no network anywhere" would be the wrong rule. The rule is narrower
and truer: the modules that carry MEANING must not.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "s3dgraphy"

#: Modules whose job IS to reach something. Each one is a deliberate exception
#: with a reason, and the list being short is the point.
NETWORK_ALLOWED = {
    "resources/minio_backend.py",   # the object store, optional and guarded
    "resources/resolver.py",        # resolves a locator, including remote ones
    "authorities",                  # an authority lives at a URL by definition
    "tools",                        # developer scripts, not the library surface
    "iiif.py",                      # builds URLs; reaching them is the caller's
    # A SPARQL endpoint is a graph, and reading one is import — the library's
    # own job. Declared here rather than excused: `RDFImporter.from_endpoint`
    # says in its own docstring that the HTTP conversation is a wired seam and
    # not a verified path.
    "importer/rdf_importer.py",
}

#: `urllib.parse` is deliberately NOT here: splitting a URL is string work, and a
#: rule that called it networking would be a rule people route around. What is
#: forbidden is OPENING one.
NETWORK_MODULES = {"requests", "httpx", "urllib.request", "urllib.error",
                   "urllib3", "socket", "http.client", "aiohttp", "websockets"}

#: Every engine this library must NOT know the name of. Adding one here when a
#: second driver appears costs nothing and keeps the line where it is.
ENGINE_NAMES = ("nodeodm", "opendronemap", "colmap", "micmac", "meshroom",
                "metashape", "agisoft")

#: Modules that read an engine's FILE FORMAT. Reading a format is import — the
#: library's own job, as the GraphML importer reads yEd's — and a reader of the
#: `.psx` cannot avoid the engine's name: it is the name the project gives
#: itself (`Info/OriginalSoftwareName`) and the prefix of every technique 3DSC
#: for Metashape writes. What stays forbidden to it is the rest: no network (the
#: test above does not excuse it), no driver, and no place in the
#: `photogrammetry` package, which must keep not knowing any engine.
FORMAT_READERS = {
    "importer/metashape_project.py":    # MICRO-IL-LETTORE-DI-METASHAPE, 02-10-2026
        "reads a .psx and the zips beside it; stdlib only, drives nothing",
}


def _modules():
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if "__pycache__" in rel:
            continue
        yield rel, path


def _allowed(rel: str) -> bool:
    return any(rel == a or rel.startswith(a + "/") for a in NETWORK_ALLOWED)


def test_the_semantic_modules_do_not_reach_the_network():
    offenders = []
    for rel, path in _modules():
        if _allowed(rel):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                      # not ours to judge here
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if name in NETWORK_MODULES or name.split(".")[0] in NETWORK_MODULES:
                    offenders.append(f"{rel}:{node.lineno} imports {name}")
    assert not offenders, (
        "the semantic library reached for the network:\n  "
        + "\n  ".join(offenders)
        + "\n\nA driver belongs in StratiGraph Server. If this import is "
          "legitimate, add its module to NETWORK_ALLOWED with the reason.")


def test_no_photogrammetric_ENGINE_is_named_in_the_library():
    """The names may appear in PROSE — a comment saying where the driver went is
    useful. What must not exist is code that knows one: an import, a call, a
    string value, an identifier.
    """
    offenders = []
    for rel, path in _modules():
        if rel in FORMAT_READERS:
            continue
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        if not any(engine in low for engine in ENGINE_NAMES):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        # strip every docstring and comment: what is left is code
        code_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                code_names.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                code_names.add(node.attr.lower())
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if not _is_docstring(tree, node):
                    code_names.add(node.value.lower())
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                code_names.add((getattr(node, "module", "") or "").lower())
                code_names.update(a.name.lower() for a in node.names)
        for engine in ENGINE_NAMES:
            hits = [n for n in code_names if engine in n]
            if hits:
                offenders.append(f"{rel}: {sorted(hits)[:3]}")
    assert not offenders, (
        "an engine is named in the library's CODE (prose is fine):\n  "
        + "\n  ".join(offenders))


def test_a_format_reader_stays_a_reader():
    """The exception is narrow: the reader is not in `photogrammetry/`, the
    meaning does not import it, and it imports nothing but the stdlib and the
    library."""
    for rel in FORMAT_READERS:
        assert not rel.startswith("photogrammetry/"), rel
        tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                assert name in STDLIB_FOR_READERS, f"{rel} imports {name}"
    for path in (SRC / "photogrammetry").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for rel in FORMAT_READERS:
            module = rel[:-3].replace("/", ".")
            assert module not in text, f"{path.name} reaches {module}"


#: what a format reader may import at the top level (the library's own modules
#: come in relative, `from ..`)
STDLIB_FOR_READERS = {"__future__", "argparse", "collections", "dataclasses",
                      "hashlib", "json", "os", "re", "typing", "uuid", "xml",
                      "zipfile"}


def _is_docstring(tree: ast.AST, const: ast.Constant) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and body[0].value is const):
                return True
    return False


def test_the_photogrammetry_package_is_semantics_only():
    """It exports a delta builder and the vocabulary — nothing that runs."""
    import s3dgraphy.photogrammetry as pg

    assert sorted(pg.__all__) == sorted([
        "build_photogrammetry_delta", "ProducedModel", "PhotogrammetryDelta",
        "MODES", "PROCESS_KIND", "MODEL_KIND",
        "EDGE_HAS_TRANSFORM", "EDGE_HAS_GCP_SET",
        "EDGE_HAD_INPUT", "EDGE_HAD_OUTPUT", "EDGE_DERIVED_FROM"])
    files = sorted(p.name for p in
                   (SRC / "photogrammetry").iterdir() if p.suffix == ".py")
    assert files == ["__init__.py", "delta.py"]


def test_the_api_surface_offers_the_meaning_and_not_a_runner():
    import s3dgraphy.api as em

    assert hasattr(em, "build_photogrammetry_delta")
    assert hasattr(em, "produced_model")
    assert hasattr(em, "gcp_set")
    assert hasattr(em, "registration_transform")
    # what a node does, not what the library means
    assert not hasattr(em, "run_photogrammetry")
    assert not hasattr(em, "photo_cluster")


def test_importing_the_surface_drags_in_no_web_framework_and_no_client():
    """The DoD the api suite already states, extended by one: the library must
    not pull an HTTP client in either.

    In a SUBPROCESS, and that is the whole difference between a measurement and a
    coincidence: `sys.modules` is shared across a pytest run, so another test that
    imported httpx first would make this pass while saying nothing. Measured, not
    assumed — this failed exactly that way before the subprocess.
    """
    import subprocess
    import sys

    probe = (
        "import s3dgraphy.api, sys;"
        "bad=[m for m in ('fastapi','uvicorn','starlette','requests','httpx')"
        " if m in sys.modules];"
        "print(','.join(bad))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=str(SRC.parent.parent))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", (
        f"importing s3dgraphy.api dragged in: {out.stdout.strip()}")
