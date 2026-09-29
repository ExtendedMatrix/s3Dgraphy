"""Every 2D icon the datamodel DECLARES exists — because 2D is what renders.

The asymmetry between the two assertions in this file is the whole point:

* **2D is enforced.** `em_visual_rules.node_styles` is read by EMStudio's
  `icons.ts`, which resolves vector-then-raster and returns *null* when neither
  file is there. A declaration naming a file that does not exist therefore fails
  SILENTLY: the canvas draws the node's shape and nobody sees an error. Measured
  on 2026-08-29: four such declarations had accumulated (SE, TSU, serUSD, and
  `unknown`, which named a `unknown.png` that never existed), plus GRAPH, which
  had *neither* half and drew no icon at all.
* **3D is reported, not enforced.** Sixteen of the forty-one styles declare a
  `.glb` that has not been modelled yet, and that is a known state of the visual
  language rather than a bug: the 3D set covers the stratigraphic core and stops
  there. Asserting it would mean a permanently red suite or sixteen fabricated
  assets, and a placeholder that looks official is harder to notice than an
  absence. So it is counted and named, and the number is allowed to go down.
"""

from __future__ import annotations

import json
import pathlib

CONFIG = (pathlib.Path(__file__).resolve().parent.parent
          / "src" / "s3dgraphy" / "JSON_config")

_2D_FIELDS = ("2d_file_vect", "2d_file_rast", "file_2d")


def _styles():
    return json.loads((CONFIG / "em_visual_rules.json").read_text(
        encoding="utf-8"))["node_styles"]


def _declared(fields):
    for key, style in _styles().items():
        if not isinstance(style, dict):
            continue
        for field in fields:
            path = style.get(field)
            if isinstance(path, str):
                yield key, field, path


def test_every_declared_2D_icon_is_there():
    missing = [f"{key}.{field} → {path}"
               for key, field, path in _declared(_2D_FIELDS)
               if not (CONFIG / path).is_file()]
    assert not missing, (
        "the datamodel names 2D icons that do not exist. `icons.ts` returns null "
        "and the canvas quietly draws the shape instead, so this never shows up "
        "as an error — which is why it is a test:\n  " + "\n  ".join(missing))


def test_each_field_names_its_own_half():
    """`2d_file_vect` is a `.svg`, `2d_file_rast` is a `.png` — the field says
    what kind of file it is, and until 1.6.19 seventeen of them lied.

    Every one duplicated the OTHER field of its style, so nothing drew wrong:
    `icons.ts` dedupes by basename. The damage was to the reader who trusts the
    field name — the glyph tool picks its source from `2d_file_vect` if it is an
    `.svg`, and a PNG sitting there meant "no vector", said the wrong way round.
    """
    wrong = [f"{key}.{field} → {path}"
             for key, field, path in _declared(("2d_file_vect", "2d_file_rast"))
             if not path.endswith(".svg" if field == "2d_file_vect" else ".png")]
    assert not wrong, (
        "these declarations name the other half (vect must be .svg, rast must "
        "be .png):\n  " + "\n  ".join(wrong))


def test_every_glyph_type_declares_the_svg_its_paths_come_from():
    """1.6.20 · a glyph type's `2d_file_vect` IS the source of its `2d_glyphs`
    entry — the file `glyphs_from_svg` built the paths from.

    The two can drift in two ways, both seen: a style that declares no vector
    although the SVG exists (AUTH_AI, LIC, EMB after 1.6.19 correctly removed a
    `.png` from the vect field), and one whose declared vector is NOT the glyph
    (NARR declared the 617 KB illustration, AUTH a Font Awesome silhouette). A
    consumer that does not read `2d_glyphs` — Blender, the GraphML palette —
    reads `2d_file_vect`, and must reach the same drawing.
    """
    rules = json.loads((CONFIG / "em_visual_rules.json").read_text(encoding="utf-8"))
    styles = rules["node_styles"]
    glyphs = rules["2d_glyphs"]
    # node_type → node_styles key, the table the glyph tool itself uses
    from s3dgraphy.tools.glyphs_from_svg import STYLE_KEY
    wrong = []
    for node_type in rules["2d_render_glyph_types"]["types"]:
        key = STYLE_KEY.get(node_type)
        entry = glyphs.get(node_type)
        if not key or not entry:
            continue
        vect = styles.get(key, {}).get("2d_file_vect")
        if vect != entry["source"]:
            wrong.append(f"{key}.2d_file_vect = {vect!r}, glyph source {entry['source']!r}")
    assert not wrong, ("a glyph type must declare the SVG its paths come from:\n  "
                       + "\n  ".join(wrong))
    for key in ("AUTH_AI", "LIC", "EMB"):
        assert styles[key].get("2d_file_vect", "").endswith(".svg"), key
    assert not any(e.get("draft") for e in glyphs.values() if isinstance(e, dict)), \
        "no glyph is a draft since 1.6.20"


def test_every_node_type_the_canvas_draws_resolves_to_a_FILE():
    """One level past the declaration: what `icons.ts` would actually reach.

    Its order is declared-vector, declared-raster, then a file named after the
    type. A style whose declarations are all stale still draws if the convention
    saves it — and one where neither does draws nothing. GRAPH was the second
    case until 2026-08-29.
    """
    icons = CONFIG / "src" / "2D"
    unresolved = []
    for key, style in _styles().items():
        if not isinstance(style, dict):
            continue
        found = any((CONFIG / style[f]).is_file()
                    for f in _2D_FIELDS if isinstance(style.get(f), str))
        found = found or any((icons / f"{key}{ext}").is_file()
                             for ext in (".svg", ".png"))
        if not found:
            unresolved.append(key)
    # Two allowances, and they are different things.
    #
    # SHARING: `BR`, `serUSVn`, `serUSVs` are drawn with somebody else's file,
    # spelled out in `icons.ts::FILE_ALIAS` rather than in the datamodel.
    # Declared sharing, not a gap.
    shared = {"BR", "serUSVn", "serUSVs"}
    # A KNOWN GAP: three of the five group types have no drawing and draw
    # nothing. Their siblings do (`ActivityNodeGroup.svg`,
    # `ParadataNodeGroup.svg`), so this is an unfinished family rather than a
    # design decision — and finishing it is an act of EM iconography with an
    # author, not a thing to fill in from a test. Named here so the number can
    # only go DOWN.
    #
    # …AND ON 2026-09-10 IT WENT UP BY ONE, which is worth recording rather
    # than smoothing over. `RepresentationModelNodeGroup` (EM16-RMNG) arrived
    # with its GraphML/style identity complete — group shape, RM-family
    # title-tab (#FF6600) — and no icon, because choosing one is the authored
    # act this comment reserves. Two forms were available and both were
    # declined on purpose: drawing a new mark (forbidden here), and declaring
    # `file_2d` onto an existing file — legitimate in this datamodel (`UL`,
    # `USN`, `USNt` all share `src/2D/US.png` that way) but still a choice
    # about what the mark MEANS. Left to E.D., and flagged in the EM16-RMNG
    # report under openings.
    known_gap = {"LocationNodeGroup", "TimeBranchNodeGroup",
                 "RepresentationModelNodeGroup"}
    assert set(unresolved) <= shared | known_gap, (
        f"these node types would draw NO icon at all: "
        f"{sorted(set(unresolved) - shared - known_gap)}")


def test_the_3D_gap_is_counted_and_named_rather_than_asserted():
    """Reported, and the number is allowed to go DOWN, never silently up."""
    missing = sorted(key for key, _field, path in _declared(("file_3d",))
                     if not (CONFIG / path).is_file())
    # the state on 2026-08-29: the 3D set covers the stratigraphic core, and the
    # newer families (rights, references, DTC, georeferencing) are unmodelled
    assert len(missing) <= 16, (
        f"{len(missing)} styles declare a .glb that is not there — MORE than the "
        f"16 known on 2026-08-29. A new type should either ship its model or not "
        f"declare one:\n  " + "\n  ".join(missing))
    # the two georeferencing types added on 2026-08-29 are in that list, and the
    # test says so rather than letting them hide in a count
    assert {"GCP", "RGT"} <= set(missing) or not ({"GCP", "RGT"} & set(missing))


# ═════════════════════════════════════════════════════════════════════════════
# THE OTHER FAMILY — `dtc_kinds[*][*].glyph`, which nothing was checking
# ═════════════════════════════════════════════════════════════════════════════
#
# The tests above walk `node_styles` and its FILE-PATH fields. The DTC kind
# vocabulary declares its icon differently — a bare `glyph` NAME, resolved by
# convention to `src/2D/dtc/<glyph>.svg` — and in a different block, so every
# check in this file and the one EMStudio's `sync-datamodels.sh` prints walked
# straight past it.
#
# It was not caught by a failure. It was caught by COUNTING, on 2026-09-16: the
# apparatus axis declared seven glyphs (`11_device_optical` … `_gnss`) and the
# directory stopped at `10_laserscanner.svg`. Seven declared, zero drawn, every
# suite green and the vendoring script reporting «all declared files present» —
# true of what it looks at, and that is the whole lesson: a report is only as
# honest as its scope, and a family nobody walks is a family nobody defends.
#
# ENFORCED, like the 2D icons above and unlike the 3D gap, and the reason is the
# datamodel's own note: these names are «recorded here as data only», wired to a
# renderer in a later slice. That is exactly the window in which an absence costs
# nothing to fix and is invisible — and the moment something reads them, the same
# absence becomes a hole in the canvas that `icons.ts` draws as silence.

DTC_GLYPHS = CONFIG / "src" / "2D" / "dtc"


def _kinds():
    return json.loads((CONFIG / "em_visual_rules.json").read_text(
        encoding="utf-8")).get("dtc_kinds") or {}


def _declared_glyphs(kinds):
    """(axis, kind, glyph) for every kind that names one. Shared with the
    counterexample below so the two cannot scan differently — a counterexample
    that reads the vocabulary its own way proves nothing about the assertion."""
    for axis, entries in kinds.items():
        if not isinstance(entries, dict):
            continue
        for kind, spec in entries.items():
            if isinstance(spec, dict) and isinstance(spec.get("glyph"), str):
                yield axis, kind, spec["glyph"]


def test_every_glyph_the_DTC_vocabulary_names_is_drawn():
    missing = [f"dtc_kinds.{axis}.{kind} → src/2D/dtc/{glyph}.svg"
               for axis, kind, glyph in _declared_glyphs(_kinds())
               if not (DTC_GLYPHS / f"{glyph}.svg").is_file()]
    assert not missing, (
        "the DTC vocabulary names glyphs that have not been drawn. Adding a kind "
        "is meant to be a JSON entry PLUS A SIGN, and this is the half that has "
        "no compiler:\n  " + "\n  ".join(missing))


def test_THE_COUNTEREXAMPLE_an_undrawn_glyph_is_seen():
    """The assertion above passes on an empty walk as happily as on a full one.

    Feed the same collector a kind naming a glyph that certainly does not exist,
    and it must come back — otherwise the test above is green because it looks at
    nothing, which is the state it was written to end.
    """
    invented = {"device": {"teleporter": {"glyph": "11_device_teleporter"}}}
    seen = list(_declared_glyphs(invented))
    assert seen == [("device", "teleporter", "11_device_teleporter")], seen
    assert not (DTC_GLYPHS / "11_device_teleporter.svg").is_file()


def test_the_apparatus_family_keeps_ONE_outline():
    """The family promise, checked as a fact rather than trusted as a comment.

    Every apparatus glyph is the same body and stub with one inner mark changed,
    so the family reads from far away and the genus from close up. Redrawing one
    of them «a bit bigger» is the change that dissolves the family silently, and
    it is invisible in a diff of eight files that all look like SVG.
    """
    # The body DECLARES itself — `class="device-body"` on the rounded box and on
    # the connector stub. Counting `<rect>` instead was the first version of this
    # test, and it failed on `computer`, whose inner mark is a rectangle too: a
    # check that recognises its target by shape rather than by name breaks on the
    # first drawing it did not foresee.
    bodies = {}
    for path in sorted(DTC_GLYPHS.glob("11_device*.svg")):
        bodies[path.name] = tuple(
            line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if 'class="device-body"' in line)
    assert len(bodies) >= 8, f"expected the whole family, found {sorted(bodies)}"
    assert all(len(b) == 2 for b in bodies.values()), (
        "every apparatus glyph carries exactly two device-body rects — the box "
        f"and the stub: {[(n, len(b)) for n, b in bodies.items() if len(b) != 2]}")
    shapes = set(bodies.values())
    assert len(shapes) == 1, (
        "the apparatus glyphs no longer share one outline:\n  "
        + "\n  ".join(f"{name}: {b}" for name, b in sorted(bodies.items())))
