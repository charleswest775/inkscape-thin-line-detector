#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Copy the Thin Line Detector extension into Inkscape's per-user folder.

Usage:
    python3 install.py            # install (copy files)
    python3 install.py --uninstall
    python3 install.py --path     # just print the target folder

Works on Windows, macOS and Linux. No third-party dependencies.
"""

import argparse
import os
import pathlib
import shutil
import sys

FILES = ("thin_line_detector.py", "thin_line_detector.inx")


def candidate_dirs():
    """User extension dirs to try, most-preferred first."""
    home = pathlib.Path.home()
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = pathlib.Path(appdata) if appdata else home / "AppData" / "Roaming"
        return [base / "inkscape" / "extensions"]
    if sys.platform == "darwin":
        return [
            home / "Library/Application Support/org.inkscape.Inkscape"
            "/config/inkscape/extensions",
            home / ".config" / "inkscape" / "extensions",
        ]
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = pathlib.Path(xdg) if xdg else home / ".config"
    return [base / "inkscape" / "extensions"]


def target_dir():
    """Pick an existing extensions dir, else the preferred default."""
    options = candidate_dirs()
    for path in options:
        if path.exists():
            return path
    return options[0]


def main():
    parser = argparse.ArgumentParser(
        description="Install the Thin Line Detector Inkscape extension."
    )
    parser.add_argument("--uninstall", action="store_true", help="remove installed files")
    parser.add_argument("--path", action="store_true", help="print the target folder and exit")
    args = parser.parse_args()

    dest = target_dir()
    if args.path:
        print(dest)
        return

    src = pathlib.Path(__file__).resolve().parent

    if args.uninstall:
        removed = 0
        for name in FILES:
            target = dest / name
            if target.exists():
                target.unlink()
                removed += 1
                print("removed {}".format(target))
        print("Uninstalled ({} file(s)).".format(removed) if removed
              else "Nothing to uninstall in {}".format(dest))
        return

    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        source = src / name
        if not source.exists():
            sys.exit("error: {} not found next to install.py".format(name))
        shutil.copy2(source, dest / name)
        print("installed {}".format(dest / name))
    print("\nDone. Restart Inkscape, then use Extensions > Cleanup > "
          "Thin Line Detector.")


if __name__ == "__main__":
    main()
