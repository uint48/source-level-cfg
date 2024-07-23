import uuid

from code.ast import *
from code.cfg import SourceLevelCFG
from code.expressions import ParseExpressionSubTree
from gen.Java20Parser import Java20Parser
from gen.Java20ParserListener import Java20ParserListener
from antlr4.error.ErrorListener import ErrorListener


class MyErrorListener(ErrorListener):
    """
    This class is an error listener that raises an exception when a syntax error is encountered.
    """

    def __init__(self):
        super(MyErrorListener, self).__init__()

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise Exception("Syntax error: " + "line " + str(line) + ":" + str(column) + " " + msg)


class WalkerState:
    def __init__(self):
        """
        This class is responsible for maintaining the state of the walker.
        It keeps track of the current class, current method, current switch case, and the stack of statements.
        """
        self.CurrentClass = None
        self.CurrentMethod = None
        self.CurrentSwitchCase = None
        self.StmtStack = []


class ASTListener(Java20ParserListener):
    def __init__(self,output_dir):
        self.output_dir = output_dir
        self.ast = AST()
        self.state = WalkerState()

    def popStmtStack(self):
        # this method attempts to pop the last statement from the stack.
        # depending on the type and situation,
        # it either sets the scope and fields or appends the top of the stack statement
        # to the body of the current method, switch case, or any other relevant bodies.

        # if no stmts on stack, do nothing
        if len(self.state.StmtStack) == 0:
            return
        else:
            try:
                # pop last stmt
                ss = self.state.StmtStack.pop()

                # last stmts on stack should pop and add to current method body
                if len(self.state.StmtStack) == 0:
                    self.state.CurrentMethod.bodyBlock.body.append(ss)
                    return

                # get last stmt in stack
                topOfStack = self.state.StmtStack[-1]

                if type(ss) == BlockStmt:
                    # if it's a block stmt and it's inside a for stmt:
                    if type(topOfStack) == BasicForStmt:
                        # add block stmts to for stmt body
                        topOfStack.bodyBlock.body.extend(ss.body)
                        # set scope of block stmt to for stmt body
                        topOfStack.bodyBlock.scope = ss.scope
                        # merge fields of block stmt and for stmt and set the result to for stmt body
                        tmp = topOfStack.bodyBlock.fields
                        topOfStack.bodyBlock.fields = {**tmp, **ss.fields}

                    # if it's a block stmt and it's inside a switch stmt:
                    elif type(topOfStack) == SwitchStmt:
                        # add block stmts to current switch case body
                        topOfStack.caseBlocks[self.state.CurrentSwitchCase].body = ss.body
                        # set scope of block stmt to current switch case body
                        topOfStack.caseBlocks[self.state.CurrentSwitchCase].scope = ss.scope
                        # merge fields of block stmt and current switch case and set the result to current switch case
                        tmp = topOfStack.caseBlocks[self.state.CurrentSwitchCase].fields
                        topOfStack.caseBlocks[self.state.CurrentSwitchCase].fields = {**tmp, **ss.fields}

                    elif type(topOfStack) == BlockStmt:
                        # if it's a block stmt and it's inside another block stmt add it to parent body block
                        topOfStack.body.append(ss)

                    # if it's a block stmt and it's inside an if stmt:
                    elif type(topOfStack) == IfStmt:
                        if topOfStack.currentBlock == "bodyBlock":
                            topOfStack.bodyBlock.body = ss.body
                            topOfStack.bodyBlock.scope = ss.scope
                            tmp = topOfStack.bodyBlock.fields
                            topOfStack.bodyBlock.fields = {**tmp, **ss.fields}
                        else:
                            topOfStack.elseBlock.body = ss.body
                            topOfStack.elseBlock.scope = ss.scope
                            tmp = topOfStack.elseBlock.fields
                            topOfStack.elseBlock.fields = {**tmp, **ss.fields}

                    elif type(topOfStack) == WhileStmt:
                        topOfStack.bodyBlock.body = ss.body
                        topOfStack.bodyBlock.scope = ss.scope
                        tmp = topOfStack.bodyBlock.fields
                        topOfStack.bodyBlock.fields = {**tmp, **ss.fields}

                    elif type(topOfStack) == DoWhileStmt:
                        topOfStack.bodyBlock.body = ss.body
                        topOfStack.bodyBlock.scope = ss.scope
                        tmp = topOfStack.bodyBlock.fields
                        topOfStack.bodyBlock.fields = {**tmp, **ss.fields}

                    return

                # if it's not a block stmt, add topOfStack to related body block

                if type(topOfStack) == BlockStmt:
                    topOfStack.body.append(ss)

                elif type(topOfStack) == BasicForStmt:
                    topOfStack.bodyBlock.body.append(ss)

                if type(topOfStack) == SwitchStmt:
                    topOfStack.caseBlocks[self.state.CurrentSwitchCase].body.append(ss)

                elif type(topOfStack) == IfStmt:
                    if topOfStack.currentBlock == "bodyBlock":
                        topOfStack.bodyBlock.body.append(ss)
                    else:
                        topOfStack.elseBlock.body.append(ss)

                elif type(topOfStack) == WhileStmt:
                    topOfStack.bodyBlock.body.append(ss)

                elif type(topOfStack) == DoWhileStmt:
                    topOfStack.bodyBlock.body.append(ss)
            except:
                pass

    def enterExpressionStatement(self, ctx: Java20Parser.ExpressionStatementContext):
        exprStmt = ExpressionStmt(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.statementExpression())
        )

        # if the stmt stack is empty the related body block is the current method body block
        if len(self.state.StmtStack) == 0:
            try:
                relatedBodyBlock = self.state.CurrentMethod.bodyBlock.body
                relatedBodyBlock.append(exprStmt)
            except:
                pass

        else:
            topOfStack = self.state.StmtStack[-1]

            # if walker is inside a block stmt the related body block is the block stmt body
            if type(topOfStack) == BlockStmt:
                relatedBodyBlock = topOfStack.body

            # if walker is inside a switch stmt the related body block is the current switch case body block
            elif type(topOfStack) == SwitchStmt:
                relatedBodyBlock = topOfStack.caseBlocks[self.state.CurrentSwitchCase].body

            # if walker is inside a for stmt the related body block is the for stmt body block
            elif type(topOfStack) == BasicForStmt:
                relatedBodyBlock = topOfStack.bodyBlock.body

            # if walker is inside a if stmt the related body block is the if stmt body block
            elif type(topOfStack) == IfStmt:
                # if stmt current block is body block, the related body block is the if stmt body block
                if topOfStack.currentBlock == "":
                    relatedBodyBlock = topOfStack.bodyBlock.body
                else:
                    # if stmt current block is else block, the related body block is the else body block
                    relatedBodyBlock = topOfStack.elseBlock.body

            # if walker is inside a while stmt the related body block is the while stmt body block
            elif type(topOfStack) == WhileStmt:
                relatedBodyBlock = topOfStack.bodyBlock.body

            # if walker is inside a do while stmt the related body block is the do while stmt body block
            elif type(topOfStack) == DoWhileStmt:
                relatedBodyBlock = topOfStack.bodyBlock.body

            # at the end append expr stmt to related body block
            relatedBodyBlock.append(exprStmt)

    def enterReturnStatement(self, ctx: Java20Parser.ReturnStatementContext):
        retStmt = ReturnStmt(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.expression())
        )

        # if the stmt stack is empty, the walker is in method root body block
        if len(self.state.StmtStack) == 0:
            relatedBodyBlock = self.state.CurrentMethod.bodyBlock.body
            relatedBodyBlock.append(retStmt)
        else:
            topOfStack = self.state.StmtStack[-1]

            # In Java, the return statement is not always required to be within a block statement,
            # but it depends on the context.

            if type(topOfStack) == SwitchStmt:
                relatedBodyBlock = topOfStack.caseBlocks[self.state.CurrentSwitchCase].body
                relatedBodyBlock.append(retStmt)
            elif type(topOfStack) == IfStmt:
                if topOfStack.currentBlock == "bodyBlock":
                    relatedBodyBlock = topOfStack.bodyBlock.body
                else:
                    # if stmt current block is else block, the related body block is the else body block
                    relatedBodyBlock = topOfStack.elseBlock.body
                relatedBodyBlock.append(retStmt)
            else:
                relatedBodyBlock = topOfStack.body
                relatedBodyBlock.append(retStmt)

    def enterBreakStatement(self, ctx: Java20Parser.BreakStatementContext):

        # a 'break' statement should always be within a loop or an inner labeled statement,
        # and therefore, it cannot be added to the method's root body block.

        topOfStack = self.state.StmtStack[-1]
        brkStmt = BreakStmt(Pos(ctx.start.line, ctx.start.column))

        if type(topOfStack) == SwitchStmt:
            relatedBodyBlock = topOfStack.caseBlocks[self.state.CurrentSwitchCase].body
        elif type(topOfStack) == IfStmt:
            if topOfStack.currentBlock == "bodyBlock":
                relatedBodyBlock = topOfStack.bodyBlock.body
            else:
                relatedBodyBlock = topOfStack.elseBlock.body
        else:
            relatedBodyBlock = topOfStack.body

        relatedBodyBlock.append(brkStmt)

    def enterContinueStatement(self, ctx: Java20Parser.ContinueStatementContext):

        # a 'continue' statement should always be within a loop or an inner labeled statement,
        # and therefore, it cannot be added to the method's root body block.

        topOfStack = self.state.StmtStack[-1]
        continueStmt = ContinueStmt(Pos(ctx.start.line, ctx.start.column))
        if  type(topOfStack) == IfStmt:
            if topOfStack.currentBlock == "bodyBlock":
                relatedBodyBlock = topOfStack.bodyBlock.body
            else:
                relatedBodyBlock = topOfStack.elseBlock.body

        else:
            relatedBodyBlock = topOfStack.body
            relatedBodyBlock.append(continueStmt)

    def enterPackageDeclaration(self, ctx: Java20Parser.PackageDeclarationContext):
        packageName = ctx.Identifier(0).getText()
        self.ast.package = packageName

    def enterNormalClassDeclaration(self, ctx: Java20Parser.NormalClassDeclarationContext):
        # get class name while entering class declaration on tree
        className = ctx.typeIdentifier().getText()

        # initialize a 'Class' object and assign it to the 'WalkerState' current class field.
        self.state.CurrentClass = Class(
            Pos(ctx.start.line, ctx.start.column),
            className
        )

        # iterate through all the class modifiers and add them to the 'Class' modifiers
        for m in ctx.classModifier():
            self.state.CurrentClass.modifiers.append(m.getText())

        # add current class to AST scopes
        self.ast.scopes[className] = self.state.CurrentClass

    def exitClassDeclaration(self, ctx: Java20Parser.ClassDeclarationContext):
        # after exiting class declaration in syntax tree, add the class to the AST declaration list.
        self.ast.decls.append(self.state.CurrentClass)

        # and the 'WalkerState' current class field needs to be set to 'None' to avoid bugs.
        self.state.CurrentClass = None

    def enterMethodDeclaration(self, ctx: Java20Parser.MethodDeclarationContext):
        # get method name and return type
        methodName = ctx.methodHeader().methodDeclarator().Identifier().getText()
        returnType = ctx.methodHeader().result().getText()

        # initialize a 'Method' object and assign it to the 'WalkerState' current method field.
        self.state.CurrentMethod = Method(
            Pos(ctx.start.line, ctx.start.column),
            methodName,
            returnType
        )

        self.state.CurrentMethod.bodyBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )

        # set scope of current method to it's class
        try:
            self.state.CurrentMethod.scope = self.state.CurrentClass.name
        except:
            pass

    def exitMethodDeclaration(self, ctx: Java20Parser.MethodDeclarationContext):
        # after exiting method declaration in syntax tree, add the method to the AST declaration list.
        self.ast.decls.append(self.state.CurrentMethod)
        self.state.CurrentMethod = None

    def enterConstructorDeclaration(self, ctx:Java20Parser.ConstructorDeclarationContext):
        # get method name and return type
        methodName = ctx.constructorDeclarator().getText()
        returnType = "void"

        # initialize a 'Method' object and assign it to the 'WalkerState' current method field.
        self.state.CurrentMethod = Method(
            Pos(ctx.start.line, ctx.start.column),
            methodName,
            returnType
        )

        self.state.CurrentMethod.bodyBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )

        # set scope of current method to it's class
        try:
            self.state.CurrentMethod.scope = self.state.CurrentClass.name
        except:
            pass

    def exitConstructorDeclaration(self, ctx:Java20Parser.ConstructorDeclarationContext):
        # after exiting method declaration in syntax tree, add the method to the AST declaration list.
        self.ast.decls.append(self.state.CurrentMethod)
        self.state.CurrentMethod = None

    def enterFieldDeclaration(self, ctx: Java20Parser.FieldDeclarationContext):
        fieldType = ctx.unannType().getText()

        for i in ctx.variableDeclaratorList().variableDeclarator():
            f = Field(
                Pos(i.start.line, i.start.column),
                i.variableDeclaratorId().getText(),
                fieldType,
                Field.Type.CLASS_FIELD,
                None
            )

            try:
                f.scope = self.state.CurrentClass.name
                if i.variableInitializer() is not None:
                    f.expr = ParseExpressionSubTree(i.variableInitializer().expression())

                self.state.CurrentClass.fields[f.name] = f
            except:
                pass

    def enterLocalVariableDeclaration(self, ctx: Java20Parser.LocalVariableDeclarationContext):
        fieldType = ctx.localVariableType().getText()

        for i in ctx.variableDeclaratorList().variableDeclarator():
            f = Field(
                Pos(i.start.line, i.start.column),
                i.variableDeclaratorId().getText(),
                fieldType,
                Field.Type.LOCAL_VAR,
                None
            )

            if i.variableInitializer() is not None:
                if type(i.variableInitializer().getChild(0)) == Java20Parser.ExpressionContext:
                    f.expr = ParseExpressionSubTree(i.variableInitializer().expression())
                elif type(i.variableInitializer().getChild(0)) == Java20Parser.ArrayInitializerContext:
                    f.expr = i.variableInitializer().arrayInitializer().getText()

            ds = DeclStmt(
                Pos(i.start.line, i.start.column),
                f
            )

            if len(self.state.StmtStack) == 0:
                f.scope = self.state.CurrentMethod.name
                self.state.CurrentMethod.bodyBlock.fields[f.name] = f
                self.state.CurrentMethod.bodyBlock.body.append(ds)

            else:
                topOfStack = self.state.StmtStack[-1]
                if type(topOfStack) == BlockStmt:
                    f.scope = topOfStack.scope
                    topOfStack.fields[f.name] = f
                    topOfStack.body.append(ds)

                elif type(topOfStack) == BasicForStmt:
                    # if decl stmt is in for init then add it to for init stmt list
                    # else add it to for body
                    if type(ctx.parentCtx) == Java20Parser.ForInitContext:
                        f.scope = topOfStack.bodyBlock.scope
                        topOfStack.bodyBlock.fields[f.name] = f
                        topOfStack.initStmtList.append(ds)
                    elif type(ctx.parentCtx) == Java20Parser.EnhancedForStatementContext:
                        # enhanced for loops are replaced with basic for loops, so this section will be empty.
                        return
                    else:
                        f.scope = topOfStack.bodyBlock.scope
                        topOfStack.bodyBlock.fields[f.name] = f
                        topOfStack.bodyBlock.body.append(ds)

                # if the walker is inside an If statement, the scope of field should be
                # the scope of the If statement (body or else block).
                elif type(topOfStack) == IfStmt:
                    if topOfStack.currentBlock == "bodyBlock":
                        f.scope = topOfStack.bodyBlock.scope
                        topOfStack.bodyBlock.fields[f.name] = f
                        topOfStack.bodyBlock.pos = Pos(i.start.line, i.start.column)
                        topOfStack.bodyBlock.body.append(ds)
                    else:
                        f.scope = topOfStack.elseBlock.scope
                        topOfStack.elseBlock.fields[f.name] = f
                        topOfStack.elseBlock.pos = Pos(i.start.line, i.start.column)
                        topOfStack.elseBlock.body.append(ds)

                # if the walker is inside a while statement, the scope of field should be
                # the scope of the while statement.
                elif type(topOfStack) == WhileStmt:
                    f.scope = topOfStack.bodyBlock.scope
                    topOfStack.bodyBlock.fields[f.name] = f
                    topOfStack.bodyBlock.pos = Pos(i.start.line, i.start.column)
                    topOfStack.bodyBlock.body.append(ds)

                # if the walker is inside a do while statement, the scope of field should be
                # the scope of the do while statement.
                elif type(topOfStack) == DoWhileStmt:
                    f.scope = topOfStack.bodyBlock.scope
                    topOfStack.bodyBlock.fields[f.name] = f
                    topOfStack.bodyBlock.pos = Pos(i.start.line, i.start.column)
                    topOfStack.bodyBlock.body.append(ds)

                # if the walker is inside a switch statement, the scope of field should be
                # the scope of the current switch case.
                elif type(topOfStack) == SwitchStmt:
                    f.scope = topOfStack.caseBlocks[self.state.CurrentSwitchCase].scope
                    topOfStack.caseBlocks[self.state.CurrentSwitchCase].fields[f.name] = f
                    topOfStack.caseBlocks[self.state.CurrentSwitchCase].pos = Pos(i.start.line, i.start.column)
                    topOfStack.caseBlocks[self.state.CurrentSwitchCase].body.append(ds)

    def enterFormalParameter(self, ctx: Java20Parser.FormalParameterContext):
        paramType = ctx.unannType().getText()
        paramName = ctx.variableDeclaratorId().getText()

        f = Field(
            Pos(ctx.start.line, ctx.start.column),
            paramName,
            paramType,
            Field.Type.PARAM,
            None
        )

        try:
            f.scope = self.state.CurrentMethod.name
            self.state.CurrentMethod.bodyBlock.fields[paramName] = f
        except:
            pass

    def enterBlock(self, ctx: Java20Parser.BlockContext):
        # if we enter a block and the parent context was MethodBodyContext
        # then we are in a method body
        if type(ctx.parentCtx) == Java20Parser.MethodBodyContext:
            self.state.CurrentMethod.bodyBlock.pos = Pos(ctx.start.line, ctx.start.column)
            self.state.CurrentMethod.bodyBlock.scope = self.state.CurrentMethod.name
            self.ast.scopes[self.state.CurrentMethod.name] = self.state.CurrentMethod.bodyBlock
        else:
            # else if we enter a block and the parent context was not MethodBodyContext
            if len(self.state.StmtStack) != 0:
                # if the top of the statement stack is an IfStmt,
                # then we should decide and switch between bodyBlock and elseBlock
                # for further operations.
                topOfStack = self.state.StmtStack[-1]
                if type(topOfStack) == IfStmt:
                    if topOfStack.currentBlock == "":
                        topOfStack.currentBlock = "bodyBlock"
                    else:
                        topOfStack.currentBlock = "elseBlock"

            blockStmt = BlockStmt(
                Pos(ctx.start.line, ctx.start.column)
            )

            # create new scope
            blockStmt.scope = str(uuid.uuid4())
            self.ast.scopes[blockStmt.scope] = blockStmt

            # append block stmt to stack
            self.state.StmtStack.append(blockStmt)

    def exitBlock(self, ctx: Java20Parser.BlockContext):
        # run generic stmt stack pop method
        self.popStmtStack()

    def enterBasicForStatement(self, ctx: Java20Parser.BasicForStatementContext):

        # create new basic 'for' stmt object
        basicForStmt = BasicForStmt(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.expression())
        )

        # initiate the body of the basic 'for' statement
        basicForStmt.bodyBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )

        # if for loop condition loop is empty then set it to an always true condition like 0==0
        # and the for loop os equivalent to while(true) loop.
        if basicForStmt.condExpr is None:
            basicForStmt.condExpr = BinaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                "0",
                "==",
                "0",
            )

        basicForStmt.updateStmtList = ParseExpressionSubTree(ctx.forUpdate())

        # if for loop update stmt is not a list then wrap it in a list
        if type(basicForStmt.updateStmtList) != list and basicForStmt.updateStmtList is not None:
            basicForStmt.updateStmtList = [basicForStmt.updateStmtList]

        else:
            # if for loop update stmt is None then set it to an empty list
            if basicForStmt.updateStmtList is None:
                basicForStmt.updateStmtList = []

        self.state.StmtStack.append(basicForStmt)

    def exitBasicForStatement(self, ctx: Java20Parser.BasicForStatementContext):
        # run generic stmt stack pop method
        self.popStmtStack()

    def enterEnhancedForStatement(self, ctx: Java20Parser.EnhancedForStatementContext):
        # here we convert the enhanced for loop into a basic 'for' loop

        # initiate the basic for loop; its condition expression will be filled in next.
        basicForStmt = BasicForStmt(
            Pos(ctx.start.line, ctx.start.column),
            None
        )

        # initiate the body
        basicForStmt.bodyBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )

        fieldType = ctx.localVariableDeclaration().localVariableType().getText()
        for v in ctx.localVariableDeclaration().variableDeclaratorList().variableDeclarator():
            # in fact, the enhanced 'for' in Java grammar should have only one variable declarator
            # however, the ANTLR grammar has this bug. After the first iteration of this loop, we break it.

            initVar = Field(
                Pos(v.start.line, v.start.column),
                v.variableDeclaratorId().getText(),
                fieldType,
                Field.Type.LOCAL_VAR,
                None
            )

            # add init variable to scope of 'for' loop body
            basicForStmt.bodyBlock.fields[initVar.name] = initVar

            counterVar = Field(
                Pos(v.start.line, v.start.column),
                "_" + str(uuid.uuid4())[:8],
                "int",
                Field.Type.LOCAL_VAR,
                "0"
            )

            iterableVar = ctx.expression().getText()

            basicForStmt.condExpr = BinaryExpr(
                Pos(ctx.start.line, ctx.start.column),
                counterVar.name,
                "<",
                iterableVar + ".length"
            )

            # add counter variable to scope of 'for' loop body
            basicForStmt.bodyBlock.fields[counterVar.name] = counterVar

            # append loop counter variable decl stmt to 'for' stmt init list
            basicForStmt.initStmtList.append(
                DeclStmt(
                    Pos(v.start.line, v.start.column),
                    counterVar
                )
            )

            # append loop init variable decl to 'for' stmt init list
            basicForStmt.initStmtList.append(
                DeclStmt(
                    Pos(v.start.line, v.start.column),
                    initVar
                )
            )

            # append loop counter increment expr to 'for' stmt update list
            basicForStmt.updateStmtList.append(
                ExpressionStmt(
                    Pos(v.start.line, v.start.column),
                    UnaryExpr(
                        Pos(v.start.line, v.start.column),
                        UnaryExpr.Type.POST_INC,
                        counterVar.name
                    )
                )
            )

            # append the loop initialization variable assignment to the 'for' statement's body.
            # assign the first member of the array (iterable) to the initialization variable.
            basicForStmt.bodyBlock.body.append(
                ExpressionStmt(
                    Pos(v.start.line, v.start.column),
                    BinaryExpr(
                        Pos(v.start.line, v.start.column),
                        initVar.name,
                        "=",
                        iterableVar + "[" + counterVar.name + "]"
                    )
                )
            )

            break

        # at end we append the 'for' stmt to the stack
        self.state.StmtStack.append(basicForStmt)

    def exitEnhancedForStatement(self, ctx: Java20Parser.EnhancedForStatementContext):
        # run generic stmt stack pop method
        self.popStmtStack()

    def enterIfThenStatement(self, ctx: Java20Parser.IfThenStatementContext):
        # create new if stmt and push it on the stack
        ifStmt = IfStmt(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.expression()),
        )

        # initiate the body
        ifStmt.bodyBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )

        # initiate the else body
        ifStmt.elseBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )
        ifStmt.hasElif = False

        self.state.StmtStack.append(ifStmt)

    def exitIfThenStatement(self, ctx: Java20Parser.IfThenStatementContext):
        # run generic stmt stack pop method
        self.popStmtStack()

    def enterIfThenElseStatement(self, ctx: Java20Parser.IfThenElseStatementContext):
        # create new if stmt and push it on the stack
        ifStmt = IfStmt(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.expression())
        )

        # initiate the body
        ifStmt.bodyBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )

        # initiate the else body
        ifStmt.elseBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )

        # check if our 'if' statement has an 'else-if'.
        # we can determine this by inspecting the context of the first child of the 'if' statement.
        # if the context type of the first child is 'IfThenElseStatementContext' or 'IfThenStatementContext',
        # we conclude that we have an 'else-if' (elif).
        if ctx.statement().getChildCount() == 1:
            if (type(ctx.statement().getChild(0)) == Java20Parser.IfThenElseStatementContext or
                    type(ctx.statement().getChild(0)) == Java20Parser.IfThenStatementContext):
                ifStmt.hasElif = True

        if len(self.state.StmtStack) == 0:
            self.state.StmtStack.append(ifStmt)

        else:
            topOfStack = self.state.StmtStack[-1]

            if type(topOfStack) == IfStmt:
                if topOfStack.currentBlock == "":
                    topOfStack.bodyBlock.body.append(ifStmt)
                else:
                    topOfStack.elseBlock.body.append(ifStmt)
            else:
                self.state.StmtStack.append(ifStmt)



    def exitIfThenElseStatement(self, ctx: Java20Parser.IfThenElseStatementContext):
        # run generic stmt stack pop method
        self.popStmtStack()

    def enterWhileStatement(self, ctx: Java20Parser.WhileStatementContext):
        # create new while stmt and push it on the stack
        whileStmt = WhileStmt(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.expression())
        )
        # initiate the body
        whileStmt.bodyBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )
        self.state.StmtStack.append(whileStmt)

    def exitWhileStatement(self, ctx: Java20Parser.WhileStatementContext):
        # run generic stmt stack pop method
        self.popStmtStack()

    def enterDoStatement(self, ctx: Java20Parser.DoStatementContext):
        # create new do while stmt and push it on the stack
        doWhileStmt = DoWhileStmt(
            Pos(ctx.start.line, ctx.start.column),
            ParseExpressionSubTree(ctx.expression())
        )
        # initiate the body
        doWhileStmt.bodyBlock = BlockStmt(
            Pos(ctx.start.line, ctx.start.column)
        )
        self.state.StmtStack.append(doWhileStmt)

    def exitDoStatement(self, ctx: Java20Parser.DoStatementContext):
        # run generic stmt stack pop method
        self.popStmtStack()

    def enterSwitchStatement(self, ctx: Java20Parser.SwitchStatementContext):
        # create new switch stmt and push it on the stack
        self.state.StmtStack.append(
            SwitchStmt(
                Pos(ctx.start.line, ctx.start.column),
                ParseExpressionSubTree(ctx.expression())
            )
        )

    def exitSwitchStatement(self, ctx: Java20Parser.SwitchStatementContext):
        # run generic stmt stack pop method
        self.popStmtStack()

    def enterSwitchBlockStatementGroup(self, ctx: Java20Parser.SwitchBlockStatementGroupContext):
        # get top of stack and check if it is a switch stmt
        topOfStack = self.state.StmtStack[-1]

        if type(topOfStack) == SwitchStmt:
            # initialize a new block
            blockStmt = BlockStmt(
                Pos(ctx.start.line, ctx.start.column)
            )

            # set the scope of the block as UUID.
            blockStmt.scope = str(uuid.uuid4())

            # add scope of the block to the AST
            self.ast.scopes[blockStmt.scope] = blockStmt

            # for each case label:
            for c in ctx.switchLabel():
                if type(c) == Java20Parser.SwitchLabelContext:
                    if c.getChildCount() == 2:
                        # if it is a list of case constants, add them to the switch-case blocks.
                        for sl in c.caseConstant():
                            topOfStack.caseBlocks[sl.getText()] = blockStmt
                            self.state.CurrentSwitchCase = sl.getText()
                    else:
                        # if it is default, add it to switch-case blocks
                        topOfStack.caseBlocks["default"] = blockStmt
                        self.state.CurrentSwitchCase = "default"

    def exitSwitchBlockStatementGroup(self, ctx: Java20Parser.SwitchBlockStatementGroupContext):
        # set current switch case to None
        self.state.CurrentSwitchCase = None

    def exitCompilationUnit(self, ctx: Java20Parser.CompilationUnitContext):
        # after the walker exits the parse tree, run the CFG generator.
        cfg = SourceLevelCFG(self.ast,self.output_dir)
        cfg.Gen()
