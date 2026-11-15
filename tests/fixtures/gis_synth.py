"""Synthetic GIS data for MICRO-D-GIS-DOCUMENTI (15 Nov 2026).

E.D.: «questo giro apparecchia logica e menu su DATI SINTETICI; i dati reali
vengono dopo». Around a point near Paestum (lon 15.005, lat 40.42 — any
point would do), written by this script, never by hand:

* ``GIS/catasto/`` — a «cadastre» of three sheets in **EPSG:3004** (Monte
  Mario / Italy zone 2): ``foglio_01.tif`` and ``foglio_02.tif`` (GeoTIFF) and
  ``foglio_03.jpg`` with its world file ``foglio_03.jgw`` and ``.prj``; three
  sheets side by side, 400 × 300 m each, 2 m a pixel, a grid of parcels and
  the sheet's number;
* ``GIS/ortofoto/ortofoto_2024.tif`` — an orthophoto in **EPSG:32633**
  (WGS 84 / UTM 33N), 512 × 512 m, 2 m a pixel;
* ``GIS/curve/curve_livello.shp`` (+ .shx .dbf .prj) — contour lines in
  EPSG:32633, rings every 5 m around a hill (field ``quota``);
* ``GIS/dxf/rilievo_cad.dxf`` — an ASCII DXF without a CRS: polylines (the
  plan of a building, layer ``MURI``), lines (``ASSI``), texts (``TESTI``),
  written in 32633 coordinates MINUS a shift (the shift a CAD file is
  usually drawn with); the shift is in ``truth.json`` to be typed in the
  popup «CRS + shift»;
* ``EM/gis_sintetico.em.json`` — the minimal graph of the test, in
  **EPSG:32633**, its GeoPositionNode's shift on the site (not the v10, which
  lies in Romania, EPSG:3844).

``truth.json`` says the numbers (centre, bboxes in both CRS, the DXF's
shift) for the checks. Needs pyproj (the conversion of the sheets' corners)
and Pillow (the pictures).

    python tests/fixtures/gis_synth.py ../_datasets/gis-sintetici
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys

LON, LAT = 15.005, 40.42
DXF_SHIFT = (500000.0, 4470000.0, 0.0)


def _to(crs: str, lon: float, lat: float):
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)


def _sheet_pixels(w, h, n, seed):
    """An RGB picture of a sheet: paper, a grid of parcels, the sheet's number."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (236, 226, 196))
    d = ImageDraw.Draw(im)
    for x in range(0, w, 25):
        d.line([(x + (seed * 7) % 25, 0), (x + (seed * 7) % 25, h)], fill=(150, 110, 70), width=1)
    for y in range(0, h, 20):
        d.line([(0, y), (w, y + (y % 3))], fill=(150, 110, 70), width=1)
    d.rectangle([2, 2, w - 3, h - 3], outline=(80, 40, 20), width=3)
    d.text((10, 10), f"FOGLIO {n:02d}", fill=(60, 20, 10))
    d.text((10, h - 22), "Catasto sintetico 1835", fill=(60, 20, 10))
    return im


def _rows(im):
    w, h = im.size
    px = list(im.getdata())
    return [px[r * w:(r + 1) * w] for r in range(h)]


def _prj(epsg: int, name: str) -> str:
    return f'PROJCS["{name}",AUTHORITY["EPSG","{epsg}"]]'


def _shp_lines(base: str, lines, values, epsg: int, name: str):
    """A PolyLine shapefile (type 3), one part a record, a dbf field «quota»."""
    recs = b""
    allx = [p[0] for ln in lines for p in ln]
    ally = [p[1] for ln in lines for p in ln]
    bbox = (min(allx), min(ally), max(allx), max(ally))
    offsets = []
    for i, ln in enumerate(lines):
        bx = (min(p[0] for p in ln), min(p[1] for p in ln), max(p[0] for p in ln), max(p[1] for p in ln))
        content = struct.pack("<i4d2i", 3, *bx, 1, len(ln)) + struct.pack("<i", 0)
        content += b"".join(struct.pack("<2d", *p) for p in ln)
        offsets.append((50 + len(recs) // 2, len(content) // 2))
        recs += struct.pack(">2i", i + 1, len(content) // 2) + content
    head = lambda total: (struct.pack(">7i", 9994, 0, 0, 0, 0, 0, total) + struct.pack("<2i", 1000, 3)
                          + struct.pack("<4d", *bbox) + struct.pack("<4d", 0, 0, 0, 0))
    open(base + ".shp", "wb").write(head((100 + len(recs)) // 2) + recs)
    shx = head((100 + 8 * len(lines)) // 2) + b"".join(struct.pack(">2i", o, ln) for o, ln in offsets)
    open(base + ".shx", "wb").write(shx)
    fields = [(b"quota", b"N", 10, 1)]
    hlen = 32 + 32 * len(fields) + 1
    rlen = 1 + sum(f[2] for f in fields)
    dbf = struct.pack("<BBBBIHH20x", 3, 126, 11, 15, len(lines), hlen, rlen)
    for nm, t, ln, dec in fields:
        dbf += nm.ljust(11, b"\x00") + t + b"\x00" * 4 + bytes([ln, dec]) + b"\x00" * 14
    dbf += b"\x0D"
    for v in values:
        dbf += b" " + f"{v:10.1f}".encode()
    dbf += b"\x1A"
    open(base + ".dbf", "wb").write(dbf)
    open(base + ".prj", "w").write(_prj(epsg, name))


def _dxf(path: str, polylines, lines, texts):
    out = ["0", "SECTION", "2", "HEADER", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for layer, pts, closed in polylines:
        out += ["0", "LWPOLYLINE", "8", layer, "90", str(len(pts)), "70", "1" if closed else "0"]
        for x, y in pts:
            out += ["10", f"{x:.3f}", "20", f"{y:.3f}"]
    for layer, (a, b) in lines:
        out += ["0", "LINE", "8", layer, "10", f"{a[0]:.3f}", "20", f"{a[1]:.3f}", "30", "0.0",
                "11", f"{b[0]:.3f}", "21", f"{b[1]:.3f}", "31", "0.0"]
    for layer, (x, y), words in texts:
        out += ["0", "TEXT", "8", layer, "10", f"{x:.3f}", "20", f"{y:.3f}", "30", "0.0", "40", "1.5", "1", words]
    out += ["0", "ENDSEC", "0", "EOF"]
    open(path, "w").write("\n".join(out) + "\n")


def make(root: str) -> dict:
    from s3dgraphy.gis.geotiff import write_geotiff
    gis = os.path.join(root, "GIS")
    for sub in ("catasto", "ortofoto", "curve", "dxf"):
        os.makedirs(os.path.join(gis, sub), exist_ok=True)
    os.makedirs(os.path.join(root, "EM"), exist_ok=True)
    mmE, mmN = _to("EPSG:3004", LON, LAT)
    uE, uN = _to("EPSG:32633", LON, LAT)
    truth = {"centre_wgs84": [LON, LAT], "centre_3004": [mmE, mmN], "centre_32633": [uE, uN],
             "sheets": {}, "dxf_shift": list(DXF_SHIFT)}
    # the cadastre: three sheets side by side (west → east), 400 × 300 m, 2 m a pixel
    W, H, px = 200, 150, 2.0
    x_left = round(mmE - 600.0)
    y_top = round(mmN + 150.0)
    for n in (1, 2, 3):
        x0 = x_left + (n - 1) * W * px
        im = _sheet_pixels(W, H, n, n)
        stem = os.path.join(gis, "catasto", f"foglio_{n:02d}")
        if n < 3:
            write_geotiff(stem + ".tif", _rows(im), affine=(x0, px, 0.0, y_top, 0.0, -px), epsg=3004, rgb=True)
            f = stem + ".tif"
        else:
            im.save(stem + ".jpg", quality=88)
            # the world file: A D B E C F, C/F the CENTRE of the top-left pixel
            open(stem + ".jgw", "w").write("\n".join(f"{v:.6f}" for v in
                                                     (px, 0.0, 0.0, -px, x0 + px / 2, y_top - px / 2)) + "\n")
            open(stem + ".prj", "w").write(_prj(3004, "Monte_Mario_Italy_2"))
            f = stem + ".jpg"
        truth["sheets"][os.path.basename(f)] = {"crs": "EPSG:3004",
                                                "bbox": [x0, y_top - H * px, x0 + W * px, y_top]}
    # the orthophoto in 32633
    from PIL import Image, ImageDraw
    ow = 256
    im = Image.new("RGB", (ow, ow), (90, 120, 70))
    d = ImageDraw.Draw(im)
    for r in range(10, 128, 12):
        d.ellipse([128 - r, 128 - r, 128 + r, 128 + r], outline=(140 + r % 60, 150, 90))
    d.rectangle([110, 110, 146, 140], fill=(200, 190, 170))
    d.text((6, 6), "ORTOFOTO 2024 (sintetica)", fill=(255, 255, 255))
    ox0, oy0 = round(uE - 256.0), round(uN + 256.0)
    write_geotiff(os.path.join(gis, "ortofoto", "ortofoto_2024.tif"), _rows(im),
                  affine=(ox0, 2.0, 0.0, oy0, 0.0, -2.0), epsg=32633, rgb=True)
    truth["ortofoto"] = {"crs": "EPSG:32633", "bbox": [ox0, oy0 - 512, ox0 + 512, oy0]}
    # contour lines in 32633: rings every 5 m (a hill of 40 m at the centre)
    lines, vals = [], []
    for k, r in enumerate(range(30, 231, 40)):
        ring = [(uE + r * math.cos(t / 36 * 2 * math.pi), uN + 0.8 * r * math.sin(t / 36 * 2 * math.pi)) for t in range(37)]
        lines.append(ring)
        vals.append(40.0 - 5.0 * k)
    _shp_lines(os.path.join(gis, "curve", "curve_livello"), lines, vals, 32633, "WGS_84_UTM_zone_33N")
    truth["curve"] = {"crs": "EPSG:32633", "rings": len(lines)}
    # the DXF: a building of 24 × 14 m at the centre, its axes, three texts — minus the shift
    sx, sy, _ = DXF_SHIFT
    cx, cy = uE - sx, uN - sy
    room = [(cx - 12, cy - 7), (cx + 12, cy - 7), (cx + 12, cy + 7), (cx - 12, cy + 7)]
    inner = [(cx - 4, cy - 7), (cx - 4, cy + 7)]
    _dxf(os.path.join(gis, "dxf", "rilievo_cad.dxf"),
         [("MURI", room, True), ("MURI", inner, False)],
         [("ASSI", ((cx - 16, cy), (cx + 16, cy))), ("ASSI", ((cx, cy - 10), (cx, cy + 10)))],
         [("TESTI", (cx - 10, cy + 2), "Ambiente A"), ("TESTI", (cx + 2, cy + 2), "Ambiente B"),
          ("TESTI", (cx - 12, cy - 10), "Rilievo CAD sintetico")])
    truth["dxf"] = {"crs": None, "proposed_crs": "EPSG:32633", "shift": list(DXF_SHIFT),
                    "local_centre": [cx, cy]}
    # the graph: minimal, in 32633, shift on the site
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.geo_position_node import GeoPositionNode
    from s3dgraphy.nodes.epoch_node import EpochNode
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    g = Graph("gis-sintetico")
    g.name = "GIS sintetico"
    gs = round(uE / 100) * 100, round(uN / 100) * 100
    gp = next((n for n in g.nodes if n.node_type == "geo_position"), None)
    if gp is None:
        gp = GeoPositionNode("geo")
        g.add_node(gp)
    gp.data.update({"epsg": 32633, "shift_x": gs[0], "shift_y": gs[1], "shift_z": 0})
    g.add_node(EpochNode("ep_rom", "Età romana", start_time=-273, end_time=476))
    g.add_node(StratigraphicUnit("US1", "US1", description="un'unità di prova"))
    g.add_edge("us1_ep", "US1", "ep_rom", "has_first_epoch")
    truth["graph"] = {"crs": "EPSG:32633", "shift": [gs[0], gs[1], 0]}
    doc = build_emjson(g)
    with open(os.path.join(root, "EM", "gis_sintetico.em.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(root, "truth.json"), "w", encoding="utf-8") as fh:
        json.dump(truth, fh, indent=1)
    return truth


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                                               "_datasets", "gis-sintetici")
    t = make(os.path.abspath(out))
    print(json.dumps(t, indent=1))
