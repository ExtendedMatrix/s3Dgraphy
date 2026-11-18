"""MICRO-PL03 · s3dgraphy.profiles — the library of the community packages (row W1).

The packages under tests/data/profiles are SYNTHETIC (D-5): «esempio-statuaria»
in its two forms — separate (data, then the plugin facemesh_fit) and mixed —
generated for these tests and marked ESEMPIO everywhere. The 0.1 profile of
the vocabularies repository (example-toolmarks) is read when the repository
is beside this one.
"""
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from s3dgraphy import profiles as P
from s3dgraphy.profiles import semver
from s3dgraphy.profiles.problems import MESSAGES, Problem

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN, MIXED = DATA / "esempio-statuaria", DATA / "facemesh_fit", DATA / "esempio-statuaria-misto"
TOOLMARKS = Path(__file__).resolve().parents[2] / "vocabularies" / "profiles" / "example-toolmarks"
IRI = "https://w3id.org/extendedmatrix/profile/esempio-statuaria"


def copy(src: Path, tmp_path: Path, name=None) -> Path:
    dst = tmp_path / (name or src.name)
    shutil.copytree(src, dst)
    return dst


def edit_json(path: Path, fn):
    doc = json.loads(path.read_text(encoding="utf-8"))
    fn(doc)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def codes(target, level=None):
    return P.validate(target).codes(level)


def zip_of(folder: Path, tmp_path: Path, top=False) -> Path:
    out = tmp_path / (folder.name + ".zip")
    with zipfile.ZipFile(out, "w") as z:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                rel = f.relative_to(folder).as_posix()
                z.write(f, f"{folder.name}/{rel}" if top else rel)
    return out


# ── schemas, messages, versions ─────────────────────────────────────────────

def test_both_schemas_are_valid_schemas():
    jsonschema = pytest.importorskip("jsonschema")
    for fmt in P.FORMATS:
        jsonschema.Draft202012Validator.check_schema(P.schema_for(fmt))


def test_every_message_speaks_english_and_italian():
    for code, (en, it) in MESSAGES.items():
        assert en and it, code
    p = Problem("label_language", "error", "profile.json", {"where": "qualia stat:x", "lang": "en"})
    assert "no label in 'en'" in p.text("en") and "manca l'etichetta in 'en'" in p.text("it")
    assert p.as_dict()["it"] != p.as_dict()["en"]


@pytest.mark.parametrize("version,spec,ok", [
    ("1.0.3", "^1.0", True), ("2.0.0", "^1.0", False), ("0.1.9", "^0.1", True), ("0.2.0", "^0.1", False),
    ("1.6.2", ">=1.6,<1.7", True), ("1.7.0", ">=1.6,<1.7", False), ("1.6.0-dev.3", ">=1.6", False),
    ("0.3.4", "~0.3", True), ("0.4.0", "~0.3", False), ("1.2.3", "1.2.3", True), ("1.2.4", "*", True),
])
def test_semver_ranges(version, spec, ok):
    assert semver.satisfies(version, spec) is ok
    assert semver.valid_range(spec)


# ── validation: the packages as they should be ──────────────────────────────

@pytest.mark.parametrize("folder,kind", [(SEPARATE, "community-package"), (PLUGIN, "plugin"), (MIXED, "mixed")])
def test_the_synthetic_packages_validate(folder, kind):
    r = P.validate(folder)
    assert r.ok, [str(p) for p in r.errors]
    assert P.open_package(folder).kind == kind


def test_a_zip_with_or_without_its_top_folder_validates(tmp_path):
    assert P.validate(zip_of(MIXED, tmp_path)).ok
    (tmp_path / "t").mkdir()
    assert P.validate(zip_of(SEPARATE, tmp_path / "t", top=True)).ok


@pytest.mark.skipif(not TOOLMARKS.exists(), reason="the vocabularies repository is not beside this one")
def test_the_01_profile_of_vocabularies_validates_and_its_node_types_are_said_suspended(tmp_path):
    r = P.validate(TOOLMARKS)
    assert r.ok, [str(p) for p in r.errors]
    assert set(r.codes("warning")) == {"node_types_suspended"}
    stable = copy(TOOLMARKS, tmp_path)
    edit_json(stable / "profile.json", lambda m: m.update(lifecycle="stable"))
    assert "node_types_suspended" in codes(stable, "error")


def test_validation_writes_nothing(tmp_path, monkeypatch):
    from s3dgraphy.authorities.packages import vocab_dir
    assert P.validate(MIXED).ok
    assert not any(vocab_dir().glob("*/*/manifest.json"))
    assert not P.profiles_dir().exists() or not any(P.profiles_dir().iterdir())


# ── validation: what it refuses, and what it only says ─────────────────────

def _break(tmp_path, fn, folder=SEPARATE, file="profile.json"):
    pkg = copy(folder, tmp_path)
    edit_json(pkg / file, fn)
    return pkg


@pytest.mark.parametrize("fn,code", [
    (lambda m: m["qualia"].append({"id": "lab:x", "label": {"it": "x", "en": "x"}, "data_type": "float"}), "prefix_missing"),
    (lambda m: m["qualia"].append({"id": "height", "label": {"it": "x", "en": "x"}, "data_type": "float"}), "core_redefined"),
    (lambda m: m["extractor_types"][0]["geometry"].update(produces="area"), "geometry_produces"),
    (lambda m: m["combiner_types"][0]["inputs"].pop(), "combiner_arity"),
    (lambda m: m["combiner_types"][0]["inputs"].__setitem__(0, {"landmark": "stat:volto/menton"}), "landmark_unknown"),
    (lambda m: m["combiner_types"][2]["inputs"].__setitem__(0, {"landmark": "stat:volto/nasion"}), "combiner_inputs"),
    (lambda m: m["forms"][0].update(digest="sha256:" + "0" * 64), "form_digest"),
    (lambda m: m["qualia"][0]["label"].pop("en"), "label_language"),
    (lambda m: m["file_types"][0].update(reader="plugin:org.example.rti-viewer"), "reader_plugin"),
    (lambda m: m["extractor_types"][0]["source_documents"].append("stat:nessuno"), "unknown_node_type"),
    (lambda m: m["extractor_types"][1]["produces"].append("stat:nessuno"), "unknown_quale"),
    (lambda m: m["qualia_vocabularies"].append({"property_type": "stat:nuova", "label": {"it": "n", "en": "n"},
                                                "scheme": "https://example.org/v/", "version": "1.0.0"}), "vocab_not_carried"),
    (lambda m: m["qualia_vocabularies"][0].update(version="0.2.0"), "vocab_version_mismatch"),
    (lambda m: m.update(version="1.0"), "schema"),
    (lambda m: m.update(examples=[]), "no_example"),
    (lambda m: m.update(name="altro-nome"), "env_profile_id"),
])
def test_what_the_validator_refuses(tmp_path, fn, code):
    r = P.validate(_break(tmp_path, fn))
    assert code in r.codes("error"), [str(p) for p in r.problems]
    assert all(p.text("it") for p in r.problems)


def test_a_landmark_set_file_is_checked(tmp_path):
    pkg = _break(tmp_path, lambda d: d["points"][2].update(mirror="exocanthion_x"), file="landmarks/volto.json")
    assert "landmark_mirror" in codes(pkg, "error")
    pkg = _break(tmp_path / "b", lambda d: d["points"].append(dict(d["points"][0])), file="landmarks/volto.json")
    assert "landmark_file" in codes(pkg, "error")


def test_the_checked_datamodel_is_said_never_refused(tmp_path):
    r = P.validate(_break(tmp_path, lambda m: m.update(datamodel_checked={"nodes": "1.6.1"})))
    assert r.ok and "datamodel_checked" in r.codes("warning")
    assert "verificato contro nodes 1.6.1" in next(p for p in r.warnings if p.code == "datamodel_checked").text("it")


def test_the_envelope_partition_and_requires(tmp_path):
    pkg = copy(MIXED, tmp_path)
    (pkg / "data" / "colors" / "trucco.py").write_text("print('no')\n")
    (pkg / "notes.txt").write_text("fuori\n")
    toml = (pkg / "em-extension.toml").read_text()
    (pkg / "em-extension.toml").write_text(toml.replace('type = "mixed"', 'type = "plugin"'))
    c = codes(pkg, "error")
    assert {"partition_code_in_data", "partition_outside", "env_type"} <= set(c)
    sep = copy(SEPARATE, tmp_path / "s")
    t = (sep / "em-extension.toml").read_text()
    (sep / "em-extension.toml").write_text(t.replace("optional = true", "optional = false"))
    assert "requires_code_optional" in codes(sep, "error")


def test_a_carried_vocabulary_is_checked_inside_its_file(tmp_path):
    pkg = copy(SEPARATE, tmp_path)
    ttl = pkg / "vocab" / "lavorazione.ttl"
    ttl.write_text(ttl.read_text().replace("subbia", "subbia piatta"))
    assert "data_vocabulary" in codes(pkg, "error")      # the digest no longer matches


def test_a_permission_carries_its_short_reason(tmp_path):
    pkg = copy(PLUGIN, tmp_path)
    t = (pkg / "em-extension.toml").read_text()
    (pkg / "em-extension.toml").write_text(t.replace('riconoscere il volto"', 'riconoscere il volto."')
                                           .replace("[code.permissions]", "[code.permissions]\n  camera = \"x\""))
    assert {"permission_reason", "permission_unknown"} <= set(codes(pkg, "error"))


# ── the machine folder ──────────────────────────────────────────────────────

def test_install_the_data_package_and_its_vocabularies():
    from s3dgraphy.vocabularies import vocab_installed
    out = P.install(SEPARATE)
    assert out["status"] == "installed" and out["kind"] == "community-package"
    dest = Path(out["path"])
    assert dest == P.profiles_dir() / "esempio-statuaria" / "0.1.0"
    assert (dest / "profile.json").is_file() and (dest / "landmarks" / "volto.json").is_file()
    assert not (dest / "vocab").exists(), "the carried .ttl went to the vocabulary manager"
    assert not (dest / "em-extension.toml").exists()
    vocs = {v["scheme"]: v for v in vocab_installed() if v.get("scheme", "").startswith(IRI)}
    assert len(vocs) == 3
    assert all("extension:esempio-statuaria" in v["carriers"] for v in vocs.values())
    idx = json.loads((P.profiles_dir() / P.INDEX_FILE).read_text())
    row = idx["profiles"][0]
    assert row["iri"] == IRI and row["prefix"] == "stat" and "stat:volto" in row["types"]["landmark_set"]
    assert P.install(SEPARATE)["status"] == "unchanged"


def test_a_version_is_not_reused_and_nothing_is_written_on_an_error(tmp_path):
    P.install(SEPARATE)
    other = copy(SEPARATE, tmp_path)
    (other / "help" / "it" / "index.md").write_text("altro\n")
    with pytest.raises(P.ProfileError, match="already installed with other content"):
        P.install(other)
    bad = _break(tmp_path / "b", lambda m: m.update(prefix="X"))
    with pytest.raises(P.ProfileError) as e:
        P.install(bad)
    assert e.value.report.errors
    assert [r["version"] for r in P.installed()] == ["0.1.0"]


def test_install_the_mixed_package_records_the_code_as_not_installed(tmp_path):
    out = P.install(zip_of(MIXED, tmp_path))
    assert out["kind"] == "mixed" and out["code"]["status"] == "not_installed"
    dest = Path(out["path"])
    assert not (dest / "code").exists() and not list(dest.rglob("*.py"))
    assert P.installed()[0]["code"]["version"] == "0.1.0"
    with pytest.raises(P.ProfileError, match="plugin"):
        P.install(PLUGIN)


def test_versions_side_by_side_find_and_remove(tmp_path):
    P.install(SEPARATE)
    newer = copy(SEPARATE, tmp_path)
    edit_json(newer / "profile.json", lambda m: m.update(version="0.1.1"))
    edit_json(newer / "examples" / "testa-esempio.em.json",
              lambda d: d["header"].update(profiles=[{"iri": IRI, "version": "0.1.1"}]))
    t = (newer / "em-extension.toml").read_text()
    (newer / "em-extension.toml").write_text(t.replace('version = "0.1.0"\nname', 'version = "0.1.1"\nname', 1))
    P.install(newer)
    assert [r["version"] for r in P.installed(all_versions=False)] == ["0.1.1"]
    assert P.installed(all_versions=False)[0]["versions"] == ["0.1.1", "0.1.0"]
    assert P.find(IRI, "0.1.0").version == "0.1.0"
    assert P.find(IRI, "0.1.5").version == "0.1.1"          # compatible (0.1.x): read in its place
    assert P.find(IRI, "0.1.5", exact=True) is None
    assert P.find("esempio-statuaria").version == "0.1.1"
    assert P.find(IRI, "1.0.0") is None
    assert P.remove("esempio-statuaria", "0.1.0") == ["0.1.0"]
    assert [r["version"] for r in P.installed()] == ["0.1.1"]


# ── the overlay ─────────────────────────────────────────────────────────────

def test_the_merged_views_keep_the_core_and_add_the_package():
    P.install(SEPARATE)
    ov = P.overlay([{"iri": IRI, "version": "0.1.0"}])
    q = ov.qualia_types()
    assert q["height"]["origin"] == "core"
    assert q["stat:larghezza_biorbitale"]["origin"] == "esempio-statuaria@0.1.0"
    assert q["stat:lavorazione"]["data_type"] == "controlled_vocabulary"
    assert q["stat:lavorazione"]["vocabulary_source"] == IRI + "/vocab/lavorazione/"
    ex = ov.extractor_types()
    assert "3d_model_analysis" in ex and ex["stat:punto_canonico"]["geometry"]["primitive"] == "point"
    assert set(ov.combiner_types()) == {"stat:c_larghezza_biorbitale", "stat:c_altezza_facciale", "stat:c_indice_facciale"}
    assert "3d_model" in ov.document_types() and "stat:rilievo_rti" in ov.document_types()
    pts = [p["id"] for p in ov.landmark_set("stat:volto")["set"]["points"]]
    assert pts[:2] == ["glabella", "nasion"] and len(pts) == 6
    assert ov.label("stat:punto_canonico", "it") == "Punto canonico"
    assert ov.label("stat:punto_canonico", "en") == "Canonical point"
    assert ov.strings("it")["stat.posa.prossimo"].startswith("Posa il punto")
    assert Path(ov.forms()["stat-scheda-superficie"]["compiled_path"]).is_file()
    assert Path(ov.color_schemes()["stat:fasi"]["file"]).is_file()
    json.dumps(ov.as_dict("it"))
    # the core alone stays the core alone
    assert "stat:larghezza_biorbitale" not in P.qualia_types()
    assert P.combiner_types() == {}


def test_two_packages_never_share_a_prefix(tmp_path):
    P.install(SEPARATE)
    other = copy(SEPARATE, tmp_path, "ritratti-romani")
    iri2 = "https://w3id.org/extendedmatrix/profile/ritratti-romani"
    edit_json(other / "profile.json", lambda m: m.update(name="ritratti-romani", iri=iri2))
    edit_json(other / "examples" / "testa-esempio.em.json",
              lambda d: d["header"].update(profiles=[{"iri": iri2, "version": "0.1.0"}]))
    t = (other / "em-extension.toml").read_text()
    (other / "em-extension.toml").write_text(t.replace('id = "esempio-statuaria"', 'id = "ritratti-romani"'))
    P.install(other)
    ov, missing, problems = P.activate([{"iri": IRI, "version": "0.1.0"}, {"iri": iri2, "version": "0.1.0"}])
    assert [p.name for p in ov] == ["esempio-statuaria"] and not missing
    clash = next(p for p in problems if p.code == "prefix_clash")
    assert "prefisso 'stat'" in clash.text("it")


# ── em.json: the importer activates, the exporter declares ──────────────────

def _example_doc():
    return json.loads((SEPARATE / "examples" / "testa-esempio.em.json").read_text(encoding="utf-8"))


def test_a_file_with_a_missing_package_opens_and_says_so():
    from s3dgraphy.container import parse_container
    c, warnings = parse_container(_example_doc())
    assert c.graphs["testa"] and c.profiles_missing == [{"iri": IRI, "version": "0.1.0"}]
    assert any("not installed" in w for w in warnings)
    assert not c.profiles


def test_the_importer_activates_the_declared_package():
    from s3dgraphy.container import parse_container
    P.install(SEPARATE)
    c, warnings = parse_container(_example_doc())
    assert [p.name for p in c.profiles] == ["esempio-statuaria"] and not c.profiles_missing
    assert not [w for w in warnings if "package" in w]
    assert c.profiles.label("stat:c_larghezza_biorbitale", "it") == "Larghezza biorbitale"


def test_the_exporter_declares_what_the_content_uses_and_keeps_what_was_declared():
    from s3dgraphy.container import build_container, parse_container
    P.install(SEPARATE)
    doc = _example_doc()
    doc["header"].pop("profiles")
    c, _ = parse_container(doc)
    out = build_container(c)
    assert out["header"]["profiles"] == [{"iri": IRI, "version": "0.1.0"}]
    # a declaration of a package not installed here survives the write
    doc = _example_doc()
    doc["header"]["profiles"].append({"iri": "https://example.org/altro", "version": "2.0.0"})
    c, _ = parse_container(doc)
    assert {"iri": "https://example.org/altro", "version": "2.0.0"} in build_container(c)["header"]["profiles"]


def test_a_file_without_packages_gets_no_profiles_key():
    from s3dgraphy.container import build_container, container_of
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("u1", "US1"))
    assert "profiles" not in build_container(container_of(g))["header"]


def test_the_multigraph_manager_keeps_the_declaration(tmp_path):
    from s3dgraphy.multigraph.multigraph import MultiGraphManager
    src = tmp_path / "in.em.json"
    src.write_text(json.dumps(_example_doc()), encoding="utf-8")
    m = MultiGraphManager()
    m.load_container(str(src), replace=True)
    out = tmp_path / "out.em.json"
    m.save_container(str(out))
    assert {"iri": IRI, "version": "0.1.0"} in json.loads(out.read_text())["header"]["profiles"]


# ── the command line ────────────────────────────────────────────────────────

def test_the_command_line_validates(tmp_path, capsys):
    from s3dgraphy.profiles.__main__ import main
    assert main(["validate", str(MIXED)]) == 0
    bad = _break(tmp_path, lambda m: m.update(prefix="X"))
    assert main(["validate", "--lang", "it", str(bad)]) == 1
    assert "prefix 'X'" in capsys.readouterr().out


def test_a_package_quale_with_its_scheme_is_a_controlled_field():
    from s3dgraphy import terms
    P.install(SEPARATE)
    ov = P.overlay([{"iri": IRI, "version": "0.1.0"}])
    node = {"id": "p", "node_type": "property", "name": "stat:lavorazione", "data": {"value": "gradina"}}
    assert not terms.is_controlled(node)
    assert terms.is_controlled(node, ov)
    w = terms.vocabulary_warnings({"nodes": [node]}, overlay=ov)
    assert [x["kind"] for x in w] == ["uncontrolled_value"]
    assert terms.vocabulary_warnings({"nodes": [node]}) == []
