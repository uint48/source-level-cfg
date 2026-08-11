#!/usr/bin/env python3
"""Regenerate the figures under docs/ for every sample.

Requires the Graphviz `dot` binary on PATH (the Python `graphviz` package only
shells out to it):

    sudo apt install graphviz     # Debian/Ubuntu
    brew install graphviz         # macOS

    python tools/render_docs.py                    # JPG + PDF, as the README uses
    python tools/render_docs.py --format png
    python tools/render_docs.py --clean            # remove stale figures first

One figure per method, named `<Class>.<method>.<ext>`. The README embeds the
raster image and links the PDF alongside it.
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slcfg.astbuilder import build_ast  # noqa: E402
from slcfg.cfg import build_cfgs  # noqa: E402
from slcfg.errors import Diagnostics  # noqa: E402
from slcfg.parse import parse_file  # noqa: E402
from slcfg.render import assign_filenames, draw_cfg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "javasamples"
DOCS = ROOT / "docs"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        nargs="+",
        default=["jpg", "pdf"],
        choices=["svg", "pdf", "png", "jpg"],
        metavar="FMT",
        help="one or more formats to render (default: jpg pdf)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="delete existing figures in docs/ before rendering",
    )
    options = parser.parse_args(argv)

    if shutil.which("dot") is None:
        print(
            "error: the Graphviz 'dot' binary is not on PATH.\n"
            "       install it (e.g. `sudo apt install graphviz`) and retry.",
            file=sys.stderr,
        )
        return 2

    DOCS.mkdir(exist_ok=True)
    if options.clean:
        for pattern in ("*.svg", "*.pdf", "*.png", "*.jpg"):
            for stale in DOCS.glob(pattern):
                stale.unlink()

    total = 0
    for java_path in sorted(SAMPLES.glob("*.java")):
        diagnostics = Diagnostics(filename=str(java_path), quiet=True)
        cfgs = build_cfgs(build_ast(parse_file(str(java_path)), diagnostics), diagnostics)
        names = assign_filenames(cfgs)
        for cfg in cfgs:
            for fmt in options.format:
                draw_cfg(cfg, str(DOCS), names[id(cfg)], fmt=fmt)
            total += 1
        print(f"{java_path.name}: {len(cfgs)} method(s)")

    print(
        f"\n{total} method(s) x {len(options.format)} format(s) "
        f"= {total * len(options.format)} file(s) written to {DOCS}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
