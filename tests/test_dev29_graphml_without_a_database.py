"""dev29 · A5 — a .graphml imports without SQLAlchemy.

Measured with a plain ``pip install s3dgraphy`` (1 Oct 2026): ``import_graphml``
reached ``s3dgraphy.sync.rapporti``, and ``sync/__init__`` requires SQLAlchemy
(the ``[sync]`` extra). The parser of the rapporti has no database in it: it
lives in ``s3dgraphy.rapporti`` now, and ``s3dgraphy.sync.rapporti`` re-exports
it. Measured again in a venv without SQLAlchemy: San Pietro converts to 66
nodes and 142 edges. Here SQLAlchemy is made unimportable in a subprocess.
"""

import os
import subprocess
import sys
import textwrap

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
SAN_PIETRO = os.path.expanduser(
    "~/Documents/GitHub/_datasets/SegniSanPietro/caso-di-studio-EM/EM/SanPietro_EM.graphml")
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

SCRIPT = textwrap.dedent("""
    import sys
    class _NoDatabase:
        def find_spec(self, name, path=None, target=None):
            if name == "sqlalchemy" or name.startswith("sqlalchemy."):
                raise ModuleNotFoundError("No module named 'sqlalchemy'")
            return None
    sys.meta_path.insert(0, _NoDatabase())
    sys.path.insert(0, sys.argv[1])
    from s3dgraphy import api
    doc, report = api.convert_graphml_to_emjson(open(sys.argv[2], "rb").read())
    g = doc["graph"]
    print(len(g["nodes"]), len(g["edges"]), "sqlalchemy" in sys.modules)
""")


def _graphml():
    if os.path.isfile(SAN_PIETRO):
        return SAN_PIETRO, (66, 142)
    for root, _dirs, files in os.walk(FIXTURE):
        for name in files:
            if name.endswith(".graphml"):
                return os.path.join(root, name), None
    return None, None


def test_graphml_converts_without_sqlalchemy():
    path, expected = _graphml()
    assert path, "no .graphml to read"
    out = subprocess.run([sys.executable, "-c", SCRIPT, SRC, path],
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    nodes, edges, loaded = out.stdout.strip().splitlines()[-1].split()
    assert loaded == "False"
    if expected:
        assert (int(nodes), int(edges)) == expected


def test_the_old_name_still_answers():
    from s3dgraphy import rapporti
    from s3dgraphy.sync import rapporti as old
    assert old.parse_rapporti is rapporti.parse_rapporti
    assert old._US_PREFIX_PATTERN is rapporti._US_PREFIX_PATTERN
