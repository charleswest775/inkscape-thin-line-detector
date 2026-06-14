# Thin Line Detector — Inkscape Hairline Stroke Finder

Find the strokes in an SVG that are too thin: sub-pixel hairlines, lines below
your laser/plotter/print minimum, and strokes that all but vanish once their
parent group is scaled down. Set a width **threshold**; every stroke that width
**or thinner** is highlighted, thickened to a safe minimum, or deleted.

Works on **Windows, macOS and Linux** (Inkscape 1.0+). Pure Python, no
third-party dependencies — it only uses Inkscape's bundled `inkex`.

## Why

Hairline strokes are a classic production trap. A 0.05 mm line looks fine on
screen but won't cut on a laser, won't plot on a pen plotter, and drops out or
renders inconsistently in print. Worse, a "normal" 1 px stroke inside a group
that's been scaled to 10 % is really a 0.1 px stroke — invisible to the eye but
still in the file. Thin Line Detector measures the **rendered** width of every
stroke so you can find and fix these in one pass, with a live-updating preview.

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

1. Tick the **Live preview** checkbox at the bottom of the dialog.
2. Leave **Action** on *Highlight* and drag the **Threshold** slider — matching
   strokes recolor on the canvas in real time so you can dial in the cutoff.
3. Switch **Action** to *Thicken* (raise hairlines to a safe minimum width) or
   *Delete*, then click **Apply**.

`Ctrl+Z` undoes any applied change, so it is safe to experiment. (Inkscape
effect extensions cannot hand a selection back to the canvas, so *Highlight* —
not a "select" mode — is the review step.)

### Threshold and units

The threshold can be entered in **px** (user units), **mm**, **pt** or **in**;
it is converted to the document's user units before comparing, so picking `mm`
lets you work directly in your machine's minimum line width. A stroke matches
when its rendered width is **at or below** the threshold.

### Actions

| Action | What it does | Good for |
|--------|--------------|----------|
| **Highlight** (default) | Recolors matching strokes (non-destructive) | Reviewing what counts as "too thin" with Live preview |
| **Thicken** | Raises each matching stroke so it *renders* at exactly the threshold width | Enforcing a minimum line width for laser/plotter/print |
| **Delete** | Removes matching elements | Stripping stray hairline debris |

### How width is measured

For each stroked object the rendered width is computed as:

1. **Resolve `stroke-width` through inheritance** — a width set on a parent
   `<g>` is picked up by its children (via `inkex`'s cascaded style).
2. **Convert to user units** — values carrying their own unit (`0.1mm`, `2pt`)
   are converted; bare numbers are user units already.
3. **Apply transform scale** — the object's composed transform can shrink or
   grow the stroke. The scale factor is `sqrt(|det|)` of the transform's linear
   part, so a `2 px` stroke inside `scale(0.1)` is measured as `0.2 px`.

Objects flagged `vector-effect:non-scaling-stroke` skip step 3 — their stroke
keeps its nominal width because transforms don't scale it. Objects with
`stroke:none` (the SVG default) have no line and are always ignored. Percentage
stroke widths are skipped. **Scope** can be limited to the current selection
instead of the whole document.

> Stroke width is a single property shared by every subpath of a path, so
> compound/traced paths need no special handling here. To clean up tiny
> *shapes* (specks, slivers, short segments) rather than thin *strokes*, see the
> companion [inkscape-despeckle](https://github.com/charleswest775/inkscape-despeckle)
> extension.

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
