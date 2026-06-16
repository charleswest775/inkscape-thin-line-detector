# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration tests: run the extension end-to-end via inkex and inspect SVG."""

import io
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from thin_line_detector import ThinLineDetector  # noqa: E402


def run_ext(tmp_path, args, svg):
    src = tmp_path / "in.svg"
    src.write_text(svg)
    out = io.BytesIO()
    try:
        ThinLineDetector().run(args + [str(src)], output=out)
    except SystemExit:
        pass
    data = out.getvalue().decode("utf-8")
    # inkex writes nothing when an effect changes nothing; Inkscape then leaves
    # the canvas as-is, so an empty result means "document unchanged".
    return data if data else svg


def _elem(svg_text, pid):
    root = ET.fromstring(svg_text)
    for e in root.iter():
        if e.get("id") == pid:
            return e
    return None


def _style_of(svg_text, pid):
    e = _elem(svg_text, pid)
    return "" if e is None else (e.get("style") or "")


def _stroke_width(svg_text, pid):
    """Resolved stroke-width of an element, from style or attribute."""
    e = _elem(svg_text, pid)
    if e is None:
        return None
    m = re.search(r"stroke-width\s*:\s*([0-9.eE+-]+)", e.get("style") or "")
    if m:
        return float(m.group(1))
    attr = e.get("stroke-width")
    return float(attr) if attr is not None else None


def _subpath_count(svg_text, pid):
    """Number of subpaths (M/m moveto commands) in a path's d attribute."""
    e = _elem(svg_text, pid)
    if e is None or e.tag.split("}")[-1] != "path":
        return None
    return len(re.findall(r"[Mm]", e.get("d") or ""))


# =====================================================================
# Stroke-width mode  (--measure=stroke)
# =====================================================================

# width == viewBox so 1 user unit == 1 px: stroke widths below are px.
STROKE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <path id="hairline" d="M 0,0 L 100,0" style="stroke:#000000;stroke-width:0.1"/>
  <path id="thick" d="M 0,50 L 100,50" style="stroke:#000000;stroke-width:5"/>
  <path id="nostroke" d="M 0,100 L 100,100" style="fill:#000000;stroke:none"/>
  <rect id="thinrect" x="10" y="120" width="50" height="50"
        style="stroke:#000000;stroke-width:0.2;fill:none"/>
</svg>"""


def run_stroke(tmp_path, args, svg=STROKE_SVG):
    return run_ext(tmp_path, ["--measure=stroke"] + args, svg)


def test_stroke_highlight_recolors_thin_only_and_deletes_nothing(tmp_path):
    result = run_stroke(
        tmp_path,
        ["--mode=highlight", "--threshold=1", "--highlight_color=#ff0000"],
    )
    assert "#ff0000" in _style_of(result, "hairline")
    assert "#ff0000" in _style_of(result, "thinrect")
    assert "#ff0000" not in _style_of(result, "thick")
    for obj_id in ("hairline", "thick", "nostroke", "thinrect"):
        assert 'id="{}"'.format(obj_id) in result


def test_stroke_delete_removes_thin_keeps_thick_and_unstroked(tmp_path):
    result = run_stroke(tmp_path, ["--mode=delete", "--threshold=1"])
    assert 'id="hairline"' not in result    # 0.1 px removed
    assert 'id="thinrect"' not in result    # 0.2 px removed
    assert 'id="thick"' in result           # 5 px kept
    assert 'id="nostroke"' in result        # no stroke -> not a line -> kept


def test_stroke_thicken_raises_thin_to_threshold_only(tmp_path):
    result = run_stroke(tmp_path, ["--mode=thicken", "--threshold=1"])
    assert _stroke_width(result, "hairline") == pytest.approx(1.0)
    assert _stroke_width(result, "thinrect") == pytest.approx(1.0)
    assert _stroke_width(result, "thick") == pytest.approx(5.0)


def test_stroke_nothing_matches_below_smallest_width(tmp_path):
    result = run_stroke(tmp_path, ["--mode=delete", "--threshold=0.05"])
    for obj_id in ("hairline", "thick", "nostroke", "thinrect"):
        assert 'id="{}"'.format(obj_id) in result


STROKE_SCALED = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <g transform="scale(0.1)">
    <path id="scaled" d="M 0,0 L 100,0" style="stroke:#000000;stroke-width:2"/>
  </g>
  <path id="control" d="M 0,0 L 100,0" style="stroke:#000000;stroke-width:2"/>
</svg>"""


def test_stroke_transform_scale_is_applied_to_width(tmp_path):
    result = run_stroke(
        tmp_path, ["--mode=delete", "--threshold=1"], svg=STROKE_SCALED
    )
    assert 'id="scaled"' not in result      # 2 px under scale(0.1) -> 0.2 px
    assert 'id="control"' in result         # 2 px, no transform -> kept


STROKE_NONSCALING = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <g transform="scale(10)">
    <path id="ns" d="M 0,0 L 10,0"
          style="stroke:#000000;stroke-width:0.5;vector-effect:non-scaling-stroke"/>
  </g>
</svg>"""


def test_stroke_non_scaling_stroke_keeps_nominal_width(tmp_path):
    result = run_stroke(
        tmp_path, ["--mode=delete", "--threshold=1"], svg=STROKE_NONSCALING
    )
    assert 'id="ns"' not in result          # stays 0.5 px (not 5 px) -> matches


STROKE_INHERITED = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <g style="stroke:#000000;stroke-width:0.1">
    <path id="inh" d="M 0,0 L 100,0"/>
  </g>
</svg>"""


def test_stroke_inherited_width_from_group(tmp_path):
    result = run_stroke(
        tmp_path, ["--mode=delete", "--threshold=1"], svg=STROKE_INHERITED
    )
    assert 'id="inh"' not in result         # inherits 0.1 px from its group


STROKE_UNITS = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <path id="w3" d="M 0,0 L 100,0" style="stroke:#000000;stroke-width:3"/>
  <path id="w5" d="M 0,50 L 100,50" style="stroke:#000000;stroke-width:5"/>
</svg>"""


def test_stroke_threshold_in_mm(tmp_path):
    # 1 mm == 96/25.4 == 3.7795 px: the 3 px stroke is thinner, the 5 px isn't.
    result = run_stroke(
        tmp_path, ["--mode=delete", "--threshold=1", "--unit=mm"], svg=STROKE_UNITS
    )
    assert 'id="w3"' not in result
    assert 'id="w5"' in result


def test_stroke_scope_selection_with_nothing_selected_falls_back(tmp_path):
    result = run_stroke(
        tmp_path, ["--mode=delete", "--threshold=1", "--scope=selection"]
    )
    assert 'id="hairline"' not in result
    assert 'id="thick"' in result


# =====================================================================
# Filled-thickness mode  (--measure=fill, the default)
# =====================================================================

# One path, two subpaths: a 40x40 square (thickness ~20) and a 2x40 sliver
# (thickness ~1.9, where thickness = 2*area/perimeter).
FILL_COMPOUND = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <path id="cmp" d="M 0,0 H 40 V 40 H 0 Z M 100,0 H 102 V 40 H 100 Z"
        fill="#000000"/>
</svg>"""


def test_fill_is_the_default_measure(tmp_path):
    # No --measure flag: should behave as fill mode and drop the thin subpath.
    result = run_ext(tmp_path, ["--mode=delete", "--threshold=5"], FILL_COMPOUND)
    assert 'id="cmp"' in result                  # path survives
    assert _subpath_count(result, "cmp") == 1    # 2 subpaths -> 1 (square kept)


def test_fill_delete_drops_thin_subpath_keeps_thick(tmp_path):
    result = run_ext(
        tmp_path, ["--measure=fill", "--mode=delete", "--threshold=5"], FILL_COMPOUND
    )
    assert _subpath_count(result, "cmp") == 1


def test_fill_highlight_overlays_without_touching_original(tmp_path):
    result = run_ext(
        tmp_path,
        ["--measure=fill", "--mode=highlight", "--threshold=5",
         "--highlight_color=#ff0000"],
        FILL_COMPOUND,
    )
    assert "thin-line-preview" in result          # overlay added
    assert "#ff0000" in result                    # in the highlight colour
    assert _subpath_count(result, "cmp") == 2     # original untouched


def test_fill_thicken_falls_back_to_highlight(tmp_path):
    result = run_ext(
        tmp_path,
        ["--measure=fill", "--mode=thicken", "--threshold=5"],
        FILL_COMPOUND,
    )
    assert "thin-line-preview" in result          # previewed, not modified
    assert _subpath_count(result, "cmp") == 2


FILL_SHAPES = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <rect id="thinbar" x="0" y="0" width="2" height="40" fill="#000000"/>
  <rect id="bigbox" x="100" y="0" width="40" height="40" fill="#000000"/>
  <path id="nofill" d="M 200,0 H 202 V 40 H 200 Z" style="fill:none"/>
</svg>"""


def test_fill_delete_single_thin_shape_keeps_thick_and_unfilled(tmp_path):
    result = run_ext(
        tmp_path, ["--measure=fill", "--mode=delete", "--threshold=5"], FILL_SHAPES
    )
    assert 'id="thinbar"' not in result   # 2x40 filled sliver removed
    assert 'id="bigbox"' in result        # 40x40 filled square kept
    assert 'id="nofill"' in result        # fill:none -> no area -> ignored


# A 2x40 sliver rotated 45 degrees: its axis-aligned bbox is ~30 px on a side,
# but 2*area/perimeter is rotation-invariant, so it is still ~1.9 px thick.
FILL_DIAGONAL = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <g transform="rotate(45 120 120)">
    <rect id="diag" x="120" y="120" width="2" height="40" fill="#000000"/>
  </g>
</svg>"""


def test_fill_detects_diagonal_sliver(tmp_path):
    result = run_ext(
        tmp_path, ["--measure=fill", "--mode=delete", "--threshold=5"], FILL_DIAGONAL
    )
    assert 'id="diag"' not in result      # caught despite its large bbox
