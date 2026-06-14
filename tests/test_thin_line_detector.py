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

# width == viewBox so 1 user unit == 1 px: stroke widths below are px.
SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <path id="hairline" d="M 0,0 L 100,0" style="stroke:#000000;stroke-width:0.1"/>
  <path id="thick" d="M 0,50 L 100,50" style="stroke:#000000;stroke-width:5"/>
  <path id="nostroke" d="M 0,100 L 100,100" style="fill:#000000"/>
  <rect id="thinrect" x="10" y="120" width="50" height="50"
        style="stroke:#000000;stroke-width:0.2;fill:none"/>
</svg>"""


def run_ext(tmp_path, args, svg=SVG):
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


# --- threshold matching + actions ---------------------------------------

def test_highlight_recolors_thin_only_and_deletes_nothing(tmp_path):
    result = run_ext(
        tmp_path,
        ["--mode=highlight", "--threshold=1", "--highlight_color=#ff0000"],
    )
    # Thin strokes recolored...
    assert "#ff0000" in _style_of(result, "hairline")
    assert "#ff0000" in _style_of(result, "thinrect")
    # ...thick stroke left alone...
    assert "#ff0000" not in _style_of(result, "thick")
    # ...and highlight is non-destructive: every object still present.
    for obj_id in ("hairline", "thick", "nostroke", "thinrect"):
        assert 'id="{}"'.format(obj_id) in result


def test_delete_removes_thin_keeps_thick_and_unstroked(tmp_path):
    result = run_ext(tmp_path, ["--mode=delete", "--threshold=1"])
    assert 'id="hairline"' not in result    # 0.1 px removed
    assert 'id="thinrect"' not in result    # 0.2 px removed
    assert 'id="thick"' in result           # 5 px kept
    assert 'id="nostroke"' in result        # no stroke -> not a line -> kept


def test_thicken_raises_thin_to_threshold_only(tmp_path):
    result = run_ext(tmp_path, ["--mode=thicken", "--threshold=1"])
    # No transform here, so local width == rendered width == threshold.
    assert _stroke_width(result, "hairline") == pytest.approx(1.0)
    assert _stroke_width(result, "thinrect") == pytest.approx(1.0)
    # Thick line is above threshold, so it is never touched.
    assert _stroke_width(result, "thick") == pytest.approx(5.0)


def test_nothing_matches_below_smallest_width(tmp_path):
    result = run_ext(tmp_path, ["--mode=delete", "--threshold=0.05"])
    for obj_id in ("hairline", "thick", "nostroke", "thinrect"):
        assert 'id="{}"'.format(obj_id) in result


# --- transform / vector-effect awareness --------------------------------

SCALED = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <g transform="scale(0.1)">
    <path id="scaled" d="M 0,0 L 100,0" style="stroke:#000000;stroke-width:2"/>
  </g>
  <path id="control" d="M 0,0 L 100,0" style="stroke:#000000;stroke-width:2"/>
</svg>"""


def test_transform_scale_is_applied_to_width(tmp_path):
    # 2 px under scale(0.1) renders at 0.2 px -> thin; the same 2 px stroke
    # without a transform renders at 2 px -> not thin.
    result = run_ext(tmp_path, ["--mode=delete", "--threshold=1"], svg=SCALED)
    assert 'id="scaled"' not in result
    assert 'id="control"' in result


NONSCALING = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <g transform="scale(10)">
    <path id="ns" d="M 0,0 L 10,0"
          style="stroke:#000000;stroke-width:0.5;vector-effect:non-scaling-stroke"/>
  </g>
</svg>"""


def test_non_scaling_stroke_keeps_nominal_width(tmp_path):
    # 0.5 px non-scaling under scale(10) stays 0.5 px (not 5 px), so it matches.
    result = run_ext(tmp_path, ["--mode=delete", "--threshold=1"], svg=NONSCALING)
    assert 'id="ns"' not in result


# --- inherited style ----------------------------------------------------

INHERITED = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <g style="stroke:#000000;stroke-width:0.1">
    <path id="inh" d="M 0,0 L 100,0"/>
  </g>
</svg>"""


def test_inherited_stroke_width_from_group(tmp_path):
    # The path has no own stroke-width; it inherits 0.1 px from its group.
    result = run_ext(tmp_path, ["--mode=delete", "--threshold=1"], svg=INHERITED)
    assert 'id="inh"' not in result


# --- unit conversion ----------------------------------------------------

UNITS = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <path id="w3" d="M 0,0 L 100,0" style="stroke:#000000;stroke-width:3"/>
  <path id="w5" d="M 0,50 L 100,50" style="stroke:#000000;stroke-width:5"/>
</svg>"""


def test_threshold_in_mm(tmp_path):
    # 1 mm == 96/25.4 == 3.7795 px: the 3 px stroke is thinner, the 5 px isn't.
    result = run_ext(
        tmp_path,
        ["--mode=delete", "--threshold=1", "--unit=mm"],
        svg=UNITS,
    )
    assert 'id="w3"' not in result
    assert 'id="w5"' in result


# --- scope --------------------------------------------------------------

def test_scope_selection_with_nothing_selected_falls_back(tmp_path):
    # No selection passed: scope=selection should fall back to whole document.
    result = run_ext(
        tmp_path, ["--mode=delete", "--threshold=1", "--scope=selection"]
    )
    assert 'id="hairline"' not in result
    assert 'id="thick"' in result
