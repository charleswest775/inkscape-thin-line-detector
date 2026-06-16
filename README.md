# Thin Line Detector — Inkscape Thin-Feature Finder

Find the parts of an SVG that are too thin to survive cutting, plotting or
printing — either **thin filled slivers** (narrow ribbons in filled artwork) or
**hairline strokes** (sub-pixel pen lines). Set a width **threshold**; every
feature that thin **or thinner** is highlighted, deleted, or (for strokes)
thickened to a safe minimum.

Works on **Windows, macOS and Linux** (Inkscape 1.0+). Pure Python, no
third-party dependencies — it only uses Inkscape's bundled `inkex`.

## Why

Traced, laser, stencil and mandala art is almost always built from **filled
shapes**, not pen strokes — usually a single compound path with hundreds of
subpaths. The fragile parts are thin *slivers*: narrow filled ribbons that snap
when cut or won't hold up on a lantern. They're invisible to a stroke-width
checker (there's no stroke to measure) and hard to spot by eye in a busy design.

Other files *are* stroke-based, where the trap is the opposite: a hairline
`0.05 mm` stroke that won't cut, or a "normal" `1 px` stroke sitting inside a
group scaled to 10 % — really `0.1 px`. Thin Line Detector measures whichever
applies and lets you find and fix it in one pass, with a live-updating preview.

## Install

### Option A — installer script (recommended)

```bash
python3 install.py        # copies the two files into your Inkscape folder
```

Then restart Inkscape. To remove it later: `python3 install.py --uninstall`.
To just see where it installs: `python3 install.py --path`.

### Option B — manual

Copy `thin_line_detector.py` and `thin_line_detector.inx` into your Inkscape
**user extensions** folder, then restart Inkscape:

| OS      | Folder |
|---------|--------|
| Windows | `%APPDATA%\inkscape\extensions\` |
| macOS   | `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/` (older builds: `~/.config/inkscape/extensions/`) |
| Linux   | `~/.config/inkscape/extensions/` |

The exact path is also shown in Inkscape under
**Edit ▸ Preferences ▸ System ▸ User extensions**.

## Use it

Open **Extensions ▸ Cleanup ▸ Thin Line Detector**.

1. Set **Detect thin** to **Filled shapes** (the default — for traced/laser/
   stencil/mandala art) or **Stroke width** (for stroke-based drawings).
2. Tick the **Live preview** checkbox at the bottom of the dialog.
3. Leave **Action** on *Highlight* and drag the **Threshold** slider — matching
   features light up on the canvas in real time so you can dial in the cutoff.
4. Switch **Action** to *Delete* (or *Thicken*, in stroke mode) and click
   **Apply**.

`Ctrl+Z` undoes any applied change, so it is safe to experiment. (Inkscape
effect extensions cannot hand a selection back to the canvas, so *Highlight* —
not a "select" mode — is the review step.)

### Threshold and units

The threshold can be entered in **px** (user units), **mm**, **pt** or **in**;
it is converted to the document's user units before comparing, so picking `mm`
lets you work directly in your machine's minimum feature size. A feature matches
when its measured width is **at or below** the threshold.

### Detect thin → Filled shapes (default)

Measures the **thickness of each filled shape**, computed per subpath as
`2 × area ÷ perimeter` — the width of an equivalent ribbon. Because it's based on
area and perimeter (not the bounding box), it is **rotation-invariant**: a thin
sliver is caught at any angle, and the hundreds of subpaths inside a single
compound path are each measured individually. Only filled shapes (`fill` is not
`none`) are considered.

- **Highlight** adds a `thin-line-preview` overlay that outlines the matching
  slivers in the highlight colour, using a *non-scaling* 2 px stroke so even
  hairline slivers stay visible no matter how far you zoom out.
- **Delete** rebuilds each compound path keeping only the subpaths above the
  threshold (a lone thin shape is removed outright).

### Detect thin → Stroke width

Measures the **rendered stroke width**:

1. **Resolve `stroke-width` through inheritance** — a width set on a parent
   `<g>` is picked up by its children.
2. **Convert to user units** — values with their own unit (`0.1mm`, `2pt`) are
   converted; bare numbers are user units already.
3. **Apply transform scale** — `sqrt(|det|)` of the object's composed
   transform, so a `2 px` stroke inside `scale(0.1)` is measured as `0.2 px`.

`vector-effect:non-scaling-stroke` skips step 3; `stroke:none` (the SVG default)
has no line and is ignored; percentage widths are skipped.

### Actions

| Action | Filled shapes | Stroke width |
|--------|---------------|--------------|
| **Highlight** | Outlines thin slivers in an overlay (non-destructive) | Recolors thin strokes (non-destructive) |
| **Thicken** | — (falls back to Highlight) | Raises each thin stroke to render at the threshold |
| **Delete** | Drops thin subpaths, keeps the rest | Removes thin-stroked elements |

**Scope** can be limited to the current selection instead of the whole document.

> To clean up tiny *whole objects* (specks, dots, short segments) rather than
> thin *features*, see the companion
> [inkscape-despeckle](https://github.com/charleswest775/inkscape-despeckle).

## Development

```bash
python3 -m pip install --no-deps "inkex==1.4.1"
python3 -m pip install lxml cssselect numpy tinycss2 pytest
python3 -m pytest
```

CI runs the test suite on Linux, macOS and Windows across Python 3.9–3.12.

## License

[GPL-2.0-or-later](LICENSE), matching the Inkscape `inkex` library this
extension builds on.
