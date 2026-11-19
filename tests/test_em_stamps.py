"""MICRO-GEO02 part 0 · the stamp on a derived artifact (G-5 of the geophysics decisions).

What is defended:

* ``em.stamp(path, inputs=…)`` writes ``<path>.stamp.json`` that ``dtcstamp``
  reads back: the output by digest (``digest_covers = artifact``, size, media
  type), the inputs by identity only (a path hashed, never written; a graph's
  resource cited with its own id; an acquisition with ``kind``), the process
  (``dtc_kind``, technique, parameters) and the software;
* the same bytes get the same ``res:`` identity, and two stamps of them differ
  only in the instant (the format's «same fact, twice»);
* ``ctx.stamp`` in a loaded plugin names the plugin (id and version) as the
  first software line and no operator (the format: the agent is the software);
  ``em.stamp`` inside a command finds the calling plugin by itself;
* the validator's advice: code that writes files and stamps none hears a
  WARNING (never an error), in EN and IT; code that stamps, or writes nothing,
  hears nothing.
"""
import textwrap

import dtcstamp
import pytest

from s3dgraphy import em
from s3dgraphy import extensions as X
from s3dgraphy.em import plugins as PL
from s3dgraphy.em import stamps as ST
from s3dgraphy.profiles.problems import MESSAGES

from tests.test_em_plugins import ORCID, _fresh, host, install, write_plugin  # noqa: F401 — the fixture too


def _files(tmp_path):
    src = tmp_path / "slice_0.10-0.20m.csv"
    src.write_text("x,y,v\n0,0,1\n", encoding="utf-8")
    png = tmp_path / "slice.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
    return src, png


def test_em_stamp_writes_a_stamp_dtcstamp_reads(tmp_path):
    src, png = _files(tmp_path)
    stamp = em.stamp(png, agent={"id": "geofisica", "name": "Geophysics", "version": "0.1.0"},
                     inputs=[src, {"resource_id": "acq:ilici-s1", "kind": "acquisition"}],
                     parameters={"colormap": "viridis", "clip": [2, 98]},
                     dtc_kind="format_conversion", technique="slice rasterization", label="Slice 0.10–0.20 m")
    path = ST.stamp_path(png)
    assert path.name == "slice.png.stamp.json" and path.is_file()
    back = dtcstamp.read_stamp(str(path))
    assert back == stamp
    me = back["self"]
    assert me["digest"] == dtcstamp.file_digest(str(png)) and me["digest_covers"] == "artifact"
    assert me["measures"]["size_bytes"] == png.stat().st_size and me["media_type"] == "image/png"
    assert me["resource_id"] == ST.resource_id_for(me["digest"]) and me["label"] == "Slice 0.10–0.20 m"
    assert dtcstamp.stamp_identity(back)["strength"] == "verifiable"
    first, acq = back["from"]
    assert first["digest"] == dtcstamp.file_digest(str(src)) and first["label"] == src.name
    assert str(tmp_path) not in path.read_text(encoding="utf-8")   # never a path
    assert acq == {"resource_id": "acq:ilici-s1", "kind": "acquisition"}
    how = back["how"]
    assert how["dtc_kind"] == "format_conversion" and how["parameters"]["colormap"] == "viridis"
    assert how["software"][0] == {"id": "geofisica", "name": "Geophysics", "version": "0.1.0"}
    assert how["software"][-1]["name"] == "s3dgraphy"
    assert "operator" not in back["by"] and back["by"]["at"].endswith("Z")
    assert dtcstamp.declared_origin(back) is False


def test_same_bytes_same_identity_only_the_instant_differs(tmp_path):
    src, png = _files(tmp_path)
    a = ST.make_stamp(png, inputs=[src], at="2026-11-19T08:00:00Z")
    b = ST.make_stamp(png, inputs=[src], at="2026-11-19T09:00:00Z")
    assert a["self"]["resource_id"] == b["self"]["resource_id"]
    assert dtcstamp.stamps_agree(a, b)


def test_refusals(tmp_path):
    src, png = _files(tmp_path)
    with pytest.raises(ST.StampError):
        em.stamp(tmp_path / "missing.png")
    with pytest.raises(ST.StampError):
        em.stamp(png, inputs=[tmp_path / "missing.csv"])
    with pytest.raises(ST.StampError):
        em.stamp(png, inputs=[{"label": "names nothing"}])
    assert not ST.stamp_path(png).exists()
    s = em.stamp(png, write=False)
    assert s["from"] == [] and not ST.stamp_path(png).exists()


STAMPING = '''
  [[code.commands]]
  id = "bake"
  label = { it = "Cuoci", en = "Bake" }
  writes = false
  slots = [{ name = "path", kind = "path" }]
  in = ["menu.tools@1"]
  [[code.commands]]
  id = "bake2"
  label = { it = "Cuoci 2", en = "Bake 2" }
  writes = false
  slots = [{ name = "path", kind = "path" }]
  in = ["menu.tools@1"]
'''

STAMPING_MODULE = '''
from pathlib import Path
from s3dgraphy import em

CTX = {}


def bake(slots):
    out = Path(slots["path"]).with_suffix(".png")
    out.write_bytes(b"png of " + Path(slots["path"]).read_bytes())
    return CTX["ctx"].stamp(out, inputs=[slots["path"]], dtc_kind="format_conversion")["self"]["resource_id"]


def bake2(slots):
    out = Path(slots["path"]).with_suffix(".bin")
    out.write_bytes(b"bin")
    return em.stamp(out, inputs=[slots["path"]])["how"]["software"][0]


def setup(ctx):
    CTX["ctx"] = ctx
    ctx.command("bake", bake)
    ctx.command("bake2", bake2)


plugin = type("Plugin", (), {"setup": staticmethod(setup)})
'''


def test_ctx_stamp_names_the_plugin(tmp_path):
    folder = write_plugin(tmp_path, commands=STAMPING, body=STAMPING_MODULE, version="0.3.1", api="1.2")
    pid = install(folder)["id"]
    [p] = PL.sync("emstudio")
    assert p.state == "loaded", p.problems
    host()
    src = tmp_path / "data.asc"
    src.write_text("1 2 3\n", encoding="utf-8")
    r = PL.invoke(pid, "bake", {"path": str(src)})
    assert r.ok, r.message
    stamp = dtcstamp.read_stamp(str(tmp_path / "data.png.stamp.json"))
    assert stamp["self"]["resource_id"] == r.data["value"]
    assert stamp["how"]["software"][0] == {"name": p.name, "id": pid, "version": "0.3.1"}
    r = PL.invoke(pid, "bake2", {"path": str(src)})
    assert r.ok and r.data["value"]["id"] == pid                       # em.stamp found the calling plugin


def test_the_validator_advises_and_never_refuses(tmp_path):
    writes = write_plugin(tmp_path, body=textwrap.dedent('''
        def go(slots):
            open(slots["path"] + ".out", "wb").write(b"x")
        plugin = type("Plugin", (), {"setup": staticmethod(lambda ctx: None)})
        '''))
    rep = X.validate_archive(writes)
    assert rep.ok and "code_stamp_advice" in rep.codes("warning")
    [w] = [p for p in rep.warnings if p.code == "code_stamp_advice"]
    assert "consiglio" in w.text("it") and "advice" in w.text("en")
    stamps = write_plugin(tmp_path, body=STAMPING_MODULE)
    assert "code_stamp_advice" not in X.validate_archive(stamps).codes()
    reads = write_plugin(tmp_path)                                     # the tests' plugin only reads files
    assert "code_stamp_advice" not in X.validate_archive(reads).codes()
    en, it = MESSAGES["code_stamp_advice"]
    assert "{files}" in en and "{files}" in it
