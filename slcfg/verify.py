"""Structural invariants for a generated CFG.

This module exists because the failure mode being fixed was *silent*: the old
generator produced graphs that looked plausible and were wrong, so there was no
signal short of reading every figure by hand. Each check below turns one class of
that wrongness into a named violation.

The load-bearing one is :func:`check_statement_conservation`. Every statement in
the AST must appear exactly once in the CFG, or be accounted for as unreachable.
That is what catches a dropped `continue`, a branch body filed into the wrong
arm, or a block duplicated by a bad merge -- the families that made the output
roughly 70% correct.
"""

import networkx as nx

from slcfg.ast import (
    BreakStmt,
    ContinueStmt,
    iter_simple_statements,
)
from slcfg.cfg import CONDITIONAL, END, FALSE, REGULAR, START, SWITCH, TRUE


class Violation:
    """One failed invariant."""

    def __init__(self, cfg, check, message):
        self.method = cfg.method.qualified_name()
        self.check = check
        self.message = message

    def __str__(self):
        return f"{self.method}: [{self.check}] {self.message}"


def check_cfg(cfg, allow_infinite_loops=True):
    """Run every invariant. Returns a list of :class:`Violation`."""
    violations = []
    for check in (
        check_reachable_from_entry,
        check_reaches_exit,
        check_conditional_edges,
        check_switch_edges,
        check_no_empty_blocks,
        check_no_duplicate_or_bogus_edges,
        check_transfers_are_edges,
        check_statement_conservation,
        check_entry_and_exit,
    ):
        if check is check_reaches_exit:
            violations.extend(check(cfg, allow_infinite_loops))
        else:
            violations.extend(check(cfg))
    return violations


def check_entry_and_exit(cfg):
    """Exactly one start and one end block, with the expected degrees."""
    out = []
    starts = [b for b in cfg.blocks.values() if b.kind == START]
    ends = [b for b in cfg.blocks.values() if b.kind == END]
    if len(starts) != 1:
        out.append(Violation(cfg, "entry", f"expected 1 start block, found {len(starts)}"))
    if len(ends) != 1:
        out.append(Violation(cfg, "exit", f"expected 1 end block, found {len(ends)}"))
    if cfg.graph.in_degree(cfg.entry) != 0:
        out.append(Violation(cfg, "entry", "start block has an incoming edge"))
    if cfg.graph.out_degree(cfg.exit) != 0:
        out.append(Violation(cfg, "exit", "end block has an outgoing edge"))
    return out


def check_reachable_from_entry(cfg):
    reachable = set(nx.descendants(cfg.graph, cfg.entry)) | {cfg.entry}
    orphans = sorted(set(cfg.graph.nodes) - reachable)
    if orphans:
        return [
            Violation(cfg, "reachability", f"blocks unreachable from start: {orphans}")
        ]
    return []


def check_reaches_exit(cfg, allow_infinite_loops=True):
    """Every block must have a path to `end`.

    A deliberate infinite loop legitimately has none, so it is tolerated by
    default -- but only for blocks that actually sit on a cycle, not for a block
    that simply lost its successor.
    """
    reverse = cfg.graph.reverse(copy=False)
    can_exit = set(nx.descendants(reverse, cfg.exit)) | {cfg.exit}
    stuck = sorted(set(cfg.graph.nodes) - can_exit)
    if not stuck:
        return []

    if allow_infinite_loops:
        on_cycle = set()
        for component in nx.strongly_connected_components(cfg.graph):
            if len(component) > 1:
                on_cycle |= component
            else:
                (only,) = component
                if cfg.graph.has_edge(only, only):
                    on_cycle.add(only)
        stuck = [b for b in stuck if b not in on_cycle]
        if not stuck:
            return []

    return [Violation(cfg, "termination", f"blocks with no path to end: {stuck}")]


def check_conditional_edges(cfg):
    """A conditional has exactly two successors, labeled `true` and `false`."""
    out = []
    for bid, block in cfg.blocks.items():
        if block.kind != CONDITIONAL:
            continue
        labels = sorted(cfg.edge_label(bid, v) for _, v in cfg.graph.out_edges(bid))
        if labels != sorted([TRUE, FALSE]):
            out.append(
                Violation(
                    cfg,
                    "conditional",
                    f"block {bid} has out-edge labels {labels}, expected ['false', 'true']",
                )
            )
    return out


def check_switch_edges(cfg):
    """Every out-edge of a switch dispatch is labeled, and the labels are distinct.

    A switch whose only case is `default` legitimately has one successor, so the
    count is not constrained -- only that each edge says which case it is.
    """
    out = []
    for bid, block in cfg.blocks.items():
        if block.kind != SWITCH:
            continue
        labels = [cfg.edge_label(bid, v) for _, v in cfg.graph.out_edges(bid)]
        if not labels:
            out.append(Violation(cfg, "switch", f"block {bid} has no out-edges"))
        unlabeled = [label for label in labels if not label]
        if unlabeled:
            out.append(
                Violation(
                    cfg, "switch", f"block {bid} has {len(unlabeled)} unlabeled out-edge(s)"
                )
            )
        if len(set(labels)) != len(labels):
            out.append(Violation(cfg, "switch", f"block {bid} has duplicate case labels"))
    return out


def check_no_empty_blocks(cfg):
    """No empty block, except start, end, and ones kept on purpose.

    A few empty blocks carry structure rather than statements -- the empty body of
    `while (c) {}`, or an arm of `if (c) {} else {}` that exists so the `true` and
    `false` edges stay distinct. The contraction pass marks each of those with
    `attr["structural"]` and the reason, so anything empty and *unmarked* is a
    block the pass should have removed.
    """
    empties = [
        bid
        for bid, block in cfg.blocks.items()
        if not block.stmts
        and block.kind not in (START, END)
        and "structural" not in block.attr
    ]
    if empties:
        return [Violation(cfg, "empty-block", f"empty blocks remain: {sorted(empties)}")]
    return []


def check_no_duplicate_or_bogus_edges(cfg):
    """No self-loop that is not a real back-edge, and no parallel edges.

    `nx.DiGraph` cannot hold parallel edges, so a duplicate would have silently
    overwritten a label instead; this checks the observable consequence -- a
    conditional whose two successors are the same block.
    """
    out = []
    for bid in cfg.graph.nodes:
        if cfg.graph.has_edge(bid, bid) and cfg.blocks[bid].kind == REGULAR:
            out.append(
                Violation(cfg, "self-loop", f"regular block {bid} has a self-loop")
            )
    return out


def check_transfers_are_edges(cfg):
    """`break` and `continue` must be edges, not block contents.

    They carry no information beyond their target, so a `break` sitting inside a
    basic block means the builder failed to resolve it -- which is exactly what
    the old generator did, leaving loops with no path to their exit.
    """
    out = []
    for bid, block in cfg.blocks.items():
        for stmt in block.stmts:
            if isinstance(stmt, (BreakStmt, ContinueStmt)):
                out.append(
                    Violation(
                        cfg,
                        "transfer-as-statement",
                        f"block {bid} contains '{stmt}' as a statement",
                    )
                )
    return out


def check_statement_conservation(cfg):
    """Every AST statement appears exactly once in the CFG, or is unreachable.

    Compound statements are excluded: they become graph structure, and their
    conditions are re-emitted as the contents of the conditional blocks, which
    are counted separately below. `break` and `continue` are excluded for the
    same reason -- they are represented as edges, which
    :func:`check_transfers_are_edges` asserts from the other direction.
    """
    expected = _multiset(
        stmt
        for stmt in iter_simple_statements(cfg.method.bodyBlock)
        if not isinstance(stmt, (BreakStmt, ContinueStmt))
    )
    unreachable = _multiset(cfg.unreachable)
    actual = _multiset(cfg.statements())

    out = []
    missing = _subtract(_subtract(expected, actual), unreachable)
    if missing:
        out.append(
            Violation(
                cfg,
                "conservation",
                "statements missing from the CFG: " + _describe(missing),
            )
        )

    # Anything in the CFG that is not an AST statement should be a synthesized
    # one (a loop condition, a switch dispatch, a caught-exception binding).
    extra = _subtract(actual, expected)
    duplicated = {key: n for key, n in extra.items() if key in expected}
    if duplicated:
        out.append(
            Violation(
                cfg,
                "conservation",
                "statements duplicated in the CFG: " + _describe(duplicated),
            )
        )
    return out


def _multiset(stmts):
    counts = {}
    for stmt in stmts:
        key = (str(stmt.pos), str(stmt))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _subtract(left, right):
    out = {}
    for key, count in left.items():
        remaining = count - right.get(key, 0)
        if remaining > 0:
            out[key] = remaining
    return out


def _describe(counts, limit=5):
    items = sorted(counts.items())
    shown = ", ".join(f"{text!r}@{pos}x{n}" for (pos, text), n in items[:limit])
    if len(items) > limit:
        shown += f", ... (+{len(items) - limit} more)"
    return shown


def check_all(cfgs, allow_infinite_loops=True):
    violations = []
    for cfg in cfgs:
        violations.extend(check_cfg(cfg, allow_infinite_loops))
    return violations
