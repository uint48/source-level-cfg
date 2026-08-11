"""CFG tests: invariants on every sample, goldens, and targeted regressions.

The regression tests at the bottom each pin one bug that made the old output
wrong. They assert on *edges*, because that is what was missing -- a `break` or
`continue` used to be appended to a basic block as a statement, leaving the loop
with no path to its exit.
"""

import pytest

from slcfg.cfg import CONDITIONAL, END, START, SWITCH
from slcfg.verify import check_cfg
from tests.helpers import (
    block_containing,
    canonical_for,
    cfgs_for,
    find_cfg,
    read_golden,
    sample_paths,
    successors,
)

SAMPLES = sample_paths()
SAMPLE_IDS = [p.stem for p in SAMPLES]


def test_samples_exist():
    assert SAMPLES, "no Java samples found"


@pytest.mark.parametrize("java_path", SAMPLES, ids=SAMPLE_IDS)
def test_invariants(java_path):
    """Every method of every sample satisfies every structural invariant."""
    cfgs, _ = cfgs_for(java_path)
    violations = []
    for cfg in cfgs:
        violations.extend(str(v) for v in check_cfg(cfg))
    assert violations == []


@pytest.mark.parametrize("java_path", SAMPLES, ids=SAMPLE_IDS)
def test_matches_golden(java_path):
    """The graph is byte-for-byte what it was when last reviewed by hand."""
    assert canonical_for(java_path) == read_golden(java_path)


@pytest.mark.parametrize("java_path", SAMPLES, ids=SAMPLE_IDS)
def test_no_warnings_except_switch_expressions(java_path):
    """Samples should not trip diagnostics, other than the documented one."""
    _, diagnostics = cfgs_for(java_path)
    unexpected = [
        (pos, msg) for pos, msg in diagnostics.warnings if "switch expression" not in msg
    ]
    assert unexpected == []


# ---------------------------------------------------------------------------
# Regressions: one test per bug class that made the old output wrong
# ---------------------------------------------------------------------------


def test_continue_inside_if_is_an_edge_to_the_update_block():
    """`continue` inside an `if` used to be dropped from the AST entirely.

    `enterContinueStatement` assigned the target body list but never appended to
    it, so the statement vanished and no edge was created.
    """
    cfgs, _ = cfgs_for("javasamples/Example12.java")
    cfg = find_cfg(cfgs, "main")

    guard = block_containing(cfg, "i % 2 == 0")
    update = block_containing(cfg, "i++")
    assert successors(cfg, guard)[update] == "true"


def test_break_inside_if_is_an_edge_to_the_loop_exit():
    """`break` used to be emitted as a statement, leaving no path to the exit."""
    cfgs, _ = cfgs_for("javasamples/Example12.java")
    cfg = find_cfg(cfgs, "main")

    guard = block_containing(cfg, "i > 7")
    header = block_containing(cfg, "i < 10")
    # The loop's false edge and the break must land on the same block.
    (loop_exit,) = [
        dst for dst, label in successors(cfg, header).items() if label == "false"
    ]
    assert successors(cfg, guard)[loop_exit] == "true"


def test_labeled_continue_targets_the_outer_loop():
    """`continue outer` must reach the *outer* loop's update block."""
    cfgs, _ = cfgs_for("javasamples/Example13.java")
    cfg = find_cfg(cfgs, "main")

    guard = block_containing(cfg, "j == 3")
    outer_update = block_containing(cfg, "i++")
    assert successors(cfg, guard)[outer_update] == "true"


def test_switch_multi_label_group_keeps_every_label():
    """Cases were keyed by label text in a dict, so `case 2, 3:` kept only "3"."""
    cfgs, _ = cfgs_for("javasamples/Example14.java")
    cfg = find_cfg(cfgs, "classify")

    (dispatch,) = [b for b, blk in cfg.blocks.items() if blk.kind == SWITCH]
    labels = set(successors(cfg, dispatch).values())
    assert "case 2, 3" in labels
    assert "default" in labels
    assert "case 99" in labels


def test_switch_fallthrough_comes_from_the_end_of_the_previous_case():
    """Fall-through edges used to originate at the case body's *start*."""
    cfgs, _ = cfgs_for("javasamples/Example14.java")
    cfg = find_cfg(cfgs, "classify")

    case_one = block_containing(cfg, 'name = "one"')
    case_small = block_containing(cfg, '" small"')
    assert case_small in successors(cfg, case_one)

    # `case 0` ends in a break, so it must NOT fall through.
    case_zero = block_containing(cfg, 'name = "zero"')
    assert case_small not in successors(cfg, case_zero)


def test_arrow_switch_cases_never_fall_through():
    cfgs, _ = cfgs_for("javasamples/Example15.java")
    cfg = find_cfg(cfgs, "main")

    weekend = block_containing(cfg, "weekend")
    weekday = block_containing(cfg, '"weekday"')
    assert weekday not in successors(cfg, weekend)


def test_catch_bodies_are_reachable_via_exception_edges():
    """try/catch was unhandled, so catch bodies had no incoming edges."""
    cfgs, _ = cfgs_for("javasamples/Example16.java")
    cfg = find_cfg(cfgs, "read")

    catch = block_containing(cfg, "bad argument")
    incoming = [cfg.edge_label(src, catch) for src, _ in cfg.graph.in_edges(catch)]
    assert any(label.startswith("exception:") for label in incoming)


def test_return_inside_catch_runs_the_finally():
    """A `return` in a catch clause must route through the finally block."""
    cfgs, _ = cfgs_for("javasamples/Example16.java")
    cfg = find_cfg(cfgs, "read")

    catch = block_containing(cfg, "fatal")
    finally_block = block_containing(cfg, "cleanup")
    assert finally_block in successors(cfg, catch)


def test_unreachable_code_after_return_is_dropped_and_accounted():
    """Code after a `return` is removed, but recorded rather than lost."""
    cfgs, _ = cfgs_for("javasamples/Example9.java")
    cfg = find_cfg(cfgs, "main")

    assert all("doWhileCounter" not in str(s) for s in cfg.statements())
    assert any("doWhileCounter" in str(s) for s in cfg.unreachable)


def test_dangling_else_binds_to_the_inner_if():
    """The grammar's `*NoShortIf` variants had no handler at all."""
    cfgs, _ = cfgs_for("javasamples/Example17.java")
    cfg = find_cfg(cfgs, "danglingElse")

    inner = block_containing(cfg, "b > 0")
    both = block_containing(cfg, "both positive")
    a_only = block_containing(cfg, "a positive, b not")
    assert successors(cfg, inner) == {both: "true", a_only: "false"}


def test_unbraced_return_in_then_branch_stays_in_the_then_branch():
    """The old string toggle filed this into the *else* branch."""
    cfgs, _ = cfgs_for("javasamples/Example17.java")
    cfg = find_cfg(cfgs, "sign")

    cond = block_containing(cfg, "n > 0")
    positive = block_containing(cfg, "return 1")
    assert successors(cfg, cond)[positive] == "true"


def test_triple_shift_operator_is_parsed_whole():
    """`>>>` was built from two of its three tokens, leaving `>` as the operand."""
    cfgs, _ = cfgs_for("javasamples/Example18.java")
    cfg = find_cfg(cfgs, "shifts")

    text = " ".join(str(s) for s in cfg.statements())
    assert "v >>> 3" in text
    assert "v >> 1" in text


def test_field_access_is_not_rendered_as_a_binary_operator():
    """A 3-child catch-all turned `a.b` into a binary expression printed `a . b`."""
    cfgs, _ = cfgs_for("javasamples/Example18.java")
    cfg = find_cfg(cfgs, "ternaryAndShortCircuit")

    text = " ".join(str(s) for s in cfg.statements())
    assert "this.count" in text
    assert "this . count" not in text


def test_for_each_uses_an_iterator_not_a_length_rewrite():
    """The old rewrite hard-coded `.length`, which is wrong for any Iterable."""
    cfgs, _ = cfgs_for("javasamples/Example19.java")
    cfg = find_cfg(cfgs, "printNames")

    text = " ".join(str(s) for s in cfg.statements())
    assert "has next(names)" in text
    assert "next(names)" in text
    assert ".length" not in text


def test_lambda_body_becomes_its_own_method():
    """Lambda statements used to be spliced into the enclosing method's CFG."""
    cfgs, _ = cfgs_for("javasamples/Example23.java")

    names = [cfg.method.name for cfg in cfgs]
    assert "main$lambda$0" in names

    # The lambda's own graph holds its branch...
    lambda_cfg = find_cfg(cfgs, "main$lambda$0")
    assert any("a-name" in str(s) for s in lambda_cfg.statements())

    # ...and the enclosing method shows only the elided lambda, not its body.
    enclosing = find_cfg(cfgs, "main")
    text = " ".join(str(s) for s in enclosing.statements())
    assert "a-name" not in text
    assert "name -> {...}" in text


def test_nested_classes_keep_separate_scopes():
    """A single `CurrentClass` slot meant a nested class clobbered its outer one."""
    cfgs, _ = cfgs_for("javasamples/Example21.java")
    scopes = {cfg.method.qualified_name() for cfg in cfgs}

    assert "Example21.Helper.twice" in scopes
    assert "Example21.Inner.plusOuter" in scopes
    assert "Example21.<clinit>" in scopes


def test_method_overloads_both_produce_a_cfg():
    cfgs, _ = cfgs_for("javasamples/Example21.java")
    scale = [cfg for cfg in cfgs if cfg.method.name == "scale"]
    assert len(scale) == 2
    assert {len(cfg.method.params) for cfg in scale} == {1, 2}


def test_abstract_method_produces_no_cfg():
    cfgs, _ = cfgs_for("javasamples/Example22.java")
    assert "apply" not in [cfg.method.name for cfg in cfgs]
    assert "applyTwice" in [cfg.method.name for cfg in cfgs]


def test_infinite_loop_has_no_path_to_end_but_is_accepted():
    """A `while (true)` body legitimately cannot reach the exit."""
    cfgs, _ = cfgs_for("javasamples/Example20.java")
    cfg = find_cfg(cfgs, "infiniteLoop")

    assert check_cfg(cfg, allow_infinite_loops=True) == []
    body = block_containing(cfg, "forever")
    header = block_containing(cfg, "true")
    assert successors(cfg, body) == {header: ""}


def test_empty_if_arms_keep_both_branch_edges():
    """`if (c) {} else {}`: contracting both empty arms used to lose a label.

    A DiGraph holds one edge per node pair, so redirecting the second arm's
    `false` edge over the first arm's `true` edge silently dropped a branch.
    """
    cfgs, _ = cfgs_for("javasamples/Example25.java")
    cfg = find_cfg(cfgs, "emptyIf")

    cond = block_containing(cfg, "n > 0")
    assert sorted(successors(cfg, cond).values()) == ["false", "true"]


def test_empty_blocks_that_survive_say_why():
    """Any empty block left in the graph must be marked as deliberate."""
    for java_path in SAMPLES:
        cfgs, _ = cfgs_for(java_path)
        for cfg in cfgs:
            for bid, block in cfg.blocks.items():
                if block.stmts or block.kind in (START, END):
                    continue
                assert "structural" in block.attr, f"{java_path}:{cfg.method.name}:{bid}"


def test_switch_without_cases_produces_no_dispatch_block():
    cfgs, _ = cfgs_for("javasamples/Example25.java")
    cfg = find_cfg(cfgs, "emptySwitch")

    assert not [b for b in cfg.blocks.values() if b.kind == SWITCH]
    assert any("switch (n)" in str(s) for s in cfg.statements())


def test_switch_without_default_gets_a_no_match_edge():
    cfgs, _ = cfgs_for("javasamples/Example25.java")
    cfg = find_cfg(cfgs, "switchWithoutDefault")

    (dispatch,) = [b for b, blk in cfg.blocks.items() if blk.kind == SWITCH]
    assert "no match" in successors(cfg, dispatch).values()


def test_nested_finally_keeps_normal_and_abrupt_paths_distinct():
    cfgs, _ = cfgs_for("javasamples/Example25.java")
    cfg = find_cfg(cfgs, "nestedTryFinally")

    inner = block_containing(cfg, "inner finally")
    outer = block_containing(cfg, "outer finally")
    # The inner finally reaches the outer one abruptly (the rethrow) and also
    # continues normally -- two different successors, not one merged edge.
    labels = sorted(successors(cfg, inner).values())
    assert "abrupt" in labels
    assert len(successors(cfg, inner)) == 2
    assert outer in successors(cfg, inner)


def test_break_and_continue_resolve_to_the_right_nested_loop():
    """`else break` exits the k loop; `else continue` re-enters it."""
    cfgs, _ = cfgs_for("javasamples/Example25.java")
    cfg = find_cfg(cfgs, "deeplyNestedUnbraced")

    k_header = block_containing(cfg, "k < n")
    k_update = block_containing(cfg, "k++")
    j_update = block_containing(cfg, "j++")

    outer_if = block_containing(cfg, "i == j")
    inner_if = block_containing(cfg, "j == k")

    # `break` leaves the k loop, landing where the k header's false edge lands.
    (k_exit,) = [d for d, l in successors(cfg, k_header).items() if l == "false"]
    assert k_exit == j_update
    assert successors(cfg, outer_if)[j_update] == "false"

    # `continue` goes to the k loop's update block.
    assert successors(cfg, inner_if)[k_update] == "false"


def test_every_conditional_has_exactly_true_and_false():
    """Swept across all samples: the invariant that most often broke before."""
    for java_path in SAMPLES:
        cfgs, _ = cfgs_for(java_path)
        for cfg in cfgs:
            for bid, block in cfg.blocks.items():
                if block.kind != CONDITIONAL:
                    continue
                labels = sorted(successors(cfg, bid).values())
                assert labels == ["false", "true"], f"{java_path}:{cfg.method.name}:{bid}"


def test_start_and_end_blocks_are_empty_and_unique():
    for java_path in SAMPLES:
        cfgs, _ = cfgs_for(java_path)
        for cfg in cfgs:
            starts = [b for b in cfg.blocks.values() if b.kind == START]
            ends = [b for b in cfg.blocks.values() if b.kind == END]
            assert len(starts) == 1 and not starts[0].stmts
            assert len(ends) == 1 and not ends[0].stmts
