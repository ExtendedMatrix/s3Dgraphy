"""Making a consumer's drift VISIBLE — and refusing to make it a build break.

The tool reports; it does not distribute and it does not write. What is defended
here is the distinction it exists for:

* a consumer we own AND track being behind is a task (`--check` fails);
* a THIRD-PARTY consumer being behind is news to send, not a build break — we do
  not control 3DR's release cycle, and failing our own suite over their vendored
  copy would be theatre;
* an untracked local copy (a `.venv`, a gitignored `ext_libs`) is an
  environment, not a repo state — some of them are pinned on purpose.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy.tools import consumer_drift as drift          # noqa: E402


from s3dgraphy.datamodel import DATAMODEL_FILES, JSON_CONFIG   # noqa: E402


def write(path: pathlib.Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({drift.VERSION_KEY: version, "edge_types": {}}),
                    encoding="utf-8")


def copy_source(entry: dict, root: pathlib.Path) -> None:
    """The consumer holds exactly what s3Dgraphy declares today."""
    base = root / str(entry["dir"])
    base.mkdir(parents=True, exist_ok=True)
    for name in entry["files"]:
        filename = DATAMODEL_FILES[name][0]
        (base / filename).write_bytes((JSON_CONFIG / filename).read_bytes())


def fake_root(tmp_path: pathlib.Path, versions: dict) -> pathlib.Path:
    """A consumer given the source's own connections version gets the whole
    source set (aligned); any other version gets a lone connections file."""
    ours = json.loads(drift.CONNECTIONS_PATH.read_text(encoding="utf-8"))[drift.VERSION_KEY]
    for entry in drift.CONSUMERS:
        version = versions.get(str(entry["name"]))
        if version is None or "dir" not in entry:
            continue
        if version == ours:
            copy_source(entry, tmp_path)
        else:
            write(tmp_path / str(entry["path"]), version)
    return tmp_path


def states(result: dict) -> dict:
    return {str(row["name"]): row["state"] for row in result["consumers"]}


def test_the_source_is_the_json_config_and_it_is_read_not_assumed():
    result = drift.survey()
    ours = json.loads(drift.CONNECTIONS_PATH.read_text(encoding="utf-8"))
    assert result["source"] == ours[drift.VERSION_KEY]


def test_aligned_behind_and_absent_are_three_different_answers(tmp_path):
    ours = drift.survey()["source"]
    root = fake_root(tmp_path, {"EMStudio": ours, "Heriverse": "1.6.2"})
    got = states(drift.survey(str(root)))
    assert got["EMStudio"] == "aligned"
    assert got["Heriverse"] == "behind"
    # a repo this machine does not hold is ABSENT, not behind: nobody has to
    # keep every checkout to run this
    assert got["pyarchinit_stratigraph (ext_libs)"] == "absent"


def test_a_third_party_behind_is_reported_and_does_not_fail(tmp_path, capsys):
    ours = drift.survey()["source"]
    root = fake_root(tmp_path, {"EMStudio": ours, "Heriverse": "1.6.2"})
    code = drift.report(str(root), check=True)
    out = capsys.readouterr().out
    assert code == 0, "3DR's release cycle is not ours to fail over"
    assert "Heriverse" in out and "behind" in out, "…but it IS said"


def test_ours_and_tracked_behind_is_a_task_and_fails_the_check(tmp_path):
    root = fake_root(tmp_path, {"EMStudio": "1.6.2"})
    assert drift.report(str(root), check=True) == 1
    # …and without --check it is still only a report
    assert drift.report(str(root)) == 0


def test_a_local_untracked_copy_never_fails_the_check(tmp_path):
    ours = drift.survey()["source"]
    root = fake_root(tmp_path, {
        "EMStudio": ours,
        "EM-blender-tools (.venv)": "1.5.5",
        "pyarchinit_stratigraph (ext_libs)": "1.6.0",
    })
    assert drift.report(str(root), check=True) == 0


def test_an_unreadable_version_sorts_lowest_rather_than_raising(tmp_path):
    root = fake_root(tmp_path, {"EMStudio": "not-a-version"})
    got = states(drift.survey(str(root)))
    assert got["EMStudio"] == "behind"


def test_nothing_is_written_anywhere(tmp_path):
    ours = drift.survey()["source"]
    root = fake_root(tmp_path, {"Heriverse": "1.6.2"})
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    drift.report(str(root), check=True)
    after = {p: p.read_bytes() for p in root.rglob("*.json")}
    assert before == after, "a report that edits somebody's file is not a report"
    assert ours  # the source itself was only read


# ── the fingerprint: every datamodel, by version and by content ─────────────

def emstudio() -> dict:
    return next(e for e in drift.CONSUMERS if e["name"] == "EMStudio")


def test_every_difference_is_named_not_only_the_connections(tmp_path):
    entry = emstudio()
    copy_source(entry, tmp_path)
    nodes = tmp_path / str(entry["dir"]) / DATAMODEL_FILES["nodes"][0]
    doc = json.loads(nodes.read_text(encoding="utf-8"))
    ours = doc["s3Dgraphy_data_model_version"]
    doc["s3Dgraphy_data_model_version"] = "1.6.12"
    nodes.write_text(json.dumps(doc), encoding="utf-8")
    row = next(r for r in drift.survey(str(tmp_path))["consumers"] if r["name"] == "EMStudio")
    assert row["state"] == "behind"
    assert row["differences"] == [f"nodes 1.6.12 vs {ours}"], row["differences"]
    assert drift.report(str(tmp_path), check=True) == 1


def test_a_copy_edited_by_hand_keeps_its_version_and_is_still_caught(tmp_path):
    entry = emstudio()
    copy_source(entry, tmp_path)
    rules = tmp_path / str(entry["dir"]) / DATAMODEL_FILES["visual_rules"][0]
    doc = json.loads(rules.read_text(encoding="utf-8"))
    doc["_touched_by_hand"] = True
    rules.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    row = next(r for r in drift.survey(str(tmp_path))["consumers"] if r["name"] == "EMStudio")
    assert row["state"] == "differs"
    assert row["differences"] == [
        f"visual_rules {doc['version']}: same version, different content"]
    assert drift.report(str(tmp_path), check=True) == 1


def test_reformatting_a_copy_is_not_a_difference(tmp_path):
    entry = emstudio()
    copy_source(entry, tmp_path)
    rules = tmp_path / str(entry["dir"]) / DATAMODEL_FILES["visual_rules"][0]
    doc = json.loads(rules.read_text(encoding="utf-8"))
    rules.write_text(json.dumps(dict(reversed(list(doc.items()))), indent=4), encoding="utf-8")
    row = next(r for r in drift.survey(str(tmp_path))["consumers"] if r["name"] == "EMStudio")
    assert row["state"] == "aligned", row["differences"]


def test_a_templates_snapshot_is_compared_on_its_recorded_fingerprint(tmp_path):
    from s3dgraphy.datamodel import datamodel_fingerprint
    fp = datamodel_fingerprint()
    snap = tmp_path / "stratigraph-templates/registry/s3dgraphy-snapshot.json"
    snap.parent.mkdir(parents=True)
    snap.write_text(json.dumps({"datamodel": fp}), encoding="utf-8")
    row = next(r for r in drift.survey(str(tmp_path))["consumers"]
               if r["name"] == "stratigraph-templates")
    assert row["state"] == "aligned"
    stale = dict(fp, versions=dict(fp["versions"], nodes="1.6.12"))
    snap.write_text(json.dumps({"datamodel": stale}), encoding="utf-8")
    row = next(r for r in drift.survey(str(tmp_path))["consumers"]
               if r["name"] == "stratigraph-templates")
    assert row["state"] == "behind"
    assert row["differences"] == [f"nodes 1.6.12 vs {fp['versions']['nodes']}"]


def test_an_old_snapshot_without_a_fingerprint_is_read_on_its_versions(tmp_path):
    snap = tmp_path / "stratigraph-templates/registry/s3dgraphy-snapshot.json"
    snap.parent.mkdir(parents=True)
    snap.write_text(json.dumps({"node_datamodel_version": "1.6.12",
                                "connections_version": "1.6.27",
                                "qualia_version": "1.6.2"}), encoding="utf-8")
    row = next(r for r in drift.survey(str(tmp_path))["consumers"]
               if r["name"] == "stratigraph-templates")
    assert row["state"] == "behind"
    assert any(line.startswith("nodes 1.6.12 vs ") for line in row["differences"])
