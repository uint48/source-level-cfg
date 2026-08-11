"""Parse-tree -> expression-AST conversion.

Dispatch is explicit per context type. The previous implementation ended with a
"any 3-child context is a binary expression" fallback, which turned a field
access ``a.b`` into ``a . b`` and a parenthesized expression into nonsense. Here
the fallback is :class:`~slcfg.ast.RawExpr` -- the source text, verbatim --
because rendering the original text is always defensible, whereas inventing an
operator is not.
"""

from antlr4.tree.Tree import TerminalNodeImpl

from gen.Java20Parser import Java20Parser
from slcfg.ast import (
    ArrayAccessExpr,
    AssignExpr,
    BinaryExpr,
    CallExpr,
    CastExpr,
    ConditionalExpr,
    FieldAccessExpr,
    InstanceOfExpr,
    MallocExpr,
    MethodRefExpr,
    ParenExpr,
    Pos,
    RawExpr,
    UnaryExpr,
)

# Left-recursive binary rules: `lhs OP rhs` with the operator as the middle child.
_BINARY_CONTEXTS = (
    Java20Parser.MultiplicativeExpressionContext,
    Java20Parser.AdditiveExpressionContext,
    Java20Parser.EqualityExpressionContext,
    Java20Parser.AndExpressionContext,
    Java20Parser.ExclusiveOrExpressionContext,
    Java20Parser.InclusiveOrExpressionContext,
    Java20Parser.ConditionalAndExpressionContext,
    Java20Parser.ConditionalOrExpressionContext,
)

_PREFIX_UNARY_CONTEXTS = {
    Java20Parser.UnaryExpression3Context: UnaryExpr.Type.POS,
    Java20Parser.UnaryExpression4Context: UnaryExpr.Type.NEG,
    Java20Parser.UnaryExpression6Context: UnaryExpr.Type.PRE_INC,
    Java20Parser.UnaryExpression7Context: UnaryExpr.Type.PRE_DEC,
    Java20Parser.UnaryExpression9Context: UnaryExpr.Type.BIT_NOT,
    Java20Parser.UnaryExpression10Context: UnaryExpr.Type.LOGIC_NOT,
}


def ParseExpressionSubTree(ctx):
    """Convert an expression subtree to an AST node.

    Returns None only when `ctx` is None; every other input yields a node, so
    callers never have to guard against a silently dropped expression.
    """
    if ctx is None:
        return None

    # Collapse single-child chains (`expression` -> `assignmentExpression` ->
    # `conditionalExpression` -> ... ) down to the node that does something.
    while ctx.getChildCount() == 1 and not isinstance(ctx, TerminalNodeImpl):
        ctx = ctx.getChild(0)

    if isinstance(ctx, TerminalNodeImpl):
        return RawExpr(Pos(ctx.symbol.line, ctx.symbol.column), ctx.getText())

    pos = Pos.of(ctx)

    # --- statement expression lists (`for` update clauses, comma expressions)
    if isinstance(ctx, Java20Parser.StatementExpressionListContext):
        return [ParseExpressionSubTree(e) for e in ctx.statementExpression()]

    # --- assignment
    if isinstance(ctx, Java20Parser.AssignmentContext):
        return AssignExpr(
            pos,
            ctx.assignmentOperator().getText(),
            ParseExpressionSubTree(ctx.leftHandSide()),
            ParseExpressionSubTree(ctx.expression()),
        )

    # --- ternary
    if isinstance(ctx, Java20Parser.ConditionalExpressionContext):
        return ConditionalExpr(
            pos,
            ParseExpressionSubTree(ctx.getChild(0)),
            ParseExpressionSubTree(ctx.getChild(2)),
            ParseExpressionSubTree(ctx.getChild(4)),
        )

    # --- shift: `<<` and `>>` are two tokens, `>>>` is three.
    if isinstance(ctx, Java20Parser.ShiftExpressionContext):
        n = ctx.getChildCount()
        op_tokens = n - 2  # everything between lhs and rhs
        op = "".join(ctx.getChild(1 + i).getText() for i in range(op_tokens))
        return BinaryExpr(
            pos,
            ParseExpressionSubTree(ctx.getChild(0)),
            op,
            ParseExpressionSubTree(ctx.getChild(n - 1)),
        )

    # --- relational, which also carries `instanceof`
    if isinstance(ctx, Java20Parser.RelationalExpressionContext):
        if ctx.getChild(1).getText() == "instanceof":
            target = ctx.getChild(2)
            if isinstance(target, Java20Parser.PatternContext):
                # `x instanceof T t` -- a type pattern binds a name.
                decl = target.typePattern().localVariableDeclaration()
                type_text = decl.localVariableType().getText()
                binding = decl.variableDeclaratorList().getText()
                return InstanceOfExpr(
                    pos, ParseExpressionSubTree(ctx.getChild(0)), type_text, binding
                )
            return InstanceOfExpr(
                pos, ParseExpressionSubTree(ctx.getChild(0)), target.getText()
            )
        return BinaryExpr(
            pos,
            ParseExpressionSubTree(ctx.getChild(0)),
            ctx.getChild(1).getText(),
            ParseExpressionSubTree(ctx.getChild(2)),
        )

    if isinstance(ctx, _BINARY_CONTEXTS):
        return BinaryExpr(
            pos,
            ParseExpressionSubTree(ctx.getChild(0)),
            ctx.getChild(1).getText(),
            ParseExpressionSubTree(ctx.getChild(2)),
        )

    # --- unary
    unary_op = _PREFIX_UNARY_CONTEXTS.get(type(ctx))
    if unary_op is not None:
        return UnaryExpr(pos, unary_op, ParseExpressionSubTree(ctx.getChild(1)))

    if isinstance(ctx, Java20Parser.PostIncrementExpressionContext):
        return UnaryExpr(
            pos, UnaryExpr.Type.POST_INC, ParseExpressionSubTree(ctx.getChild(0))
        )

    if isinstance(ctx, Java20Parser.PostDecrementExpressionContext):
        return UnaryExpr(
            pos, UnaryExpr.Type.POST_DEC, ParseExpressionSubTree(ctx.getChild(0))
        )

    # `postfixExpression` folds `x++` / `x--` into a trailing `pfE` chain.
    if isinstance(
        ctx,
        (Java20Parser.PostfixExpression1Context, Java20Parser.PostfixExpression2Context),
    ):
        return _parse_postfix(ctx, pos)

    # --- casts
    if isinstance(ctx, Java20Parser.CastExpression1Context):
        return CastExpr(
            pos,
            ParseExpressionSubTree(ctx.unaryExpression()),
            ctx.primitiveType().getText(),
        )

    if isinstance(
        ctx,
        (Java20Parser.CastExpression2Context, Java20Parser.CastExpression3Context),
    ):
        return CastExpr(
            pos,
            ParseExpressionSubTree(ctx.getChild(ctx.getChildCount() - 1)),
            ctx.referenceType().getText(),
        )

    # --- calls and allocation
    if isinstance(ctx, Java20Parser.MethodInvocationContext):
        return _parse_method_invocation(ctx, pos)

    if isinstance(
        ctx, Java20Parser.UnqualifiedClassInstanceCreationExpressionContext
    ):
        malloc = MallocExpr(pos, ctx.classOrInterfaceTypeToInstantiate().getText())
        if ctx.argumentList() is not None:
            malloc.args = [
                ParseExpressionSubTree(a) for a in ctx.argumentList().expression()
            ]
        return malloc

    if isinstance(ctx, Java20Parser.ArrayCreationExpressionWithoutInitializerContext):
        type_text = (
            ctx.primitiveType() or ctx.classType()
        ).getText()
        return MallocExpr(pos, type_text, dims=ctx.dimExprs().getText())

    if isinstance(ctx, Java20Parser.ArrayCreationExpressionWithInitializerContext):
        type_text = (
            ctx.primitiveType() or ctx.classOrInterfaceType()
        ).getText()
        return MallocExpr(
            pos, type_text, dims=ctx.dims().getText() + ctx.arrayInitializer().getText()
        )

    # --- selections
    if isinstance(ctx, Java20Parser.FieldAccessContext):
        return FieldAccessExpr(
            pos,
            ParseExpressionSubTree(ctx.getChild(0)),
            ctx.Identifier().getText(),
        )

    if isinstance(ctx, Java20Parser.ArrayAccessContext):
        return ArrayAccessExpr(
            pos,
            ParseExpressionSubTree(ctx.getChild(0)),
            ParseExpressionSubTree(ctx.expression()),
        )

    if isinstance(ctx, Java20Parser.MethodReferenceContext):
        return MethodRefExpr(pos, ctx.getText())

    # A lambda's body gets its own CFG as a pseudo-method, so inlining its source
    # here would duplicate it into the enclosing block. Keep the parameters --
    # they identify the lambda -- and elide a block body.
    if isinstance(ctx, Java20Parser.LambdaExpressionContext):
        params = ctx.lambdaParameters().getText()
        body = ctx.lambdaBody()
        if body.block() is not None:
            return RawExpr(pos, f"{params} -> {{...}}")
        return RawExpr(pos, f"{params} -> {body.expression().getText()}")

    # `( expression )` is the only primaryNoNewArray shape worth structuring;
    # everything else in that rule renders fine as source text.
    if isinstance(ctx, Java20Parser.PrimaryNoNewArrayContext):
        if (
            ctx.getChildCount() == 3
            and ctx.getChild(0).getText() == "("
            and ctx.getChild(2).getText() == ")"
        ):
            return ParenExpr(pos, ParseExpressionSubTree(ctx.getChild(1)))
        return RawExpr(pos, ctx.getText())

    # Anything else -- names, literals, lambdas, switch expressions, class
    # literals, chained postfix -- keeps its source text.
    return RawExpr(pos, ctx.getText())


def _parse_postfix(ctx, pos):
    """Handle `primary pfE?` / `expressionName pfE?`.

    A `pfE` chain is a run of `++`/`--` applied left to right.
    """
    base = ParseExpressionSubTree(ctx.getChild(0))
    tail = ctx.pfE()
    while tail is not None:
        op = (
            UnaryExpr.Type.POST_INC
            if tail.getChild(0).getText() == "++"
            else UnaryExpr.Type.POST_DEC
        )
        base = UnaryExpr(pos, op, base)
        tail = tail.pfE()
    return base


def _parse_method_invocation(ctx, pos):
    """Build a CallExpr for any of `methodInvocation`'s six alternatives.

    The qualifier is whatever precedes the final `.Identifier(...)`; the
    unqualified alternative (`methodName(...)`) has none. This replaces a chain
    of nested try/except blocks that could leave the result unbound -- an
    UnboundLocalError that the old caller swallowed, dropping the call entirely.
    """
    if ctx.methodName() is not None:
        # `methodName '(' argumentList? ')'` -- unqualified.
        call = CallExpr(pos, "", ctx.methodName().getText())
    else:
        # Every other alternative ends in `Identifier '(' argumentList? ')'`.
        # The qualifier is the text before that identifier.
        identifier = ctx.Identifier()
        name = identifier.getText() if identifier is not None else ctx.getText()

        qualifier_parts = []
        for i in range(ctx.getChildCount()):
            child = ctx.getChild(i)
            if child is identifier:
                break
            if isinstance(child, Java20Parser.TypeArgumentsContext):
                continue
            text = child.getText()
            if text not in (".", "::"):
                qualifier_parts.append(text)
        call = CallExpr(pos, ".".join(p for p in qualifier_parts if p), name)

    if ctx.argumentList() is not None:
        call.args = [ParseExpressionSubTree(a) for a in ctx.argumentList().expression()]
    return call
