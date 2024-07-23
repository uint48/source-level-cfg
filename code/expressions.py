import re

from antlr4.tree.Tree import TerminalNodeImpl

from code.ast import *
from gen.Java20Parser import Java20Parser


def ParseExpressionSubTree(ctx):
    if ctx is None:
        return None

    # walk down the tree until the child count is not 1.
    # this will make our expression parsing easier.
    while ctx.getChildCount() == 1:
        ctx = ctx.getChild(0)

    # now, based on the type of the context (ctx), we create the related expression,
    # such as BinaryExpr, AssignExpr, or ...

    if type(ctx) == TerminalNodeImpl:
        return ctx.getText()

    if type(ctx) == Java20Parser.ShiftExpressionContext:
        return BinaryExpr(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.getChild(0)),
            ctx.getChild(1).getText() + ctx.getChild(2).getText(),
            ParseExpressionSubTree(ctx.getChild(3)),
        )

    if type(ctx) == Java20Parser.AndExpressionContext:
        return BinaryExpr(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.getChild(0)),
            "&",
            ParseExpressionSubTree(ctx.getChild(2)),
        )

    if type(ctx) == Java20Parser.AssignmentContext:
        return AssignExpr(
            Pos(ctx.start.line, ctx.start.column),
            ctx.getChild(1).getText(),
            ParseExpressionSubTree(ctx.getChild(0)),
            ParseExpressionSubTree(ctx.getChild(2)),
        )

    if type(ctx) == Java20Parser.ConditionalExpressionContext:
        return ConditionalExpr(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.getChild(0)),
            ParseExpressionSubTree(ctx.getChild(2)),
            ParseExpressionSubTree(ctx.getChild(4)),
        )

    if type(ctx) == Java20Parser.MethodInvocationContext:
        try:
            c = CallExpr(
                Pos(ctx.start.line, ctx.start.column),
                ctx.typeName().getText(),
                ctx.Identifier().getText()
            )
        except:
            try:
                c = CallExpr(
                    Pos(ctx.start.line, ctx.start.column),
                    "",
                    ctx.methodName().getText()
                )
            except:
                try:
                    c = CallExpr(
                        Pos(ctx.start.line, ctx.start.column),
                        ctx.primary().getText(),
                        ctx.Identifier().getText()
                    )
                except:
                    if "super." in ctx.getText():
                        c = CallExpr(
                            Pos(ctx.start.line, ctx.start.column),
                            "super",
                            ctx.Identifier().getText()
                        )

        if ctx.argumentList() is not None:
            for arg in ctx.argumentList().expression():
                c.args.append(ParseExpressionSubTree(arg))
        return c

    if type(ctx) == Java20Parser.PrimaryNoNewArrayContext:
        return ctx.getText()

    if type(ctx) == Java20Parser.CastExpression1Context:
        return CastExpr(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.getChild(3)),
            ctx.primitiveType().getText()
        )

    if type(ctx) == Java20Parser.CastExpression2Context:
        return CastExpr(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.getChild(3)),
            ctx.referenceType().getText()
        )

    if type(ctx) == Java20Parser.UnqualifiedClassInstanceCreationExpressionContext:
        try:
            if ctx.getChildCount() == 4:
                return MallocExpr(
                    Pos(ctx.start.line, ctx.start.column),
                    ctx.getChild(1).getText()
                )
            else:
                m = MallocExpr(
                    Pos(ctx.start.line, ctx.start.column),
                    ctx.getChild(1).getText()
                )

                for arg in ctx.argumentList().expression():
                    m.args.append(ParseExpressionSubTree(arg))
                return m
        except:
            return re.sub(r'\([^)]*\)', '', ctx.getText())

    elif ctx.getChildCount() == 2:
        if type(ctx) == Java20Parser.PostfixExpression2Context:
            if ctx.pfE().getText() == "++":
                return UnaryExpr(
                    Pos(ctx.start.line, ctx.start.column),
                    UnaryExpr.Type.POST_INC,
                    ctx.expressionName().getText()
                )
            elif ctx.pfE().getText() == "--":
                u = UnaryExpr(
                    Pos(ctx.start.line, ctx.start.column),
                    UnaryExpr.Type.POST_DEC,
                    ctx.expressionName().getText()
                )
                return u

        elif type(ctx) == Java20Parser.PostIncrementExpressionContext:
            return UnaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                UnaryExpr.Type.POST_INC,
                ParseExpressionSubTree(ctx.getChild(0))
            )

        elif type(ctx) == Java20Parser.PostDecrementExpressionContext:
            return UnaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                UnaryExpr.Type.POST_DEC,
                ParseExpressionSubTree(ctx.getChild(0))
            )

        elif type(ctx) == Java20Parser.UnaryExpression3Context:
            return UnaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                UnaryExpr.Type.POS,
                ParseExpressionSubTree(ctx.getChild(1))
            )

        elif type(ctx) == Java20Parser.UnaryExpression4Context:
            return UnaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                UnaryExpr.Type.NEG,
                ParseExpressionSubTree(ctx.getChild(1))
            )

        elif type(ctx) == Java20Parser.UnaryExpression6Context:
            return UnaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                UnaryExpr.Type.PRE_INC,
                ParseExpressionSubTree(ctx.getChild(1))
            )

        elif type(ctx) == Java20Parser.UnaryExpression7Context:
            return UnaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                UnaryExpr.Type.PRE_DEC,
                ParseExpressionSubTree(ctx.getChild(1))
            )

        elif type(ctx) == Java20Parser.UnaryExpression9Context:
            return UnaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                UnaryExpr.Type.BIT_NOT,
                ParseExpressionSubTree(ctx.getChild(1))
            )

        elif type(ctx) == Java20Parser.UnaryExpression10Context:
            return UnaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                UnaryExpr.Type.LOGIC_NOT,
                ParseExpressionSubTree(ctx.getChild(1))
            )

    elif ctx.getChildCount() == 3:
        if type(ctx) == Java20Parser.StatementExpressionListContext:
            exprList = []
            for expr in ctx.statementExpression():
                exprList.append(ParseExpressionSubTree(expr))
            return exprList
        else:
            return BinaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                ParseExpressionSubTree(ctx.getChild(0)),
                ctx.getChild(1).getText(),
                ParseExpressionSubTree(ctx.getChild(2))
            )
