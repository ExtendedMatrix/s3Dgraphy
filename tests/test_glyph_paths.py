"""`2d_glyphs` — the pictograms as paths — is complete, well-formed and in step.

The block is GENERATED (`s3dgraphy.tools.glyphs_from_svg`) from the authored
SVGs, so the first thing to defend is that nobody edited one side without the
other: regenerating must give back exactly what is committed. The rest defends
the promise the block makes to a consumer — that `new Path2D(d)` is all it
takes, that a role tells it what it may retheme, and that `aspect` is the number
the layout already uses.

The path check below is deliberately NOT the tool's own parser. A check that
parses with the code it is checking can only prove the code agrees with itself;
this one is a strict grammar for the subset the block promises (absolute M, L, C,
Z) and would reject an arc or a relative command the tool let through.
"""

from __future__ import annotations

import json
import pathlib
import re
import warnings

from s3dgraphy.tools import glyphs_from_svg as tool

CONFIG = (pathlib.Path(__file__).resolve().parent.parent
          / "src" / "s3dgraphy" / "JSON_config")


def _rules():
    return json.loads((CONFIG / "em_visual_rules.json").read_text(encoding="utf-8"))


def _entries(rules=None):
    rules = rules or _rules()
    return {k: v for k, v in rules["2d_glyphs"].items() if not k.startswith("_")}


def _roles(rules=None):
    rules = rules or _rules()
    return {k for k in rules["2d_glyphs"]["_roles"] if not k.startswith("_")}


# ── a strict grammar for the promised subset ────────────────────────────────

_NUM = r"-?(?:\d+(?:\.\d{1,2})?|\.\d{1,2})"
_PAIR = rf"{_NUM} {_NUM}"
_SEG = rf"(?:M{_PAIR}|L{_PAIR}|C{_PAIR} {_PAIR} {_PAIR}|Z)"
_D = re.compile(rf"(?:M{_PAIR}(?:{_SEG})*)+")
_HEX = re.compile(r"#[0-9A-F]{6}")


def path_problems(d):
    """Why `d` is not in the promised subset, or [] when it is."""
    out = []
    if not isinstance(d, str) or not d:
        return ["empty"]
    if not _D.fullmatch(d):
        bad = sorted(set(re.findall(r"[A-Za-z]", d)) - set("MLCZ"))
        out.append(f"not absolute M/L/C/Z with ≤2 decimals{' (has ' + ''.join(bad) + ')' if bad else ''}")
    return out


def layer_problems(layer, vocabulary):
    out = [f"d: {p}" for p in path_problems(layer.get("d"))]
    if layer.get("role") not in vocabulary:
        out.append(f"role {layer.get('role')!r} not in {sorted(vocabulary)}")
    paints = [k for k in ("fill", "stroke") if k in layer]
    if len(paints) != 1:
        out.append(f"exactly one of fill/stroke, got {paints}")
    for k in paints:
        if not _HEX.fullmatch(str(layer[k])):
            out.append(f"{k} {layer[k]!r} is not #RRGGBB")
    if "stroke" in layer and not (isinstance(layer.get("stroke_width"), (int, float))
                                  and layer["stroke_width"] > 0):
        out.append("a stroked layer needs a positive stroke_width")
    if "opacity" in layer and not 0 < layer["opacity"] < 1:
        out.append(f"opacity {layer['opacity']} is not in (0,1) — 1 is written by omission")
    known = {"d", "role", "fill", "fill_rule", "stroke", "stroke_width",
             "line_cap", "line_join", "opacity"}
    if set(layer) - known:
        out.append(f"unknown fields {sorted(set(layer) - known)}")
    return out


# ── completeness ────────────────────────────────────────────────────────────

def test_every_glyph_type_and_every_DTC_kind_has_an_entry():
    rules = _rules()
    entries = _entries(rules)
    wanted = list(rules["2d_render_glyph_types"]["types"])
    wanted += [f"dtc:{kind}" for _axis, kind, _g in tool.dtc_kinds(rules)]
    missing = [k for k in wanted if k not in entries]
    assert not missing, (
        "these glyphs have no paths, so a consumer reading 2d_glyphs falls back to "
        f"the shape for them: {missing}")
    extra = sorted(set(entries) - set(wanted))
    assert not extra, f"entries nothing asks for: {extra}"


# ── drift ───────────────────────────────────────────────────────────────────

def test_regenerating_from_the_SVGs_gives_back_the_committed_block():
    committed = _rules()["2d_glyphs"]
    fresh = tool.build()
    drifted = sorted(k for k in set(committed) | set(fresh)
                     if committed.get(k) != fresh.get(k))
    assert not drifted, (
        "2d_glyphs is out of step with its SVGs — someone edited one side. The "
        "SVG is the source: fix the drawing there and run\n"
        "  python -m s3dgraphy.tools.glyphs_from_svg --write\n"
        f"drifted: {drifted}")


def test_the_tool_check_agrees():
    assert tool.problems() == []
    assert tool.main(["--check"]) == 0


# ── well-formed ─────────────────────────────────────────────────────────────

def test_every_layer_is_one_path_in_one_colour_with_a_known_role():
    vocabulary = _roles()
    bad = []
    for key, entry in _entries().items():
        for i, layer in enumerate(entry["layers"]):
            bad += [f"{key}[{i}]: {p}" for p in layer_problems(layer, vocabulary)]
    assert not bad, "\n  ".join(["malformed layers:"] + bad)


def test_the_role_vocabulary_says_what_may_be_recoloured():
    table = _rules()["2d_glyphs"]["_roles"]
    roles = {k: v for k, v in table.items() if not k.startswith("_")}
    assert {"ink", "paper", "ground", "accent"} <= set(roles)
    assert all(isinstance(v.get("recolor"), bool) and v.get("meaning")
               for v in roles.values()), roles
    # the semantic colour is the one a theme must never touch
    assert roles["accent"]["recolor"] is False
    # and the tool reads THIS table, not a copy of its own
    assert tool.roles() == {k: v["recolor"] for k, v in roles.items()}


def test_aspect_is_the_viewBox_and_the_number_the_layout_reads():
    rules = _rules()
    bad = []
    for key, entry in _entries(rules).items():
        vb = entry["viewBox"]
        if vb[:2] != [0, 0]:
            bad.append(f"{key}: viewBox does not start at the origin {vb}")
        if round(vb[2] / vb[3], 3) != entry["aspect"]:
            bad.append(f"{key}: aspect {entry['aspect']} ≠ viewBox {vb[2]}/{vb[3]}")
        declared = tool.declared_aspect(rules, key)
        if abs(declared - entry["aspect"]) > 0.0015:
            bad.append(f"{key}: 2d_render_glyph_types.aspect = {declared}, "
                       f"the drawing = {entry['aspect']}")
    assert not bad, "\n  ".join(bad)


# ── drafts ──────────────────────────────────────────────────────────────────

def test_drafts_are_accepted_but_named():
    drafts = sorted(k for k, e in _entries().items() if e.get("draft"))
    if drafts:
        warnings.warn(
            "2d_glyphs carries DRAFT pictograms awaiting E.D.'s approval "
            f"(see the glifi-confronto sheet): {drafts}", UserWarning)
    for key in drafts:
        src = _entries()[key]["source"]
        # a draft beside the official files would be VENDORED and DRAWN by
        # EMStudio's next sync (icons.ts prefers an .svg of the same name)
        assert src.startswith("src/2D/bozze/"), (key, src)


def test_a_draft_is_marked_in_its_file_not_only_in_the_JSON():
    for key, entry in _entries().items():
        text = (CONFIG / entry["source"]).read_text(encoding="utf-8")
        marked = bool(re.search(r"<!--[^>]*BOZZA", text))
        assert marked == bool(entry.get("draft")), (key, entry["source"])


# ── counterexamples: the checks above can fail ──────────────────────────────

def test_THE_COUNTEREXAMPLES_are_rejected():
    vocab = _roles()
    assert path_problems("M0 0L10 10Z") == []
    assert path_problems("M0 0C1 2 3 4 5 6ZM7 7L8 8") == []
    assert path_problems("M0 0A5 5 0 0 1 10 10")        # an arc left in
    assert path_problems("m0 0l10 10z")                 # relative commands
    assert path_problems("M0 0H10")                     # H/V shorthand
    assert path_problems("M0.123 0L1 1")                # more than 2 decimals
    assert path_problems("L0 0")                        # no moveto
    ok = {"d": "M0 0L1 1Z", "role": "ink", "fill": "#000000"}
    assert layer_problems(ok, vocab) == []
    assert layer_problems({**ok, "role": "sepia"}, vocab)
    assert layer_problems({**ok, "stroke": "#000000", "stroke_width": 1}, vocab)
    assert layer_problems({**ok, "fill": "#000"}, vocab)
    assert layer_problems({**ok, "opacity": 1}, vocab)


def test_THE_COUNTEREXAMPLE_drift_is_seen():
    """Touch one committed coordinate and the drift check must see it."""
    rules = _rules()
    entry = rules["2d_glyphs"]["extractor"]
    entry["layers"][0]["d"] = entry["layers"][0]["d"].replace("M", "M1", 1)
    assert any(p.startswith("extractor:") for p in tool.problems(rules))


def test_the_normaliser_on_the_shapes_it_must_convert(tmp_path):
    """circle / rect(rx) / polygon / transform / class CSS → one M/L/C/Z path."""
    svg = tmp_path / "probe.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 10 20 20">'
        '<style>.a{fill:#fff}</style>'
        '<g transform="translate(10,10)">'
        '<circle class="a" cx="10" cy="10" r="5"/>'
        '<rect x="2" y="2" width="6" height="4" rx="1" fill="#000"/>'
        '<polygon points="0,0 4,0 4,4" fill="#888687" transform="scale(2)"/>'
        '<line x1="0" y1="0" x2="5" y2="5" stroke="#000" stroke-width="0.5"'
        ' transform="scale(2)"/>'
        '</g></svg>', encoding="utf-8")
    e = tool.glyph_from_svg(svg)
    assert e["viewBox"] == [0, 0, 20.0, 20.0] and e["aspect"] == 1.0
    roles = [layer["role"] for layer in e["layers"]]
    assert roles == ["paper", "ink", "ground", "ink"], roles
    assert e["layers"][2]["d"] == "M0 0L8 0L8 8Z"          # scaled, viewBox at origin
    assert e["layers"][3]["stroke_width"] == 1.0            # scaled with the glyph
    for layer in e["layers"]:
        assert layer_problems(layer, _roles()) == [], layer
