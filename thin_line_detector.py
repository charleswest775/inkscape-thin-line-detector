#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Thin Line Detector: find hairline strokes OR thin filled slivers in Inkscape.

There are two things people mean by "thin line", chosen with ``--measure``:

* **fill** (default) -- the *thickness of a filled shape*. Traced / laser /
  stencil / mandala art is usually filled regions, not pen strokes, and is
  often a single compound path with hundreds of subpaths. Each subpath is
  measured individually, so a long thin sliver is flagged even though the whole
  path's bounding box is large. Thickness is estimated as
  ``2 * area / perimeter`` -- the width of an equivalent ribbon -- which is
  rotation-invariant, so it catches slivers at any angle, not just axis-aligned
  ones. Only filled shapes (``fill`` is not ``none``) are considered.

* **stroke** -- the *width of a drawn stroke*. ``stroke-width`` is resolved
  through CSS inheritance, converted to user units, then scaled by the
  element's composed transform (a 2px stroke inside ``scale(0.1)`` is 0.2px).
  ``vector-effect:non-scaling-stroke`` is respected. Elements with
  ``stroke:none`` (the SVG default) have no line and are skipped.

An element/subpath "matches" when its measured size is at or below the
threshold. The threshold may be given in px, mm, pt or in, and is converted to
user units against the document so the comparison is always like-for-like.

Actions (``--mode``):

* **highlight** -- non-destructive review. Stroke mode recolors matching
  strokes; fill mode adds a ``thin-line-preview`` overlay outlining the thin
  slivers in the highlight colour (a non-scaling 2px outline, so even hairline
  slivers stay visible at any zoom).
* **thicken** -- stroke mode only: raise each matching stroke so it *renders*
  at the threshold width. In fill mode there is no meaningful "thicken", so it
  falls back to a highlight preview.
* **delete** -- remove matches. In fill mode the compound path is rebuilt
  without the thin subpaths (a lone thin shape is removed outright).

All sizes are in SVG user units (px in a typical document).
"""

import inkex
from inkex import CubicSuperPath

# Stroked / filled leaf shapes we measure. Containers (Group, Layer) are walked
# into but never measured themselves; text is excluded.
SHAPE_TYPES = (
    inkex.PathElement,
    inkex.Rectangle,
    inkex.Circle,
    inkex.Ellipse,
    inkex.Line,
    inkex.Polyline,
    inkex.Polygon,
)

# Highlight overlays we create get this id prefix, so re-running the effect
# never measures its own preview.
PREVIEW_PREFIX = "thin-line-preview"


class ThinLineDetector(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="options")
        pars.add_argument("--measure", default="fill", help="fill | stroke")
        pars.add_argument("--threshold", type=float, default=1.0)
        pars.add_argument("--unit", default="px", help="px | mm | pt | in")
        pars.add_argument(
            "--mode", default="highlight",
            help="highlight | thicken | delete",
        )
        pars.add_argument("--scope", default="all", help="all | selection")
        pars.add_argument("--highlight_color", default="#ff0000")

    # --- traversal ----------------------------------------------------------

    def _candidates(self):
        if self.options.scope == "selection" and len(self.svg.selection):
            roots = list(self.svg.selection.values())
        else:
            roots = [self.svg]
        seen = set()
        for root in roots:
            for elem in root.iter():
                key = id(elem)
                if key in seen:
                    continue
                seen.add(key)
                if str(elem.get("id") or "").startswith(PREVIEW_PREFIX):
                    continue  # never re-measure our own highlight overlay
                yield elem

    def effect(self):
        threshold = self._threshold_uu()
        if self.options.measure == "stroke":
            self._effect_stroke(threshold)
        else:
            self._effect_fill(threshold)

    # ======================================================================
    # Shared style resolution
    # ======================================================================

    @staticmethod
    def _own_prop(node, name):
        """A style property set directly on ``node`` -- the inline ``style``
        wins over the matching presentation attribute -- or None."""
        style = getattr(node, "style", None)
        if style is not None:
            try:
                val = style.get(name)
            except Exception:
                val = None
            if val is not None:
                return val
        return node.get(name)

    def _cascaded(self, elem, name):
        """Resolve an inherited style property by walking up the ancestors.

        ``stroke``, ``stroke-width``, ``fill`` and ``vector-effect`` are all
        inherited in SVG, so the nearest ancestor that sets one supplies it when
        a child does not. This mirrors what newer inkex exposes as
        ``specified_style`` but works all the way back to the inkex bundled with
        Inkscape 1.0. (Class selectors in a ``<style>`` block are not resolved
        -- inline styles and presentation attributes, which Inkscape itself
        writes, are.)
        """
        node = elem
        while node is not None:
            val = self._own_prop(node, name)
            if val is not None and str(val).strip().lower() != "inherit":
                return val
            node = node.getparent()
        return None

    # ======================================================================
    # Stroke-width mode
    # ======================================================================

    @staticmethod
    def _transform_scale(elem):
        """Uniform scale factor the element's composed transform applies.

        ``sqrt(|det|)`` of the transform's 2x2 linear part -- the standard
        scalar by which a stroke's width grows under that transform. Falls back
        to 1.0 if the transform is missing, degenerate, or unreadable.
        """
        try:
            tr = elem.composed_transform()
            det = tr.a * tr.d - tr.b * tr.c
            scale = abs(det) ** 0.5
            return scale if scale > 0 else 1.0
        except Exception:
            return 1.0

    def _is_nonscaling(self, elem):
        """True when the stroke opts out of transform scaling."""
        ve = self._cascaded(elem, "vector-effect") or ""
        return "non-scaling-stroke" in str(ve)

    def rendered_width(self, elem):
        """Element's rendered stroke width in user units, or None if it has no
        stroke. Accounts for inherited styles, transform scale, and
        non-scaling-stroke."""
        stroke = self._cascaded(elem, "stroke")
        if stroke is None or str(stroke).strip().lower() in ("", "none"):
            return None  # no stroke -> not a line

        raw = self._cascaded(elem, "stroke-width")
        if raw is None:
            raw = "1"  # SVG default stroke-width when a stroke is present
        raw = str(raw).strip()
        if raw.endswith("%"):
            return None  # percentage widths are viewport-relative; skip

        try:
            nominal = self.svg.unittouu(raw)
        except Exception:
            try:
                nominal = float(raw)
            except (TypeError, ValueError):
                return None

        if self._is_nonscaling(elem):
            return nominal
        return nominal * self._transform_scale(elem)

    def _effect_stroke(self, threshold):
        mode = self.options.mode
        matched = []
        for elem in self._candidates():
            if not isinstance(elem, SHAPE_TYPES):
                continue
            width = self.rendered_width(elem)
            if width is not None and width <= threshold:
                matched.append(elem)

        if mode == "delete":
            for elem in matched:
                try:
                    elem.delete()
                except Exception:
                    pass  # already detached (e.g. parent removed first)
        elif mode == "thicken":
            self._thicken(matched, threshold)
        else:
            self._highlight_strokes(matched)

    def _thicken(self, matched, threshold):
        """Raise each match so its stroke *renders* at the threshold width.

        The style holds the local width, which the element's transform then
        scales; to land on the threshold after scaling we store
        ``threshold / scale``. Matches were selected as <= threshold, so this
        only ever raises a width, never lowers a thick line.
        """
        for elem in matched:
            scale = (1.0 if self._is_nonscaling(elem)
                     else self._transform_scale(elem))
            local = threshold / scale if scale > 0 else threshold
            elem.style["stroke-width"] = self._fmt(local)

    def _highlight_strokes(self, matched):
        color = self.options.highlight_color
        for elem in matched:
            elem.style["stroke"] = color
            elem.style["stroke-opacity"] = "1"
            elem.style["opacity"] = "1"

    # ======================================================================
    # Filled-thickness mode
    # ======================================================================

    def _is_filled(self, elem):
        """True when the element paints a fill (so it has area to measure)."""
        fill = self._cascaded(elem, "fill")
        if fill is None:
            return True  # SVG default fill is solid black
        return str(fill).strip().lower() != "none"

    def _effect_fill(self, threshold):
        mode = self.options.mode
        overlay_subs = []  # document-coord subpaths to preview (highlight)

        for elem in self._candidates():
            if not isinstance(elem, SHAPE_TYPES) or not self._is_filled(elem):
                continue
            try:
                local_csp = elem.path.to_superpath()
                doc_csp = elem.path.transform(
                    elem.composed_transform()).to_superpath()
            except Exception:
                continue
            if (local_csp is None or len(local_csp) == 0
                    or len(doc_csp) != len(local_csp)):
                continue

            keep, drop_doc = [], []
            for i, sub in enumerate(doc_csp):
                thickness = self._subpath_thickness(sub)
                if thickness is not None and thickness <= threshold:
                    drop_doc.append(sub)
                else:
                    keep.append(local_csp[i])
            if not drop_doc:
                continue

            if mode == "delete":
                if not keep:
                    try:
                        elem.delete()
                    except Exception:
                        pass
                elif isinstance(elem, inkex.PathElement):
                    elem.path = CubicSuperPath(keep).to_path()
                # else: a non-path shape is single-subpath, so partial keep
                # cannot happen; nothing to do.
            else:  # highlight, or thicken (no fill equivalent -> preview)
                overlay_subs.extend(drop_doc)

        if overlay_subs:
            self._add_overlay(overlay_subs)

    def _add_overlay(self, overlay_subs):
        """Add a preview path outlining the thin subpaths in the highlight
        colour. The outline uses a non-scaling 2px stroke so that even hairline
        slivers stay visible no matter how far the view is zoomed out."""
        color = self.options.highlight_color
        overlay = inkex.PathElement()
        overlay.path = CubicSuperPath(overlay_subs).to_path()
        overlay.set("id", self.svg.get_unique_id(PREVIEW_PREFIX))
        overlay.style = inkex.Style({
            "fill": color,
            "fill-opacity": "0.6",
            "stroke": color,
            "stroke-width": "2",
            "stroke-opacity": "1",
            "vector-effect": "non-scaling-stroke",
        })
        self.svg.add(overlay)

    # --- subpath geometry ---------------------------------------------------

    @staticmethod
    def _flatten_sub(sub, steps=8):
        """One cubic-superpath subpath -> list of (x, y) sample points."""
        pts = []
        for i, node in enumerate(sub):
            if i == 0:
                pts.append((node[1][0], node[1][1]))
                continue
            p0, p1 = sub[i - 1][1], sub[i - 1][2]
            p2, p3 = node[0], node[1]
            for s in range(1, steps + 1):
                t = s / steps
                mt = 1.0 - t
                a = mt * mt * mt
                b = 3 * mt * mt * t
                c = 3 * mt * t * t
                d = t * t * t
                pts.append((
                    a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
                ))
        return pts

    @staticmethod
    def _poly_area(pts):
        """Shoelace area of a flattened subpath (deterministic, no numpy)."""
        total = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            total += x0 * y1 - x1 * y0
        return abs(total) * 0.5

    @staticmethod
    def _poly_perimeter(pts):
        """Closed-loop perimeter of a flattened subpath."""
        total = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        return total

    def _subpath_thickness(self, sub):
        """Effective width of a filled subpath: ``2 * area / perimeter``.

        For a long thin ribbon of width w this tends to w; it is
        rotation-invariant (area and perimeter are preserved by rotation), so a
        sliver is caught at any angle. A zero-area (collapsed/open) subpath
        reports 0 -- the thinnest possible feature. Returns None for a subpath
        with too few points to form a region.
        """
        pts = self._flatten_sub(sub)
        if len(pts) < 3:
            return None
        perimeter = self._poly_perimeter(pts)
        if perimeter <= 0:
            return None
        return 2.0 * self._poly_area(pts) / perimeter

    # --- shared helpers -----------------------------------------------------

    def _threshold_uu(self):
        """The threshold (in the chosen unit) expressed in user units."""
        spec = "{}{}".format(self.options.threshold, self.options.unit)
        try:
            return self.svg.unittouu(spec)
        except Exception:
            return float(self.options.threshold)

    @staticmethod
    def _fmt(value):
        """Compact numeric string (no trailing zeros) for a style value."""
        return "{:.6f}".format(value).rstrip("0").rstrip(".") or "0"


if __name__ == "__main__":
    ThinLineDetector().run()
