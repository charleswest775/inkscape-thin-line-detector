#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Thin Line Detector: find, highlight, thicken, or delete hairline strokes.

An element "matches" when its *rendered* stroke width is less than or equal to
the threshold. Rendered width is the ``stroke-width`` resolved through CSS
inheritance, converted to user units, then multiplied by the scale factor of
the element's composed transform -- so a 2px stroke inside a ``scale(0.1)``
group is correctly measured as 0.2px. Strokes flagged
``vector-effect:non-scaling-stroke`` keep their nominal width, because
transforms do not scale them.

The threshold may be given in px, mm, pt or inches; it is converted to user
units against the document so the comparison is always like-for-like.

Three actions:

* **highlight** -- recolor matching strokes so you can see them (non-destructive
  review; pair it with Inkscape's Live preview and drag the slider).
* **thicken** -- raise each matching stroke so it *renders* at exactly the
  threshold width: the minimum-line-width fix for laser / plotter / print prep.
* **delete** -- remove matching elements entirely.

Only stroked geometry is considered: an element with ``stroke:none`` (the SVG
default) has no line and is always skipped. Because stroke width is a single
property shared by every subpath of a path, compound paths need no special
per-subpath handling.

All widths are in SVG user units (px in a typical document).
"""

import inkex

# Stroked leaf shapes we measure. Containers (Group, Layer) are walked into but
# never measured themselves; text is excluded -- glyph outlines aren't "lines".
SHAPE_TYPES = (
    inkex.PathElement,
    inkex.Rectangle,
    inkex.Circle,
    inkex.Ellipse,
    inkex.Line,
    inkex.Polyline,
    inkex.Polygon,
)


class ThinLineDetector(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="options")
        pars.add_argument("--threshold", type=float, default=1.0)
        pars.add_argument("--unit", default="px", help="px | mm | pt | in")
        pars.add_argument(
            "--mode", default="highlight",
            help="highlight | thicken | delete",
        )
        pars.add_argument("--scope", default="all", help="all | selection")
        pars.add_argument("--highlight_color", default="#ff0000")

    # --- stroke-width measurement ------------------------------------------

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

        ``stroke``, ``stroke-width`` and ``vector-effect`` are all inherited in
        SVG, so the nearest ancestor that sets one supplies it when a child does
        not. This mirrors what newer inkex exposes as ``specified_style`` but
        works all the way back to the inkex bundled with Inkscape 1.0. (Class
        selectors in a ``<style>`` block are not resolved -- inline styles and
        presentation attributes, which Inkscape itself writes, are.)
        """
        node = elem
        while node is not None:
            val = self._own_prop(node, name)
            if val is not None and str(val).strip().lower() != "inherit":
                return val
            node = node.getparent()
        return None

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
                yield elem

    # --- main ---------------------------------------------------------------

    def effect(self):
        threshold = self._threshold_uu()
        mode = self.options.mode

        matched = []
        for elem in self._candidates():
            if not isinstance(elem, SHAPE_TYPES):
                continue
            width = self.rendered_width(elem)
            if width is not None and width <= threshold:
                matched.append(elem)

        if mode == "delete":
            self._delete(matched)
        elif mode == "thicken":
            self._thicken(matched, threshold)
        else:  # highlight
            self._highlight(matched)

    def _delete(self, matched):
        for elem in matched:
            try:
                elem.delete()
            except Exception:
                pass  # already detached (e.g. parent removed first)

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

    def _highlight(self, matched):
        color = self.options.highlight_color
        for elem in matched:
            elem.style["stroke"] = color
            elem.style["stroke-opacity"] = "1"
            elem.style["opacity"] = "1"

    # --- helpers ------------------------------------------------------------

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
