"""Output: Graphviz figures and JSON.

The visual language is unchanged from the original tool -- green `start`, red
`end`, blue conditional, an HTML table of statements with their source positions
-- so existing figures stay recognizable.
"""

import html
import json
import os

import graphviz as gv

from slcfg.cfg import ABRUPT, CATCH, CONDITIONAL, END, FINALLY, START, SWITCH

# Fill colors per block kind.
_FILL = {
    START: "#aaffaa",
    END: "#ff8080",
    CONDITIONAL: "#6cb4ee",
    SWITCH: "#8ce68c",
    CATCH: "#ffd28c",
    FINALLY: "#e0c8f0",
}

# Where an edge leaves its tail, so true/false branches separate visually.
_TAILPORT = {"true": "sw", "false": "se"}

_EXCEPTION_PREFIX = "exception: "


def block_label(block):
    """An HTML-like label: one row per statement, with its position."""
    rows = []
    for index, stmt in enumerate(block.stmts):
        last = index == len(block.stmts) - 1
        sides = "lrb" if last else "lr"
        pos_sides = "rb" if last else "r"
        rows.append(
            f'<tr><td align="left" sides="{sides}">{html.escape(str(stmt))}</td>'
            f'<td sides="{pos_sides}">{html.escape(str(stmt.pos))}</td></tr>'
        )
    return (
        '<<FONT POINT-SIZE="8"><TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">'
        f"<tr><td>{block.id}</td><td>pos</td></tr>"
        f'{"".join(rows)}'
        "</TABLE></FONT>>"
    )


def assign_filenames(cfgs):
    """Map each CFG to a unique output basename.

    Overloads share a name, so a colliding basename gets its parameter count
    appended. This replaces the old scheme of scrubbing `<`, `>`, `(`, `)` out of
    a name that included the whole parameter list.
    """
    names = {}
    used = {}
    for cfg in cfgs:
        base = _sanitize(cfg.method.qualified_name())
        count = used.get(base, 0)
        used[base] = count + 1
        if count:
            base = f"{base}__{len(cfg.method.params)}args_{count}"
        names[id(cfg)] = base
    return names


def _sanitize(name):
    out = []
    for char in name:
        out.append(char if char.isalnum() or char in "._$" else "_")
    return "".join(out).strip(".") or "method"


def draw_cfg(cfg, out_dir, basename, fmt="pdf"):
    """Render one CFG. Returns the path written.

    `fmt="dot"` writes the Graphviz source and needs no `dot` binary; every other
    format shells out to Graphviz.
    """
    graph = gv.Digraph(
        format=fmt,
        node_attr={"shape": "none"},
        strict=True,
        graph_attr={"rankdir": "TD"},
    )

    title = (
        f"package: {cfg.package or '(default)'}\\n"
        f"class: {cfg.method.scope}\\n"
        f"method: {cfg.method.signature()}"
    )
    graph.node(title, style="filled", fillcolor="#ffff00", shape="tab", fontsize="9")

    for bid, block in cfg.blocks.items():
        if block.kind == START:
            graph.node(str(bid), label="start", style="filled",
                       fillcolor=_FILL[START], shape="oval")
        elif block.kind == END:
            graph.node(str(bid), label="end", style="filled",
                       fillcolor=_FILL[END], shape="oval")
        else:
            fill = _FILL.get(block.kind)
            if fill:
                graph.node(str(bid), label=block_label(block),
                           style="filled", fillcolor=fill)
            else:
                graph.node(str(bid), label=block_label(block))

    for src, dst in cfg.graph.edges:
        label = cfg.edge_label(src, dst)
        kwargs = {"tailport": _TAILPORT.get(label, "s")}

        # Exception and abrupt edges get their own style, so the figure does not
        # have to spell out "exception:" on every one -- those labels are long
        # enough to stretch the whole graph sideways.
        if label.startswith(_EXCEPTION_PREFIX):
            kwargs.update(
                label=label[len(_EXCEPTION_PREFIX):],
                style="dashed",
                color="#c04000",
                fontcolor="#c04000",
            )
        elif label == ABRUPT:
            kwargs.update(label=label, style="dotted", color="#707070", fontcolor="#707070")
        elif label:
            kwargs["label"] = label

        graph.edge(str(src), str(dst), **kwargs)

    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, basename)

    if fmt == "dot":
        path = f"{stem}.dot"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(graph.source)
        return path

    # cleanup=True removes the intermediate .gv file; the original slept a second
    # and unlinked it by hand.
    return graph.render(stem, view=False, cleanup=True)


def cfg_to_dict(cfg, source=None):
    """Serialize a CFG.

    Schema (see the README): a header identifying the method, `nodes` with their
    statements, and `edges` that always carry an explicit `label` -- `""` for
    unconditional flow, otherwise `true`/`false`/`case ...`/`default`/`no match`/
    `exception: T`/`abrupt`.
    """
    return {
        "package": cfg.package,
        "class": cfg.method.scope,
        "method": cfg.method.name,
        "signature": cfg.method.signature(),
        "source": source,
        "entry": cfg.entry,
        "exit": cfg.exit,
        "nodes": [
            {
                "id": bid,
                "type": block.kind,
                "statements": [stmt.to_dict() for stmt in block.stmts],
            }
            for bid, block in cfg.blocks.items()
        ],
        "edges": [
            {
                "from": src,
                "to": dst,
                "label": cfg.edge_label(src, dst),
            }
            for src, dst in sorted(cfg.graph.edges)
        ],
        "unreachable": [stmt.to_dict() for stmt in cfg.unreachable],
    }


def dump_json(cfg, out_dir, basename, source=None):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{basename}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cfg_to_dict(cfg, source), handle, indent=4)
        handle.write("\n")
    return path


def canonical_dict(cfg):
    """A comparison-stable form for golden tests.

    Block ids are already breadth-first, but they are dropped here anyway so a
    renumbering that preserves structure cannot fail a test. Nodes are keyed by
    their position in that order, and edges by the pair of positions.
    """
    order = {bid: index for index, bid in enumerate(cfg.blocks)}
    return {
        "signature": cfg.method.signature(),
        "nodes": [
            {
                "index": order[bid],
                "type": block.kind,
                "statements": [f"{stmt.pos}|{stmt}" for stmt in block.stmts],
            }
            for bid, block in cfg.blocks.items()
        ],
        "edges": sorted(
            [order[src], order[dst], cfg.edge_label(src, dst)]
            for src, dst in cfg.graph.edges
        ),
        "unreachable": sorted(f"{s.pos}|{s}" for s in cfg.unreachable),
    }
