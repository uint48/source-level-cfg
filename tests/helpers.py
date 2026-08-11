"""Shared test plumbing."""

import json
from pathlib import Path

from slcfg.astbuilder import build_ast
from slcfg.cfg import build_cfgs
from slcfg.errors import Diagnostics
from slcfg.parse import parse_file
from slcfg.render import canonical_dict

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "javasamples"
GOLDEN = Path(__file__).resolve().parent / "golden"


def sample_paths():
    return sorted(SAMPLES.glob("*.java"))


def cfgs_for(java_path, strict=False):
    diagnostics = Diagnostics(filename=str(java_path), strict=strict, quiet=True)
    ast = build_ast(parse_file(str(java_path)), diagnostics)
    return build_cfgs(ast, diagnostics), diagnostics


def canonical_for(java_path):
    """The comparison form for one sample: one entry per method, in order."""
    cfgs, _ = cfgs_for(java_path)
    return [canonical_dict(cfg) for cfg in cfgs]


def golden_path(java_path):
    return GOLDEN / f"{Path(java_path).stem}.json"


def read_golden(java_path):
    return json.loads(golden_path(java_path).read_text(encoding="utf-8"))


def write_golden(java_path, data):
    GOLDEN.mkdir(parents=True, exist_ok=True)
    golden_path(java_path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def find_cfg(cfgs, method_name):
    for cfg in cfgs:
        if cfg.method.name == method_name:
            return cfg
    raise AssertionError(f"no method named {method_name!r} in {[c.method.name for c in cfgs]}")


def successors(cfg, block_id):
    """{successor: label} for one block."""
    return {
        dst: cfg.edge_label(block_id, dst) for _, dst in cfg.graph.out_edges(block_id)
    }


def block_containing(cfg, text):
    """The id of the single block whose statements include `text`."""
    matches = [
        bid
        for bid, block in cfg.blocks.items()
        if any(text in str(stmt) for stmt in block.stmts)
    ]
    assert len(matches) == 1, f"expected one block containing {text!r}, got {matches}"
    return matches[0]
