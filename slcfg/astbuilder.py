"""Parse tree -> AST, as a visitor.

Why a visitor and not a listener: a visitor *returns* nodes, so the caller
decides where a subtree goes. The previous listener had to answer "which body
list does this statement belong to?" from a stack of enclosing constructs plus a
string flag, and got it wrong in several ways -- statements filed into the wrong
branch of an `if`, a `continue` inside an `if` dropped outright, and the
dangling-else grammar variants unhandled. None of those questions arise here:
``visitBlock`` returns a :class:`~slcfg.ast.BlockStmt` and its parent places it.

Conventions that hold throughout:

* A statement visit returns a statement node, a list of them, or None (for an
  empty statement). :meth:`ASTBuilder._statements` flattens that.
* An un-braced substatement is normalized to a single-statement block by
  :meth:`ASTBuilder._as_block`, so ``if (x) y();`` and ``if (x) { y(); }`` build
  the same AST.
* The ``*NoShortIf`` grammar variants are the same constructs with a restricted
  substatement, so they delegate to the same visit methods.
* Statement visits do *not* descend into expressions. Declarations that hide
  inside an expression -- lambda bodies, anonymous class bodies -- are found by
  :meth:`ASTBuilder._scan_nested_declarations` and become their own methods,
  rather than having their statements spliced into the enclosing CFG.
"""

from gen.Java20Parser import Java20Parser
from gen.Java20ParserVisitor import Java20ParserVisitor
from slcfg.ast import (
    AssertStmt,
    AST,
    BasicForStmt,
    BlockStmt,
    BreakStmt,
    CatchClause,
    Class,
    ContinueStmt,
    DeclStmt,
    DoWhileStmt,
    ExpressionStmt,
    Field,
    ForEachStmt,
    IfStmt,
    LabeledStmt,
    Method,
    Pos,
    RawExpr,
    ReturnStmt,
    SwitchCase,
    SwitchStmt,
    SynchronizedStmt,
    ThrowStmt,
    TryStmt,
    WhileStmt,
    YieldStmt,
)
from slcfg.errors import Diagnostics
from slcfg.expressions import ParseExpressionSubTree


class ASTBuilder(Java20ParserVisitor):
    """Builds an :class:`~slcfg.ast.AST` from a ``compilationUnit`` tree."""

    def __init__(self, diagnostics=None):
        self.ast = AST()
        self.diag = Diagnostics() if diagnostics is None else diagnostics
        # Enclosing type names, so a nested class does not clobber its outer one.
        self._type_stack = []
        self._method_stack = []
        self._lambda_counts = {}
        self._anon_count = 0

    def build(self, tree):
        self.visit(tree)
        return self.ast

    # -- helpers ----------------------------------------------------------

    @property
    def _scope(self):
        return ".".join(self._type_stack)

    def _statements(self, ctx):
        """Visit a statement-bearing context and return a flat statement list."""
        if ctx is None:
            return []
        result = self.visit(ctx)
        if result is None:
            return []
        if isinstance(result, list):
            return [s for s in _flatten(result) if s is not None]
        return [result]

    def _as_block(self, ctx):
        """Normalize a substatement (braced or not) into a BlockStmt."""
        if ctx is None:
            return BlockStmt(Pos())
        stmts = self._statements(ctx)
        if len(stmts) == 1 and isinstance(stmts[0], BlockStmt):
            return stmts[0]
        return BlockStmt(Pos.of(ctx), stmts)

    def _declare_method(self, method):
        self.ast.decls.append(method)
        self.ast.scopes[method.qualified_name()] = method
        return method

    # -- compilation unit, packages, types --------------------------------

    def visitPackageDeclaration(self, ctx):
        self.ast.package = ".".join(i.getText() for i in ctx.Identifier())
        return None

    def _visit_type_declaration(self, ctx, name, kind, modifier_ctxs, body_ctx):
        decl = Class(Pos.of(ctx), name, kind)
        decl.modifiers = [m.getText() for m in (modifier_ctxs or [])]

        self._type_stack.append(name)
        # Register before descending, so members see the qualified scope.
        self.ast.scopes[self._scope] = decl
        self.ast.decls.append(decl)
        try:
            if body_ctx is not None:
                self.visit(body_ctx)
        finally:
            self._type_stack.pop()
        return None

    def visitNormalClassDeclaration(self, ctx):
        return self._visit_type_declaration(
            ctx,
            ctx.typeIdentifier().getText(),
            "class",
            ctx.classModifier(),
            ctx.classBody(),
        )

    def visitNormalInterfaceDeclaration(self, ctx):
        return self._visit_type_declaration(
            ctx,
            ctx.typeIdentifier().getText(),
            "interface",
            ctx.interfaceModifier(),
            ctx.interfaceBody(),
        )

    def visitEnumDeclaration(self, ctx):
        return self._visit_type_declaration(
            ctx,
            ctx.typeIdentifier().getText(),
            "enum",
            ctx.classModifier(),
            ctx.enumBody(),
        )

    def visitRecordDeclaration(self, ctx):
        return self._visit_type_declaration(
            ctx,
            ctx.typeIdentifier().getText(),
            "record",
            ctx.classModifier(),
            ctx.recordBody(),
        )

    def visitFieldDeclaration(self, ctx):
        owner = self.ast.scopes.get(self._scope)
        type_text = ctx.unannType().getText()
        for declarator in ctx.variableDeclaratorList().variableDeclarator():
            field = Field(
                Pos.of(declarator),
                declarator.variableDeclaratorId().getText(),
                type_text,
                Field.Type.CLASS_FIELD,
                self._variable_initializer(declarator),
            )
            field.scope = self._scope
            if isinstance(owner, Class):
                owner.fields[field.name] = field
        # A field initializer can hold a lambda or an anonymous class.
        self._scan_nested_declarations(ctx, "<init>")
        return None

    @staticmethod
    def _variable_initializer(declarator):
        init = declarator.variableInitializer()
        if init is None:
            return None
        if init.expression() is not None:
            return ParseExpressionSubTree(init.expression())
        # Array initializer -- source text; it holds no control flow.
        return RawExpr(Pos.of(init), init.arrayInitializer().getText())

    # -- methods, constructors, initializers ------------------------------

    def _build_callable(self, ctx, name, ret_type, params_ctx, body_ctx, is_ctor=False):
        method = Method(Pos.of(ctx), name, ret_type, isConstructor=is_ctor)
        method.scope = self._scope
        method.bodyBlock = BlockStmt(Pos.of(ctx))
        method.bodyBlock.scope = method.qualified_name()

        if params_ctx is not None:
            for param in params_ctx.formalParameter():
                field = self._formal_parameter(param)
                field.scope = method.qualified_name()
                method.params.append(field)
                method.bodyBlock.fields[field.name] = field

        self._declare_method(method)

        # An abstract or interface method has no body (`methodBody: block | ';'`).
        if body_ctx is not None:
            method.hasBody = True
            self._method_stack.append(method)
            try:
                method.bodyBlock.body = self._statements(body_ctx)
                self._scan_nested_declarations(body_ctx, name)
            finally:
                self._method_stack.pop()
        return method

    @staticmethod
    def _formal_parameter(ctx):
        arity = ctx.variableArityParameter()
        if arity is not None:
            return Field(
                Pos.of(ctx),
                arity.Identifier().getText(),
                arity.unannType().getText() + "...",
                Field.Type.PARAM,
                None,
            )
        return Field(
            Pos.of(ctx),
            ctx.variableDeclaratorId().getText(),
            ctx.unannType().getText(),
            Field.Type.PARAM,
            None,
        )

    def visitMethodDeclaration(self, ctx):
        header = ctx.methodHeader()
        declarator = header.methodDeclarator()
        self._build_callable(
            ctx,
            declarator.Identifier().getText(),
            header.result().getText(),
            declarator.formalParameterList(),
            ctx.methodBody().block(),
        )
        return None

    def visitInterfaceMethodDeclaration(self, ctx):
        header = ctx.methodHeader()
        declarator = header.methodDeclarator()
        self._build_callable(
            ctx,
            declarator.Identifier().getText(),
            header.result().getText(),
            declarator.formalParameterList(),
            ctx.methodBody().block(),
        )
        return None

    def visitConstructorDeclaration(self, ctx):
        declarator = ctx.constructorDeclarator()
        self._build_callable(
            ctx,
            declarator.simpleTypeName().getText(),
            "void",
            declarator.formalParameterList(),
            ctx.constructorBody(),
            is_ctor=True,
        )
        return None

    def visitCompactConstructorDeclaration(self, ctx):
        self._build_callable(
            ctx,
            ctx.simpleTypeName().getText(),
            "void",
            None,
            ctx.constructorBody(),
            is_ctor=True,
        )
        return None

    def visitConstructorBody(self, ctx):
        """`'{' explicitConstructorInvocation? blockStatements? '}'`"""
        stmts = []
        explicit = ctx.explicitConstructorInvocation()
        if explicit is not None:
            # `this(...)` / `super(...)`: a call, with no branching of its own.
            pos = Pos.of(explicit)
            stmts.append(ExpressionStmt(pos, RawExpr(pos, explicit.getText())))
        stmts.extend(self._statements(ctx.blockStatements()))
        return stmts

    def visitStaticInitializer(self, ctx):
        self._build_callable(ctx, "<clinit>", "void", None, ctx.block())
        return None

    def visitInstanceInitializer(self, ctx):
        self._build_callable(ctx, "<init>", "void", None, ctx.block())
        return None

    # -- declarations hidden inside expressions ---------------------------

    def _scan_nested_declarations(self, ctx, enclosing_name):
        """Find lambda and anonymous-class bodies inside `ctx`'s expressions.

        Statement visits stop at expression boundaries, so these would otherwise
        be missed entirely. Each becomes its own method with its own CFG. Descent
        stops at every boundary it handles, so a nested lambda is processed by
        the recursive call rather than twice here.
        """
        for i in range(ctx.getChildCount()):
            child = ctx.getChild(i)
            if child.getChildCount() == 0:
                continue

            if isinstance(child, Java20Parser.LambdaExpressionContext):
                self._build_lambda(child, enclosing_name)
                continue

            if isinstance(
                child, Java20Parser.UnqualifiedClassInstanceCreationExpressionContext
            ) and child.classBody() is not None:
                self._build_anonymous_class(child)
                # Constructor arguments may themselves hold lambdas.
                if child.argumentList() is not None:
                    self._scan_nested_declarations(
                        child.argumentList(), enclosing_name
                    )
                continue

            if isinstance(child, Java20Parser.LocalClassOrInterfaceDeclarationContext):
                # Reached through the normal statement path already.
                continue

            if isinstance(child, Java20Parser.SwitchExpressionContext):
                # A switch *expression* carries control flow inside an
                # expression. We render it as text rather than expanding it into
                # branches; say so instead of pretending it is a plain value.
                self.diag.unsupported(
                    Pos.of(child), "switch expression is not expanded into branches"
                )
                self._scan_nested_declarations(child, enclosing_name)
                continue

            self._scan_nested_declarations(child, enclosing_name)

    def _build_lambda(self, ctx, enclosing_name):
        index = self._lambda_counts.get(enclosing_name, 0)
        self._lambda_counts[enclosing_name] = index + 1
        name = f"{enclosing_name}$lambda${index}"

        method = Method(Pos.of(ctx), name, "<lambda>")
        method.scope = self._scope
        method.bodyBlock = BlockStmt(Pos.of(ctx))
        method.bodyBlock.scope = method.qualified_name()
        method.hasBody = True
        self._declare_method(method)

        body = ctx.lambdaBody()
        self._method_stack.append(method)
        try:
            if body.block() is not None:
                method.bodyBlock.body = self._statements(body.block())
            else:
                # `x -> expr` is an implicit return.
                expr_ctx = body.expression()
                method.bodyBlock.body = [
                    ReturnStmt(Pos.of(expr_ctx), ParseExpressionSubTree(expr_ctx))
                ]
            self._scan_nested_declarations(body, name)
        finally:
            self._method_stack.pop()

    def _build_anonymous_class(self, ctx):
        self._anon_count += 1
        base = ctx.classOrInterfaceTypeToInstantiate().getText()
        name = f"{base}$anon{self._anon_count}"

        decl = Class(Pos.of(ctx), name, "anonymous class")
        self._type_stack.append(name)
        try:
            self.ast.scopes[self._scope] = decl
            self.ast.decls.append(decl)
            self.visit(ctx.classBody())
        finally:
            self._type_stack.pop()

    # -- blocks -----------------------------------------------------------

    def visitBlock(self, ctx):
        block = BlockStmt(Pos.of(ctx))
        block.scope = self._scope
        block.body = self._statements(ctx.blockStatements())
        return block

    def visitBlockStatements(self, ctx):
        stmts = []
        for child in ctx.blockStatement():
            stmts.extend(self._statements(child))
        return stmts

    def visitLocalVariableDeclarationStatement(self, ctx):
        return self.visit(ctx.localVariableDeclaration())

    def visitLocalVariableDeclaration(self, ctx):
        """One DeclStmt per declarator: `int a = 1, b = 2;` is two statements."""
        type_text = ctx.localVariableType().getText()
        stmts = []
        for declarator in ctx.variableDeclaratorList().variableDeclarator():
            field = Field(
                Pos.of(declarator),
                declarator.variableDeclaratorId().getText(),
                type_text,
                Field.Type.LOCAL_VAR,
                self._variable_initializer(declarator),
            )
            stmts.append(DeclStmt(Pos.of(declarator), field))
        return stmts

    def visitLocalClassOrInterfaceDeclaration(self, ctx):
        # A local class declares members but contributes no statement to the
        # enclosing flow; its methods become their own CFGs.
        self.visitChildren(ctx)
        return None

    def visitEmptyStatement_(self, ctx):
        return None

    # -- simple statements ------------------------------------------------

    def visitExpressionStatement(self, ctx):
        return ExpressionStmt(
            Pos.of(ctx), ParseExpressionSubTree(ctx.statementExpression())
        )

    def visitReturnStatement(self, ctx):
        return ReturnStmt(Pos.of(ctx), ParseExpressionSubTree(ctx.expression()))

    def visitThrowStatement(self, ctx):
        return ThrowStmt(Pos.of(ctx), ParseExpressionSubTree(ctx.expression()))

    def visitYieldStatement(self, ctx):
        return YieldStmt(Pos.of(ctx), ParseExpressionSubTree(ctx.expression()))

    def visitAssertStatement(self, ctx):
        exprs = ctx.expression()
        message = ParseExpressionSubTree(exprs[1]) if len(exprs) > 1 else None
        return AssertStmt(Pos.of(ctx), ParseExpressionSubTree(exprs[0]), message)

    def visitBreakStatement(self, ctx):
        label = ctx.Identifier()
        return BreakStmt(Pos.of(ctx), label.getText() if label else None)

    def visitContinueStatement(self, ctx):
        label = ctx.Identifier()
        return ContinueStmt(Pos.of(ctx), label.getText() if label else None)

    # -- labels -----------------------------------------------------------

    def visitLabeledStatement(self, ctx):
        return LabeledStmt(
            Pos.of(ctx), ctx.Identifier().getText(), self._as_block(ctx.statement())
        )

    def visitLabeledStatementNoShortIf(self, ctx):
        return LabeledStmt(
            Pos.of(ctx),
            ctx.Identifier().getText(),
            self._as_block(ctx.statementNoShortIf()),
        )

    # -- conditionals -----------------------------------------------------

    def visitIfThenStatement(self, ctx):
        return IfStmt(
            Pos.of(ctx),
            ParseExpressionSubTree(ctx.expression()),
            self._as_block(ctx.statement()),
        )

    def _if_then_else(self, ctx, then_ctx, else_ctx):
        """Build an if/else.

        `else if` needs no special handling: the chained IfStmt is simply the
        only statement in the else block, and the CFG builder recurses.
        """
        return IfStmt(
            Pos.of(ctx),
            ParseExpressionSubTree(ctx.expression()),
            self._as_block(then_ctx),
            self._as_block(else_ctx),
        )

    def visitIfThenElseStatement(self, ctx):
        return self._if_then_else(ctx, ctx.statementNoShortIf(), ctx.statement())

    def visitIfThenElseStatementNoShortIf(self, ctx):
        # Same construct with restricted substatements. Previously unhandled,
        # which let a dangling-else body leak into the enclosing block.
        return self._if_then_else(
            ctx, ctx.statementNoShortIf(0), ctx.statementNoShortIf(1)
        )

    # -- loops ------------------------------------------------------------

    def _while(self, ctx, body_ctx):
        return WhileStmt(
            Pos.of(ctx),
            ParseExpressionSubTree(ctx.expression()),
            self._as_block(body_ctx),
        )

    def visitWhileStatement(self, ctx):
        return self._while(ctx, ctx.statement())

    def visitWhileStatementNoShortIf(self, ctx):
        return self._while(ctx, ctx.statementNoShortIf())

    def visitDoStatement(self, ctx):
        return DoWhileStmt(
            Pos.of(ctx),
            ParseExpressionSubTree(ctx.expression()),
            self._as_block(ctx.statement()),
        )

    def _basic_for(self, ctx, body_ctx):
        pos = Pos.of(ctx)
        cond = ParseExpressionSubTree(ctx.expression())
        if cond is None:
            # `for (;;)`: an always-true header keeps the loop shape uniform
            # instead of special-casing a missing condition downstream.
            cond = RawExpr(pos, "true")

        stmt = BasicForStmt(pos, cond, self._as_block(body_ctx))

        init = ctx.forInit()
        if init is not None:
            if init.localVariableDeclaration() is not None:
                stmt.initStmtList = self._statements(init.localVariableDeclaration())
            else:
                stmt.initStmtList = _expression_statements(init.statementExpressionList())

        update = ctx.forUpdate()
        if update is not None:
            stmt.updateStmtList = _expression_statements(update.statementExpressionList())
        return stmt

    def visitBasicForStatement(self, ctx):
        return self._basic_for(ctx, ctx.statement())

    def visitBasicForStatementNoShortIf(self, ctx):
        return self._basic_for(ctx, ctx.statementNoShortIf())

    def _enhanced_for(self, ctx, body_ctx):
        decl = ctx.localVariableDeclaration()
        declarator = decl.variableDeclaratorList().variableDeclarator(0)
        var = Field(
            Pos.of(declarator),
            declarator.variableDeclaratorId().getText(),
            decl.localVariableType().getText(),
            Field.Type.LOCAL_VAR,
            None,
        )
        return ForEachStmt(
            Pos.of(ctx),
            var,
            ParseExpressionSubTree(ctx.expression()),
            self._as_block(body_ctx),
        )

    def visitEnhancedForStatement(self, ctx):
        return self._enhanced_for(ctx, ctx.statement())

    def visitEnhancedForStatementNoShortIf(self, ctx):
        return self._enhanced_for(ctx, ctx.statementNoShortIf())

    # -- switch -----------------------------------------------------------

    def visitSwitchStatement(self, ctx):
        stmt = SwitchStmt(Pos.of(ctx), ParseExpressionSubTree(ctx.expression()))
        block = ctx.switchBlock()

        # Arrow form: `case X -> ...`, one rule per case, never falls through.
        for rule in block.switchRule():
            stmt.cases.append(self._switch_rule(rule))

        # Colon form: `case X:` groups, which do fall through.
        for group in block.switchBlockStatementGroup():
            stmt.cases.append(self._switch_group(group))

        # Trailing `case X:` labels with no statements after them.
        for label in block.switchLabel():
            labels, is_default = self._switch_labels(label)
            stmt.cases.append(
                SwitchCase(Pos.of(label), labels, BlockStmt(Pos.of(label)), is_default)
            )
        return stmt

    @staticmethod
    def _switch_labels(label_ctx):
        """Return (constants, is_default) for one `switchLabel`."""
        constants = label_ctx.caseConstant()
        if constants:
            return [c.getText() for c in constants], False
        return [], True

    def _switch_rule(self, ctx):
        """`switchLabel '->' (expression ';' | block | throwStatement)`"""
        labels, is_default = self._switch_labels(ctx.switchLabel())
        pos = Pos.of(ctx)

        if ctx.block() is not None:
            body = self._as_block(ctx.block())
        else:
            body = BlockStmt(pos)
            if ctx.throwStatement() is not None:
                body.body = [self.visit(ctx.throwStatement())]
            else:
                # `case X -> expr;`: evaluated for its value or side effect.
                expr_ctx = ctx.expression()
                body.body = [
                    ExpressionStmt(Pos.of(expr_ctx), ParseExpressionSubTree(expr_ctx))
                ]

        return SwitchCase(pos, labels, body, is_default, isArrow=True)

    def _switch_group(self, ctx):
        """`switchLabel ':' (switchLabel ':')* blockStatements`

        Every label in the group is kept. Keying cases by label text -- as the
        old dict-based representation did -- discarded all but the last.
        """
        labels = []
        is_default = False
        for label in ctx.switchLabel():
            constants, default = self._switch_labels(label)
            labels.extend(constants)
            is_default = is_default or default

        body = BlockStmt(Pos.of(ctx), self._statements(ctx.blockStatements()))
        return SwitchCase(Pos.of(ctx), labels, body, is_default, isArrow=False)

    # -- try / synchronized ----------------------------------------------

    def visitTryStatement(self, ctx):
        with_resources = ctx.tryWithResourcesStatement()
        if with_resources is not None:
            return self.visit(with_resources)

        stmt = TryStmt(Pos.of(ctx), self._as_block(ctx.block()))
        self._attach_handlers(stmt, ctx.catches(), ctx.finallyBlock())
        return stmt

    def visitTryWithResourcesStatement(self, ctx):
        stmt = TryStmt(Pos.of(ctx), self._as_block(ctx.block()))
        for resource in ctx.resourceSpecification().resourceList().resource():
            decl = resource.localVariableDeclaration()
            if decl is not None:
                stmt.resources.extend(self._statements(decl))
            else:
                access = resource.variableAccess()
                pos = Pos.of(access)
                stmt.resources.append(ExpressionStmt(pos, RawExpr(pos, access.getText())))
        self._attach_handlers(stmt, ctx.catches(), ctx.finallyBlock())
        return stmt

    def _attach_handlers(self, stmt, catches_ctx, finally_ctx):
        if catches_ctx is not None:
            for clause in catches_ctx.catchClause():
                param = clause.catchFormalParameter()
                stmt.catches.append(
                    CatchClause(
                        Pos.of(clause),
                        [t.getText() for t in _catch_types(param.catchType())],
                        param.variableDeclaratorId().getText(),
                        self._as_block(clause.block()),
                    )
                )
        if finally_ctx is not None:
            stmt.finallyBlock = self._as_block(finally_ctx.block())

    def visitSynchronizedStatement(self, ctx):
        return SynchronizedStmt(
            Pos.of(ctx),
            ParseExpressionSubTree(ctx.expression()),
            self._as_block(ctx.block()),
        )

    # -- fallback ---------------------------------------------------------

    def visitChildren(self, node):
        """Collect every child result rather than only the last one.

        ANTLR's default returns the final child's value, silently discarding
        siblings. The pass-through statement rules (`statement`,
        `blockStatement`, `statementWithoutTrailingSubstatement`, ...) depend on
        this to hand their contents upward intact.
        """
        results = []
        for i in range(node.getChildCount()):
            result = self.visit(node.getChild(i))
            if result is None:
                continue
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)
        if not results:
            return None
        return results[0] if len(results) == 1 else results

    def visitTerminal(self, node):
        return None


def _flatten(items):
    for item in items:
        if isinstance(item, list):
            yield from _flatten(item)
        else:
            yield item


def _expression_statements(list_ctx):
    """Wrap each expression of a `statementExpressionList` as a statement."""
    return [
        ExpressionStmt(Pos.of(e), ParseExpressionSubTree(e))
        for e in list_ctx.statementExpression()
    ]


def _catch_types(catch_type_ctx):
    """`unannClassType ('|' classType)*`"""
    return [catch_type_ctx.unannClassType()] + list(catch_type_ctx.classType())


def build_ast(tree, diagnostics=None):
    return ASTBuilder(diagnostics).build(tree)
