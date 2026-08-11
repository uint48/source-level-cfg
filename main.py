#!/usr/bin/env python3
"""Source-level CFG generator for Java.

Usage:
    python main.py javasamples/Example1.java
    python main.py javasamples/ --out output --format svg
    python main.py javasamples/ --check

Run with --help for the full option list.
"""

import argparse
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from slcfg.astbuilder import build_ast
from slcfg.cfg import build_cfgs
from slcfg.errors import Diagnostics
from slcfg.parse import parse_file
from slcfg.render import assign_filenames, draw_cfg, dump_json
from slcfg.verify import check_cfg


class FileResult:
    """What happened to one input file."""

    def __init__(self, path):
        self.path = path
        self.methods = 0
        self.warnings = []
        self.violations = []
        self.error = None
        self.outputs = []

    @property
    def ok(self):
        return self.error is None and not self.violations


def analyze(java_path, options):
    """Parse, build, verify, and (unless suppressed) write output for one file."""
    result = FileResult(java_path)
    diagnostics = Diagnostics(
        filename=str(java_path), strict=options.strict, quiet=options.quiet
    )
    try:
        ast = build_ast(parse_file(str(java_path)), diagnostics)
        cfgs = build_cfgs(ast, diagnostics)
        result.methods = len(cfgs)
        result.warnings = diagnostics.warnings

        for cfg in cfgs:
            result.violations.extend(
                str(v) for v in check_cfg(cfg, allow_infinite_loops=True)
            )

        if options.check:
            return result

        out_dir = _output_dir(java_path, options)
        names = assign_filenames(cfgs)
        for cfg in cfgs:
            basename = names[id(cfg)]
            if options.json:
                result.outputs.append(
                    dump_json(cfg, out_dir, basename, source=str(java_path))
                )
            if options.render:
                result.outputs.append(
                    draw_cfg(cfg, out_dir, basename, fmt=options.format)
                )
    except Exception as exc:  # one bad file must not abort a directory run
        result.error = f"{type(exc).__name__}: {exc}"
        if options.traceback:
            traceback.print_exc()
    return result


def _output_dir(java_path, options):
    """Mirror the input tree under --out, one directory per source file."""
    if options.root is None:
        return os.path.join(options.out, Path(java_path).stem)
    relative = Path(java_path).relative_to(options.root)
    return os.path.join(options.out, str(relative.parent), Path(java_path).stem)


def java_files(target):
    path = Path(target)
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.java"))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Generate a source-level control-flow graph for each Java method.",
    )
    parser.add_argument("path", help="a .java file, or a directory to walk recursively")
    parser.add_argument(
        "--out", default="output", metavar="DIR", help="output directory (default: output)"
    )
    parser.add_argument(
        "--format",
        default="pdf",
        choices=["pdf", "png", "jpg", "svg", "dot"],
        help=(
            "figure format. All but 'dot' (which writes Graphviz source) need the "
            "Graphviz `dot` binary on PATH"
        ),
    )
    parser.add_argument(
        "--no-json", dest="json", action="store_false", help="skip the JSON output"
    )
    parser.add_argument(
        "--no-render", dest="render", action="store_false", help="skip the figures"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify CFG invariants and write nothing; exit non-zero on violations",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on an unsupported construct instead of warning",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="process N files in parallel (default: 1)",
    )
    parser.add_argument("--quiet", action="store_true", help="only report problems")
    parser.add_argument(
        "--traceback", action="store_true", help="print a traceback on failure"
    )
    return parser


def main(argv=None):
    options = build_parser().parse_args(argv)

    target = Path(options.path)
    if not target.exists():
        print(f"error: no such file or directory: {target}", file=sys.stderr)
        return 2

    files = java_files(target)
    if not files:
        print(f"error: no .java files found under {target}", file=sys.stderr)
        return 2

    options.root = target if target.is_dir() else None

    if options.jobs > 1 and len(files) > 1:
        with ProcessPoolExecutor(max_workers=options.jobs) as pool:
            results = list(pool.map(analyze, files, [options] * len(files)))
    else:
        results = [analyze(path, options) for path in files]

    return _report(results, options)


def _report(results, options):
    failures = [r for r in results if r.error]
    violations = [r for r in results if r.violations]
    total_methods = sum(r.methods for r in results)
    total_warnings = sum(len(r.warnings) for r in results)

    for result in results:
        if result.error:
            print(f"ERROR   {result.path}: {result.error}", file=sys.stderr)
            continue
        for violation in result.violations:
            print(f"INVALID {result.path}: {violation}", file=sys.stderr)
        if not options.quiet and not result.violations:
            action = "checked" if options.check else "wrote"
            print(f"ok      {result.path}: {result.methods} method(s) {action}")

    if not options.quiet:
        print(
            f"\n{len(results)} file(s), {total_methods} method(s), "
            f"{total_warnings} warning(s), {len(violations)} with violations, "
            f"{len(failures)} failed"
        )

    return 1 if failures or violations else 0


if __name__ == "__main__":
    sys.exit(main())
