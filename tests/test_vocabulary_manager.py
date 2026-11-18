"""MICRO-PL02 · GESTORE-DEI-VOCABOLARI (row W20 of the extensions plan,
E.D. 18 Nov 2026): versions side by side, who brings a vocabulary and who
owns it, the three cases of a duplicate (SPEC-pacchetto §16.7), install from
a package's envelope with everything validated first, tier C «Download
locally» by hand, removal that keeps the vocabularies (D-19), labels through
VERIFIED alignments."""
import hashlib
import io
import json
import zipfile

import pytest

from s3dgraphy import terms as T
from s3dgraphy import vocabularies as V
from s3dgraphy.authorities import packages as P
from s3dgraphy.nodes.property_node import PropertyNode

NS = "https://w3id.org/extendedmatrix/profile/esempio-statuaria/vocab/punti-volto/"
OTHER_NS = "https://example.org/thesaurus/"
AAT = "http://vocab.getty.edu/aat/"
ICCD = "http://dati.beniculturali.it/vocabularies/materia_e_tecnica-ra/def/"


def _ttl(scheme, version, labels):
    lines = ["@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
             "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
             f"<{scheme}> a skos:ConceptScheme ; owl:versionInfo \"{version}\" ."]
    for local, lab in labels.items():
        lines.append(f"<{scheme}{local}> a skos:Concept ; skos:inScheme <{scheme}> ; "
                     f"skos:prefLabel \"{lab}\"@it .")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _nt(scheme, version, labels):
    out = [f"<{scheme}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
           f"<http://www.w3.org/2004/02/skos/core#ConceptScheme> .",
           f"<{scheme}> <http://www.w3.org/2002/07/owl#versionInfo> \"{version}\" ."]
    for local, (lab, lang) in labels.items():
        out.append(f"<{scheme}{local}> <http://www.w3.org/2004/02/skos/core#prefLabel> \"{lab}\"@{lang} .")
    return ("\n".join(out) + "\n").encode("utf-8")


def _pkg(vid, version, data, *, scheme=None, tier="A", fname="s.nt"):
    m = {"format": P.PACKAGE_FORMAT, "id": vid, "version": version, "snapshot_date": "2026-11-18",
         "languages": [], "license": "CC0-1.0" if tier == "A" else "CC BY-SA 4.0", "tier": tier,
         "attribution": f"attribution of {vid}",
         "source": {"file": f"source/{fname}", "sha256": hashlib.sha256(data).hexdigest()}}
    if scheme:
        m["scheme"] = scheme
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(m))
        z.writestr(m["source"]["file"], data)
    return buf.getvalue()


def _envelope(tmp_path, pid, vocabs, files, *, code=False):
    root = tmp_path / pid
    data_root = root / ("data" if code else ".")
    root.mkdir(parents=True, exist_ok=True)
    for rel, blob in files.items():
        p = data_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    lines = ['schema_version = "1.0.0"', f'id = "{pid}"', 'version = "1.0.0"',
             f'name = "{pid} (ESEMPIO)"', 'maintainer = "Curatori di esempio"', "", "[data]"]
    if code:
        lines.append('root = "data/"')
    for v in vocabs:
        lines.append("  [[data.vocabularies]]")
        for k, val in v.items():
            if isinstance(val, dict):
                inner = ", ".join(f'{a} = "{b}"' for a, b in val.items())
                lines.append(f"  {k} = {{ {inner} }}")
            else:
                lines.append(f'  {k} = "{val}"')
    if code:
        lines += ["", "[code]", 'root = "code/"', 'entry = "x:plugin"']
    (root / "em-extension.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def _entry(path, blob, version="0.1.0", **kw):
    e = {"path": path, "scheme": NS, "version": version, "license": "SPDX:CC-BY-4.0",
         "fascia": "A", "digest": "sha256:" + hashlib.sha256(blob).hexdigest()}
    e.update(kw)
    return e


# ── versions side by side ───────────────────────────────────────────────────

def test_two_versions_side_by_side_and_a_value_keeps_its_own():
    v1 = _nt(OTHER_NS, "1", {"a": ("arenaria", "it")})
    v2 = _nt(OTHER_NS, "2", {"a": ("arenaria fine", "it")})
    P.vocab_install(_pkg("thes", "1", v1, scheme=OTHER_NS))
    s = P.vocab_install(_pkg("thes", "2", v2, scheme=OTHER_NS))
    assert s["warnings"] == []
    row, = V.vocab_installed()
    assert row["version"] == "2" and [v["version"] for v in row["versions"]] == ["2", "1"]
    assert len(V.vocab_installed(all_versions=True)) == 2
    assert P.vocab_folder("thes", "1").name == "1" and P.vocab_folder("thes").name == "2"
    # a value saved with 1 resolves with 1; one without a version with the newest
    old = PropertyNode(node_id="p", name="material_type", value="arenaria")
    T.set_term(old, T.make_term(OTHER_NS + "a", "arenaria", lang="it", vocabulary="thes", version="1"))
    assert T.value_label(old, "it")["text"] == "arenaria"
    new = PropertyNode(node_id="q", name="material_type", value="arenaria")
    T.set_term(new, T.make_term(OTHER_NS + "a", "arenaria", lang="it", vocabulary="thes"))
    assert T.value_label(new, "it")["text"] == "arenaria fine"
    assert V.versions_line(row) == "2 (user) · 1 (user)"


def test_a_micro_u_flat_folder_is_read_and_becomes_its_version(tmp_path):
    data = _nt(OTHER_NS, "1", {"a": ("arenaria", "it")})
    P.vocab_install(_pkg("thes", "1", data))
    # rebuild MICRO-U's layout by hand: <id>/manifest.json
    f = P.vocab_folder("thes", "1")
    flat = P.vocab_dir() / "thes"
    for p in list(f.iterdir()):
        p.rename(flat / p.name)
    f.rmdir()
    P._changed()
    assert P.vocab_folder("thes") == flat
    assert V.vocab_installed()[0]["status"] == "ready"
    P.vocab_install(_pkg("thes", "2", _nt(OTHER_NS, "2", {"a": ("x", "it")})))
    assert sorted(v["version"] for v in V.vocab_installed()[0]["versions"]) == ["1", "2"]
    assert not (flat / "manifest.json").exists()


# ── the three cases of a duplicate ──────────────────────────────────────────

def test_same_digest_is_one_copy_with_one_more_carrier():
    data = _nt(OTHER_NS, "1", {"a": ("arenaria", "it")})
    P.vocab_install(_pkg("thes", "1", data, scheme=OTHER_NS), carrier="extension:a")
    s = P.vocab_install(_pkg("thes", "1", data, scheme=OTHER_NS), carrier="extension:b")
    assert s["warnings"] == [] and s["carriers"] == ["extension:a", "extension:b"]
    assert len(V.vocab_installed(all_versions=True)) == 1


def test_same_version_other_digest_first_installed_wins_without_the_owner():
    a = _nt(OTHER_NS, "1", {"a": ("arenaria", "it")})
    b = _nt(OTHER_NS, "1", {"a": ("arenaria", "it"), "b": ("tufo", "it")})
    P.vocab_install(_pkg("thes", "1", a, scheme=OTHER_NS), carrier="extension:a")
    s = P.vocab_install(_pkg("thes", "1", b, scheme=OTHER_NS), carrier="extension:b")
    w, = s["warnings"]
    assert w["kind"] == V._pk.WARN_DUPLICATE_KEPT and w["kept_from"] == "extension:a"
    assert "prima" in w["message_it"] and "first" in w["message"]
    assert s["sha256"] == hashlib.sha256(a).hexdigest()
    assert s["carriers"] == ["extension:a", "extension:b"]
    assert [e["kind"] for e in V.vocab_log()] == ["duplicate_kept"]


def test_the_owner_wins_and_replaces_a_copy_installed_before_it(tmp_path):
    mine = _ttl(NS, "0.1.0", {"naso": "naso"})
    copy = _ttl(NS, "0.1.0", {"naso": "naso", "mento": "mento"})
    # ritratti-romani copies punti-volto 0.1.0 with one label more
    ritratti = _envelope(tmp_path, "ritratti-romani", [_entry("vocab/pv.ttl", copy)],
                         {"vocab/pv.ttl": copy})
    r = V.install_extension_vocabularies(ritratti)
    assert r["warnings"] == [] and r["installed"][0]["owner"] == "extension:esempio-statuaria"
    statuaria = _envelope(tmp_path, "esempio-statuaria", [_entry("vocab/pv.ttl", mine)],
                          {"vocab/pv.ttl": mine})
    s = V.install_extension_vocabularies(statuaria)
    w, = s["warnings"]
    assert w["kind"] == "replaced_by_owner" and "padrone" in w["message_it"]
    row = s["installed"][0]
    assert row["sha256"] == hashlib.sha256(mine).hexdigest() and row["copy_of"] == "extension:esempio-statuaria"
    assert row["carriers"] == ["extension:ritratti-romani", "extension:esempio-statuaria"]
    # and the other way round: the owner first, the copy is not installed
    again = V.install_extension_vocabularies(ritratti)
    assert again["warnings"][0]["kind"] == "duplicate_kept"
    assert "padrone" in again["warnings"][0]["message_it"]
    assert again["installed"][0]["sha256"] == hashlib.sha256(mine).hexdigest()


def test_owner_of():
    assert V.owner_of(NS) == "extension:esempio-statuaria"
    assert V.owner_of("https://w3id.org/extendedmatrix/vocab/em-us-definizione/") == "vocabularies"
    assert V.owner_of(AAT, "A") == "vocabularies"
    assert V.owner_of("https://example.org/iaa/", "C") == "local"
    assert V.carrier_of_origin("https://github.com/ExtendedMatrix/vocabularies/releases/x.zip") == "vocabularies"
    assert V.carrier_of_origin("https://em.localhost:8443/em/v1/vocabularies/a.emvocab.zip") == "node:em.localhost:8443"
    assert V.carrier_of_origin("/Users/x/a.emvocab.zip") == "user"


# ── install from a package ──────────────────────────────────────────────────

def test_a_package_hands_its_vocabularies_to_the_manager(tmp_path):
    ttl = _ttl(NS, "0.1.0", {"naso": "naso", "mento": "mento"})
    root = _envelope(tmp_path, "esempio-statuaria", [_entry("vocab/pv.ttl", ttl)],
                     {"vocab/pv.ttl": ttl}, code=True)
    r = V.install_extension_vocabularies(root)
    row = r["installed"][0]
    assert row["id"] == "esempio-statuaria.punti-volto" and row["tier"] == "A"
    assert row["carriers"] == ["extension:esempio-statuaria"] and row["status"] == "ready"
    assert P.search("naso")[0]["uri"] == NS + "naso"
    # the same from a zip of the folder
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p in root.rglob("*"):
            if p.is_file():
                z.write(p, "esempio-statuaria/" + str(p.relative_to(root)))
    assert V.plan_extension_vocabularies(buf.getvalue())["problems"] == []


def test_everything_is_validated_before_anything_is_written(tmp_path):
    good = _ttl(NS, "0.1.0", {"naso": "naso"})
    other = "https://w3id.org/extendedmatrix/profile/esempio-statuaria/vocab/lavorazione/"
    bad = _ttl(other, "0.1.0", {"gradina": "gradina"})
    root = _envelope(tmp_path, "esempio-statuaria",
                     [_entry("vocab/pv.ttl", good),
                      _entry("vocab/lav.ttl", b"something else", scheme=other)],
                     {"vocab/pv.ttl": good, "vocab/lav.ttl": bad})
    with pytest.raises(V.PackageError, match="digest does not match"):
        V.install_extension_vocabularies(root)
    assert V.vocab_installed() == []


@pytest.mark.parametrize("change,message", [
    ({"fascia": "A", "license": "SPDX:CC-BY-SA-4.0"}, "less prudent"),
    ({"version": "0.2.0"}, "owl:versionInfo"),
    ({"scheme": "https://w3id.org/extendedmatrix/profile/x/vocab/y/"}, "declares no skos:ConceptScheme"),
    ({"fascia": "C"}, "tier C — the package may not carry its file"),
])
def test_a_vocabulary_that_does_not_hold_is_refused(tmp_path, change, message):
    ttl = _ttl(NS, "0.1.0", {"naso": "naso"})
    root = _envelope(tmp_path, "p", [_entry("vocab/pv.ttl", ttl, **change)], {"vocab/pv.ttl": ttl})
    with pytest.raises(V.PackageError, match=message):
        V.install_extension_vocabularies(root)


def test_tiers_against_licences():
    assert V.tier_for_license("CC0-1.0") == "A"
    assert V.tier_for_license("SPDX:CC-BY-4.0") == "A"
    assert V.tier_for_license("ODC-By 1.0") == "A"
    assert V.tier_for_license("CC BY-SA 3.0 IT") == "B"
    assert V.tier_for_license("SPDX:CC-BY-NC-4.0") == "B"
    assert V.tier_for_license("ODbL-1.0") == "B"
    assert V.tier_for_license("LicenseRef-IAA") == "C"
    assert V.tier_for_license("unknown") == "C"
    assert V.check_tier("B", "CC-BY-4.0") is None          # more prudent: fine
    assert V.check_tier("A", "CC BY-SA 3.0 IT")            # less prudent: refused


# ── tier C: a pointer, «Download locally» by hand ───────────────────────────

def test_tier_c_is_a_stub_completed_by_the_file_downloaded_by_hand(tmp_path):
    scheme = "https://example.org/iaa/periods/"
    src = _nt(scheme, "2026-10", {"p1": ("Iron Age II", "en")})
    entry = {"scheme": scheme, "version": "2026-10", "fascia": "C", "license": "LicenseRef-IAA",
             "fetch": {"url": "https://example.org/iaa/periods.nt",
                       "digest": "sha256:" + hashlib.sha256(src).hexdigest(),
                       "terms": "https://example.org/iaa/terms"}}
    root = _envelope(tmp_path, "levante", [entry], {})
    r = V.install_extension_vocabularies(root)
    stub = r["installed"][0]
    assert stub["status"] == "stub" and stub["fetch"]["terms"] == "https://example.org/iaa/terms"
    with pytest.raises(V.PackageError, match="not the one the manifest names"):
        V.vocab_fetch_local(stub["id"], data=b"another file")
    hand = tmp_path / "periods.nt"
    hand.write_bytes(src)
    done = V.vocab_fetch_local(stub["id"], data=str(hand))
    assert done["status"] == "ready" and done["local_copy"] is True
    assert done["carriers"] == ["extension:levante", "local"]
    assert P.search("Iron Age II")[0]["uri"] == scheme + "p1"
    with pytest.raises(V.PackageError, match="not redistributable"):
        V.vocab_package_bytes(stub["id"])


def test_a_node_serves_the_package_it_has(tmp_path):
    data = _nt(OTHER_NS, "1", {"a": ("arenaria", "it")})
    P.vocab_install(_pkg("thes", "1", data, scheme=OTHER_NS))
    blob = V.vocab_package_bytes("thes")
    m = json.loads(zipfile.ZipFile(io.BytesIO(blob)).read("manifest.json"))
    assert "carriers" not in m and "installed" not in m and m["source"]["sha256"] == hashlib.sha256(data).hexdigest()
    s = P.vocab_install(blob, carrier="node:example")
    assert s["carriers"] == ["user", "node:example"] and s["warnings"] == []


# ── removal keeps the vocabularies (D-19) ───────────────────────────────────

def test_releasing_a_package_keeps_its_vocabularies_unless_asked(tmp_path):
    ttl = _ttl(NS, "0.1.0", {"naso": "naso"})
    root = _envelope(tmp_path, "esempio-statuaria", [_entry("vocab/pv.ttl", ttl)], {"vocab/pv.ttl": ttl})
    V.install_extension_vocabularies(root)
    assert [x["id"] for x in V.vocab_carried_only_by("extension:esempio-statuaria")] == \
        ["esempio-statuaria.punti-volto"]
    out = V.vocab_release("extension:esempio-statuaria")
    assert out["orphaned"] and not out["removed"]
    row, = V.vocab_installed()
    assert row["orphan"] is True and row["removed_carriers"] == ["extension:esempio-statuaria"]
    # brought again: no longer orphan
    V.install_extension_vocabularies(root)
    assert V.vocab_installed()[0]["orphan"] is False
    out = V.vocab_release("extension:esempio-statuaria", purge=True)
    assert out["removed"] and V.vocab_installed() == []


# ── labels through verified alignments ──────────────────────────────────────

def test_a_label_through_a_verified_alignment():
    aat = _nt(AAT, "2026-11-18", {"300011286": ("limestone", "en")})
    iccd = _nt(ICCD, "2018-09", {"031": ("calcare", "it")})
    P.vocab_install(_pkg("getty-aat-materials", "2026-11-18", aat))
    P.vocab_install(_pkg("iccd-ra-materia", "2018-09", iccd, tier="B"))
    n = PropertyNode(node_id="p", name="material_type", value="Limestone")
    T.set_term(n, T.make_term(AAT + "300011286", "Limestone", lang="en",
                              vocabulary="getty-aat-materials", version="2026-11-18"))
    assert T.value_label(n, "it")["text"] == "limestone"      # no alignment yet
    row = {"source": {"scheme": "iccd-ra-materia", "concept": ICCD + "031"}, "match": "closeMatch",
           "target": {"scheme": "getty-aat", "concept": AAT + "300011286"}}
    V.install_alignments({"name": "materials", "alignments": [dict(row, status="proposed")]})
    # a proposal never speaks: the label of the language the value was written in
    assert (T.value_label(n, "it")["text"], T.value_label(n, "it")["lang"]) == ("limestone", "en")
    got = V.install_alignments({"name": "materials", "alignments": [dict(row, status="verified")]})
    assert got == {"name": "materials", "rows": 1, "verified": 1}
    lab = T.value_label(n, "it")
    assert (lab["text"], lab["from"], lab["via"]["vocabulary"]) == ("calcare", "alignment", "iccd-ra-materia")
    assert T.value_label(n, "en")["text"] == "limestone"      # its own label first
    assert V.installed_alignments() == [{"name": "materials", "rows": 1, "verified": 1}]
    assert V.remove_alignments("materials") and T.value_label(n, "it")["text"] == "limestone"
