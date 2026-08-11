"""CFG construction.

One recursive pass. Blocks are created and linked as statements are visited, so
the graph is correct when the pass ends -- there is no repair phase, and no
place where a node id is guessed by arithmetic.

Two pieces of state carry the control-transfer targets that the previous
implementation had no way to express:

``_loops``
    A stack of :class:`LoopFrame`. ``break`` and ``continue`` resolve against it
    and become *edges*. Previously they were appended to a basic block as
    ordinary statements and got no edges at all, so a loop containing a ``break``
    had no path to its exit.

``_handlers``
    A stack of :class:`HandlerFrame` -- the enclosing ``try`` regions. ``throw``
    and ``return`` resolve against it, so they reach the right ``catch`` or
    ``finally`` instead of jumping straight out.

``_current`` is the block statements are appended to, or None when flow is
*sealed*: the preceding statement was a terminator, so anything that follows is
unreachable and no fallthrough edge should exist.
"""

import networkx as nx

from slcfg.ast import (
    AssertStmt,
    BasicForStmt,
    BlockStmt,
    BreakStmt,
    ContinueStmt,
    DeclStmt,
    DoWhileStmt,
    ExpressionStmt,
    Field,
    ForEachStmt,
    IfStmt,
    iter_simple_statements,
    LabeledStmt,
    RawExpr,
    ReturnStmt,
    SwitchStmt,
    SynchronizedStmt,
    ThrowStmt,
    TryStmt,
    WhileStmt,
    YieldStmt,
)
from slcfg.errors import Diagnostics

# Edge labels.
TRUE = "true"
FALSE = "false"
NO_MATCH = "no match"
# Marks the extra edge out of a `finally` that a `return`/`throw` passed through.
ABRUPT = "abrupt"

# Block kinds.
START = "start"
END = "end"
REGULAR = "regular"
CONDITIONAL = "conditional"
SWITCH = "switch"
CATCH = "catch"
FINALLY = "finally"

_LOOP_TYPES = (WhileStmt, DoWhileStmt, BasicForStmt, ForEachStmt)


class BasicBlock:
    """A maximal run of statements with a single entry and single exit."""

    def __init__(self, bid, kind=REGULAR):
        self.id = bid
        self.kind = kind
        self.stmts = []
        self.attr = {}

    def __repr__(self):
        return f"<BasicBlock {self.id} {self.kind} stmts={len(self.stmts)}>"


class LoopFrame:
    """Where `break` and `continue` go for one enclosing construct.

    A `switch` pushes a frame with ``continue_target=None``: `break` belongs to
    the switch, but `continue` passes through to the enclosing loop.
    """

    def __init__(self, break_target, continue_target, label=None):
        self.break_target = break_target
        self.continue_target = continue_target
        self.label = label


class HandlerFrame:
    """One enclosing `try` region: where `throw` and `return` go."""

    def __init__(self, catches, finally_entry):
        # list of (block_id, CatchClause)
        self.catches = catches
        self.finally_entry = finally_entry
        # Set when a `return`/`throw` routes through this finally, which means
        # the finally block can also complete abruptly.
        self.finally_abrupt = False


class MethodCFG:
    """A finished CFG for one method."""

    def __init__(self, method, package, graph, blocks, entry, exit_, unreachable):
        self.method = method
        self.package = package
        self.graph = graph
        self.blocks = blocks
        self.entry = entry
        self.exit = exit_
        # Statements the builder proved unreachable and therefore omitted.
        self.unreachable = unreachable

    def statements(self):
        for block in self.blocks.values():
            yield from block.stmts

    def edge_label(self, u, v):
        return self.graph.get_edge_data(u, v, {}).get("label", "")


class CFGBuilder:
    """Builds one :class:`MethodCFG`."""

    def __init__(self, package="", diagnostics=None):
        self.package = package
        self.diag = Diagnostics() if diagnostics is None else diagnostics

    # -- graph primitives -------------------------------------------------

    def _new_block(self, kind=REGULAR):
        self._next_id += 1
        block = BasicBlock(self._next_id, kind)
        self._blocks[block.id] = block
        self._graph.add_node(block.id)
        return block.id

    def _link(self, src, dst, label=""):
        if src is None or dst is None:
            return
        self._graph.add_edge(src, dst, label=label)

    def _goto(self, target, label=""):
        """Transfer control to `target` and seal the current block."""
        self._link(self._current, target, label)
        self._current = None

    def _enter(self, block, label=""):
        """Fall into `block`, making it current."""
        self._link(self._current, block, label)
        self._current = block

    def _emit(self, stmt):
        if self._current is None:
            # Flow is sealed: this statement cannot execute.
            self._unreachable.extend(iter_simple_statements(stmt))
            return
        self._blocks[self._current].stmts.append(stmt)

    def _emit_into(self, block, stmt):
        self._blocks[block].stmts.append(stmt)

    # -- control-transfer target resolution -------------------------------

    def _break_target(self, label):
        for frame in reversed(self._loops):
            if label is None or frame.label == label:
                return frame.break_target
        return None

    def _continue_target(self, label):
        for frame in reversed(self._loops):
            if frame.continue_target is None:
                # A `switch` frame: `break` stops here, `continue` does not.
                if label is None or frame.label != label:
                    continue
                return None
            if label is None or frame.label == label:
                return frame.continue_target
        return None

    def _innermost_finally(self):
        for frame in reversed(self._handlers):
            if frame.finally_entry is not None:
                return frame
        return None

    # -- entry point ------------------------------------------------------

    def build(self, method):
        self._graph = nx.DiGraph()
        self._blocks = {}
        self._next_id = -1
        self._loops = []
        self._handlers = []
        self._unreachable = []
        # Blocks that leave the method: return, throw, failed assert. Wired to
        # the exit node in _finalize, once that node exists.
        self._pending_exit = []

        entry = self._new_block(START)
        self._current = entry

        body = self._new_block(REGULAR)
        self._enter(body)

        self._build_statements(method.bodyBlock.body)

        exit_ = self._new_block(END)
        # Any block still open falls off the end of the method.
        self._link(self._current, exit_)
        self._current = None

        cfg = MethodCFG(
            method,
            self.package,
            self._graph,
            self._blocks,
            entry,
            exit_,
            self._unreachable,
        )
        self._finalize(cfg)
        return cfg

    # -- statement dispatch -----------------------------------------------

    def _build_statements(self, stmts):
        for stmt in stmts:
            if self._current is None:
                # Everything from here on is unreachable. Account for it so the
                # invariant checker can tell "dropped because unreachable" from
                # "dropped by a bug".
                self._unreachable.extend(iter_simple_statements(stmt))
                continue
            self._build_statement(stmt)

    def _build_statement(self, stmt):
        handler = self._DISPATCH.get(type(stmt))
        if handler is not None:
            handler(self, stmt)
        else:
            # A simple statement: one line in the current block.
            self._emit(stmt)

    def _build_block(self, block):
        if block is not None:
            self._build_statements(block.body)

    # -- if ---------------------------------------------------------------

    def _build_if(self, stmt):
        cond = self._new_block(CONDITIONAL)
        self._goto(cond)
        self._emit_into(cond, ExpressionStmt(stmt.pos, stmt.condExpr))

        then_entry = self._new_block()
        self._link(cond, then_entry, TRUE)
        self._current = then_entry
        self._build_block(stmt.bodyBlock)
        then_exit = self._current

        else_entry = self._new_block()
        self._link(cond, else_entry, FALSE)
        self._current = else_entry
        self._build_block(stmt.elseBlock)
        else_exit = self._current

        if then_exit is None and else_exit is None:
            # Both arms terminate: there is no join, and nothing follows.
            self._current = None
            return

        join = self._new_block()
        self._link(then_exit, join)
        self._link(else_exit, join)
        self._current = join

    # -- loops ------------------------------------------------------------

    def _build_while(self, stmt, label=None):
        header = self._new_block(CONDITIONAL)
        self._goto(header)
        self._emit_into(header, ExpressionStmt(stmt.pos, stmt.condExpr))

        exit_ = self._new_block()
        body = self._new_block()
        self._link(header, body, TRUE)
        self._link(header, exit_, FALSE)

        self._loops.append(LoopFrame(exit_, header, label))
        self._current = body
        self._build_block(stmt.bodyBlock)
        self._link(self._current, header)  # back edge
        self._loops.pop()

        self._current = exit_

    def _build_do_while(self, stmt, label=None):
        body = self._new_block()
        self._enter(body)

        # Allocated before the body so `continue` can target it.
        cond = self._new_block(CONDITIONAL)
        exit_ = self._new_block()

        self._loops.append(LoopFrame(exit_, cond, label))
        self._current = body
        self._build_block(stmt.bodyBlock)
        self._link(self._current, cond)
        self._loops.pop()

        self._emit_into(cond, ExpressionStmt(stmt.pos, stmt.condExpr))
        self._link(cond, body, TRUE)
        self._link(cond, exit_, FALSE)

        self._current = exit_

    def _build_basic_for(self, stmt, label=None):
        # The init statements belong to the block preceding the loop.
        self._build_statements(stmt.initStmtList)

        header = self._new_block(CONDITIONAL)
        self._goto(header)
        self._emit_into(header, ExpressionStmt(stmt.pos, stmt.condExpr))

        exit_ = self._new_block()
        body = self._new_block()
        self._link(header, body, TRUE)
        self._link(header, exit_, FALSE)

        # `continue` runs the update clause before re-testing the condition.
        update = self._new_block() if stmt.updateStmtList else None
        back_target = update if update is not None else header

        self._loops.append(LoopFrame(exit_, back_target, label))
        self._current = body
        self._build_block(stmt.bodyBlock)
        self._link(self._current, back_target)
        self._loops.pop()

        if update is not None:
            self._current = update
            self._build_statements(stmt.updateStmtList)
            self._link(update, header)
            self._current = None

        self._current = exit_

    def _build_for_each(self, stmt, label=None):
        """`for (T v : it)` as an iterator loop.

        Modeled as ``has next(it)`` / ``v = next(it)`` rather than an index
        rewrite: without type resolution we cannot tell an array from an
        Iterable, and the old `.length` rewrite was simply wrong for the latter.
        """
        header = self._new_block(CONDITIONAL)
        self._goto(header)
        self._emit_into(
            header,
            ExpressionStmt(stmt.pos, RawExpr(stmt.pos, f"has next({stmt.iterableExpr})")),
        )

        exit_ = self._new_block()
        body = self._new_block()
        self._link(header, body, TRUE)
        self._link(header, exit_, FALSE)

        self._loops.append(LoopFrame(exit_, header, label))
        self._current = body

        var = stmt.varField
        bound = Field(
            var.pos,
            var.name,
            var.type_,
            var.kind,
            RawExpr(var.pos, f"next({stmt.iterableExpr})"),
        )
        self._emit(DeclStmt(var.pos, bound))

        self._build_block(stmt.bodyBlock)
        self._link(self._current, header)
        self._loops.pop()

        self._current = exit_

    # -- labels -----------------------------------------------------------

    def _build_labeled(self, stmt):
        """`L: stmt`

        When the label is directly on a loop, it belongs to that loop's frame so
        `continue L` reaches the loop's continue target. Otherwise the label only
        provides a `break L` exit.
        """
        body = stmt.stmt.body if isinstance(stmt.stmt, BlockStmt) else [stmt.stmt]

        if len(body) == 1 and isinstance(body[0], _LOOP_TYPES):
            inner = body[0]
            self._LOOP_DISPATCH[type(inner)](self, inner, stmt.label)
            return

        exit_ = self._new_block()
        self._loops.append(LoopFrame(exit_, None, stmt.label))
        self._build_statements(body)
        self._link(self._current, exit_)
        self._loops.pop()
        self._current = exit_

    # -- switch -----------------------------------------------------------

    def _build_switch(self, stmt):
        if not stmt.cases:
            # `switch (x) { }` evaluates the selector and does nothing else, so a
            # dispatch block with a single successor would be misleading.
            self._emit(
                ExpressionStmt(stmt.pos, RawExpr(stmt.pos, f"switch ({stmt.expr})"))
            )
            return

        dispatch = self._new_block(SWITCH)
        self._goto(dispatch)
        self._emit_into(
            dispatch,
            ExpressionStmt(stmt.pos, RawExpr(stmt.pos, f"switch ({stmt.expr})")),
        )

        exit_ = self._new_block()
        # `break` leaves the switch; `continue` belongs to an enclosing loop.
        self._loops.append(LoopFrame(exit_, None))

        entries = []
        exits = []
        for case in stmt.cases:
            entry = self._new_block()
            self._link(dispatch, entry, case.label_text())
            entries.append(entry)
            self._current = entry
            self._build_block(case.body)
            exits.append(self._current)

        # Colon-form groups fall through to the next group; arrow-form never does.
        for i, case in enumerate(stmt.cases):
            if case.isArrow or exits[i] is None:
                continue
            if i + 1 < len(stmt.cases):
                self._link(exits[i], entries[i + 1])
                exits[i] = None

        for open_exit in exits:
            self._link(open_exit, exit_)

        if not any(case.isDefault for case in stmt.cases):
            # No default: an unmatched value skips the switch entirely.
            self._link(dispatch, exit_, NO_MATCH)

        self._loops.pop()
        self._current = exit_

    # -- try / catch / finally --------------------------------------------

    def _build_try(self, stmt):
        # Resource acquisition happens before the protected region.
        self._build_statements(stmt.resources)

        region = self._new_block()
        self._enter(region)

        finally_entry = self._new_block(FINALLY) if stmt.finallyBlock else None
        catch_entries = [self._new_block(CATCH) for _ in stmt.catches]

        body_frame = HandlerFrame(list(zip(catch_entries, stmt.catches)), finally_entry)
        self._handlers.append(body_frame)
        self._build_block(stmt.bodyBlock)
        try_exit = self._current
        self._handlers.pop()

        # Block-level exception edges: one edge from the protected region to each
        # handler, rather than one from every statement that might throw.
        for entry, clause in zip(catch_entries, stmt.catches):
            self._link(region, entry, f"exception: {clause.label_text()}")

        # A catch body is not protected by its sibling catches, but a `return` or
        # `throw` inside it still runs the finally -- so it gets a frame with the
        # finally and no catches.
        catch_frame = HandlerFrame([], finally_entry)
        self._handlers.append(catch_frame)
        catch_exits = []
        for entry, clause in zip(catch_entries, stmt.catches):
            self._current = entry
            self._emit(
                DeclStmt(
                    clause.pos,
                    Field(
                        clause.pos,
                        clause.param,
                        clause.label_text(),
                        Field.Type.LOCAL_VAR,
                        None,
                    ),
                )
            )
            self._build_block(clause.body)
            catch_exits.append(self._current)
        self._handlers.pop()

        after = self._new_block()

        if finally_entry is None:
            for open_exit in [try_exit] + catch_exits:
                self._link(open_exit, after)
            self._current = after
            return

        for open_exit in [try_exit] + catch_exits:
            self._link(open_exit, finally_entry)
        self._current = finally_entry
        self._build_block(stmt.finallyBlock)
        self._link(self._current, after)

        if (body_frame.finally_abrupt or catch_frame.finally_abrupt) and self._current:
            # A `return`/`throw` inside the region routed through this finally,
            # so the finally can also complete abruptly. Approximated with one
            # extra edge out, rather than duplicating the finally block per exit
            # path the way javac does -- see the README's exception notes.
            self._route_abrupt_exit()

        self._current = after

    def _route_abrupt_exit(self):
        """Send the current block onward as an abrupt (return/throw) exit."""
        outer = self._innermost_finally()
        if outer is not None:
            outer.finally_abrupt = True
            self._link(self._current, outer.finally_entry, ABRUPT)
        else:
            self._pending_exit.append((self._current, ABRUPT))

    # -- abrupt transfers -------------------------------------------------

    def _build_break(self, stmt):
        target = self._break_target(stmt.targetLabel)
        if target is None:
            self.diag.warn(stmt.pos, f"'{stmt}' has no enclosing target")
            self._current = None
            return
        # A break is an edge, not a statement.
        self._goto(target)

    def _build_continue(self, stmt):
        target = self._continue_target(stmt.targetLabel)
        if target is None:
            self.diag.warn(stmt.pos, f"'{stmt}' has no enclosing loop")
            self._current = None
            return
        self._goto(target)

    def _build_return(self, stmt):
        # The return statement itself stays visible; it carries the value.
        self._emit(stmt)
        frame = self._innermost_finally()
        if frame is not None:
            frame.finally_abrupt = True
            self._goto(frame.finally_entry)
        else:
            self._pending_exit.append(self._current)
            self._current = None

    def _build_throw(self, stmt):
        self._emit(stmt)
        if self._handlers:
            frame = self._handlers[-1]
            if frame.catches:
                for entry, clause in frame.catches:
                    self._link(self._current, entry, f"exception: {clause.label_text()}")
                self._current = None
                return
            if frame.finally_entry is not None:
                frame.finally_abrupt = True
                self._goto(frame.finally_entry)
                return
        self._pending_exit.append(self._current)
        self._current = None

    def _build_yield(self, stmt):
        self._emit(stmt)
        target = self._break_target(None)
        if target is not None:
            self._goto(target)
        else:
            self._pending_exit.append(self._current)
            self._current = None

    # -- other compounds --------------------------------------------------

    def _build_synchronized(self, stmt):
        # Flow is single-threaded here; the lock does not branch.
        self._emit(
            ExpressionStmt(stmt.pos, RawExpr(stmt.pos, f"monitor enter {stmt.lockExpr}"))
        )
        self._build_block(stmt.bodyBlock)
        self._emit(
            ExpressionStmt(stmt.pos, RawExpr(stmt.pos, f"monitor exit {stmt.lockExpr}"))
        )

    def _build_assert(self, stmt):
        """`assert cond` branches: it either continues or raises."""
        cond = self._new_block(CONDITIONAL)
        self._goto(cond)
        self._emit_into(cond, stmt)

        after = self._new_block()
        self._link(cond, after, TRUE)
        # The failing path raises AssertionError, so it leaves the method.
        self._pending_exit.append((cond, FALSE))
        self._current = after

    def _build_nested_block(self, stmt):
        self._build_block(stmt)

    _DISPATCH = {}
    _LOOP_DISPATCH = {}

    # -- finalization -----------------------------------------------------

    def _finalize(self, cfg):
        _link_pending_exits(cfg, self._pending_exit)
        _link_open_tails(cfg)
        _drop_unreachable(cfg)
        _contract_empty_blocks(cfg)
        _merge_straight_chains(cfg)
        _renumber_breadth_first(cfg)


# Filled after the class body so the methods exist.
CFGBuilder._DISPATCH = {
    BlockStmt: CFGBuilder._build_nested_block,
    IfStmt: CFGBuilder._build_if,
    WhileStmt: CFGBuilder._build_while,
    DoWhileStmt: CFGBuilder._build_do_while,
    BasicForStmt: CFGBuilder._build_basic_for,
    ForEachStmt: CFGBuilder._build_for_each,
    LabeledStmt: CFGBuilder._build_labeled,
    SwitchStmt: CFGBuilder._build_switch,
    TryStmt: CFGBuilder._build_try,
    SynchronizedStmt: CFGBuilder._build_synchronized,
    AssertStmt: CFGBuilder._build_assert,
    BreakStmt: CFGBuilder._build_break,
    ContinueStmt: CFGBuilder._build_continue,
    ReturnStmt: CFGBuilder._build_return,
    ThrowStmt: CFGBuilder._build_throw,
    YieldStmt: CFGBuilder._build_yield,
}

CFGBuilder._LOOP_DISPATCH = {
    WhileStmt: CFGBuilder._build_while,
    DoWhileStmt: CFGBuilder._build_do_while,
    BasicForStmt: CFGBuilder._build_basic_for,
    ForEachStmt: CFGBuilder._build_for_each,
}


# ---------------------------------------------------------------------------
# Post-passes
# ---------------------------------------------------------------------------


def _link_pending_exits(cfg, pending):
    """Wire blocks that leave the method (return, throw, failed assert) to `end`."""
    for item in pending:
        if isinstance(item, tuple):
            block, label = item
        else:
            block, label = item, ""
        if block is not None and block in cfg.graph:
            cfg.graph.add_edge(block, cfg.exit, label=label)


def _link_open_tails(cfg):
    """Give every block a successor: an open tail falls off the end."""
    for bid in list(cfg.graph.nodes):
        if bid == cfg.exit:
            continue
        if cfg.graph.out_degree(bid) == 0:
            cfg.graph.add_edge(bid, cfg.exit, label="")


def _drop_unreachable(cfg):
    """Remove blocks not reachable from the entry.

    Replaces the old scan that walked block ids downward looking for something
    to reattach an orphan to.
    """
    reachable = set(nx.descendants(cfg.graph, cfg.entry)) | {cfg.entry}
    for bid in list(cfg.graph.nodes):
        if bid in reachable:
            continue
        cfg.unreachable.extend(cfg.blocks[bid].stmts)
        cfg.graph.remove_node(bid)
        del cfg.blocks[bid]


def _contract_empty_blocks(cfg):
    """Splice out empty blocks, but only where no edge is lost.

    An empty block survives whenever removing it would destroy information. Each
    such block is marked with `attr["structural"]` explaining why, and
    :func:`slcfg.verify.check_no_empty_blocks` accepts exactly those -- so the
    pass and the invariant cannot drift apart.

    The collision case matters most. `if (c) {} else {}` leaves two empty arms
    whose `true` and `false` edges both end up at the same join. A DiGraph holds
    one edge per pair, so contracting the second arm would overwrite the first
    arm's label and silently lose a branch.
    """
    changed = True
    while changed:
        changed = False
        for bid in list(cfg.graph.nodes):
            if bid not in cfg.graph:
                continue
            block = cfg.blocks[bid]
            if bid in (cfg.entry, cfg.exit) or block.kind != REGULAR or block.stmts:
                continue

            if cfg.graph.out_degree(bid) != 1:
                block.attr["structural"] = "branch point"
                continue

            (_, successor), = cfg.graph.out_edges(bid)
            if cfg.edge_label(bid, successor):
                block.attr["structural"] = "its out-edge carries a label"
                continue
            if successor == bid:
                block.attr["structural"] = "empty self-looping body"
                continue

            in_edges = [
                (pred, cfg.edge_label(pred, bid))
                for pred, _ in cfg.graph.in_edges(bid)
            ]
            if any(pred == successor for pred, _ in in_edges):
                block.attr["structural"] = "contracting would create a self-loop"
                continue
            if any(
                cfg.graph.has_edge(pred, successor)
                and cfg.edge_label(pred, successor) != label
                for pred, label in in_edges
            ):
                block.attr["structural"] = "keeps two labelled edges distinct"
                continue

            for pred, label in in_edges:
                cfg.graph.add_edge(pred, successor, label=label)

            cfg.graph.remove_node(bid)
            del cfg.blocks[bid]
            changed = True


def _merge_straight_chains(cfg):
    """Merge `u -> v` when that edge is the only way in or out of either side."""
    changed = True
    while changed:
        changed = False
        for bid in list(cfg.graph.nodes):
            if bid not in cfg.graph or bid == cfg.exit:
                continue
            block = cfg.blocks[bid]
            # START stays empty: it renders as a bare oval, so statements merged
            # into it would be invisible.
            if block.kind != REGULAR or cfg.graph.out_degree(bid) != 1:
                continue

            (_, successor), = cfg.graph.out_edges(bid)
            if successor in (cfg.entry, cfg.exit) or successor == bid:
                continue
            if cfg.graph.in_degree(successor) != 1:
                continue
            if cfg.blocks[successor].kind != REGULAR:
                continue
            if cfg.edge_label(bid, successor):
                continue

            block.stmts.extend(cfg.blocks[successor].stmts)
            for _, target in list(cfg.graph.out_edges(successor)):
                cfg.graph.add_edge(
                    bid, target, label=cfg.edge_label(successor, target)
                )
            cfg.graph.remove_node(successor)
            del cfg.blocks[successor]
            changed = True


def _renumber_breadth_first(cfg):
    """Renumber blocks in BFS order from the entry, so ids read top to bottom."""
    order = [cfg.entry]
    seen = {cfg.entry}
    queue = [cfg.entry]
    while queue:
        node = queue.pop(0)
        for successor in sorted(cfg.graph.successors(node)):
            if successor not in seen:
                seen.add(successor)
                order.append(successor)
                queue.append(successor)
    # The exit is always last, and any node BFS missed keeps a stable place.
    order.extend(n for n in sorted(cfg.graph.nodes) if n not in seen)
    order = [n for n in order if n != cfg.exit] + [cfg.exit]

    mapping = {old: new for new, old in enumerate(order)}
    cfg.graph = nx.relabel_nodes(cfg.graph, mapping, copy=True)
    new_blocks = {}
    for old, new in mapping.items():
        block = cfg.blocks[old]
        block.id = new
        new_blocks[new] = block
    cfg.blocks = dict(sorted(new_blocks.items()))
    cfg.entry = mapping[cfg.entry]
    cfg.exit = mapping[cfg.exit]


def build_cfgs(ast, diagnostics=None):
    """Build one :class:`MethodCFG` per method with a body."""
    builder = CFGBuilder(ast.package, diagnostics)
    cfgs = []
    for method in ast.methods():
        # Abstract and interface methods have no body, so there is nothing to
        # graph -- as distinct from an empty `{}` body, which gets start -> end.
        if not method.hasBody or method.bodyBlock is None:
            continue
        cfgs.append(builder.build(method))
    return cfgs
