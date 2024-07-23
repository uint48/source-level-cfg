import html
import random
import re

import networkx as nx
import graphviz as gv
from code.ast import *


class BasicBlock:
    def __init__(self):
        self.type = ""
        self.attr = {}
        self.stmts = []

    def getHTMLBlock(self, bId):
        contents = ""
        for stmt in self.stmts:
            contents += "<tr>"
            if stmt != self.stmts[-1]:
                contents += (
                        "<td align=\"left\" sides=\"lr\">" +
                        html.escape(str(stmt)) +
                        "</td><td sides=\"r\">" +
                        html.escape(str(stmt.pos)) +
                        "</td>"
                )
            elif stmt == self.stmts[-1]:
                contents += (
                        "<td align=\"left\" sides=\"lrb\">" +
                        html.escape(str(stmt)) +
                        "</td><td sides=\"rb\">" +
                        html.escape(str(stmt.pos)) +
                        "</td>"
                )
            contents += "</tr>"

        res = f"""<<FONT POINT-SIZE="8"><TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">
                <tr>
                    <td>{bId}</td>
                    <td>pos</td>
                </tr>
                {contents}
            </TABLE></FONT>>"""
        return res


class SourceLevelCFG:
    def __init__(self, ast):
        self.ast = ast
        self.CFG = nx.DiGraph()
        self.basicBlocks = {}
        self.bIndex = 0
        self.isReturn = False

        self.CFG.add_node(0)
        self.basicBlocks[0] = BasicBlock()
        self.basicBlocks[0].type = "start"

        self.bIndex += 1
        self.basicBlocks[self.bIndex] = BasicBlock()
        self.CFG.add_node(self.bIndex)
        self.CFG.add_edge(0, self.bIndex)

    def Gen(self):
        for d in self.ast.decls:
            if type(d) == Class:
                continue
            elif type(d) == Method:
                if len(d.bodyBlock.body) == 0:
                    continue

                lastBodyIndex = self.bIndex
                lastGraphOpenNodes = [1]

                for s in d.bodyBlock.body:

                    res = self.genGenericStmt(s)

                    if self.isReturn:
                        self.isReturn = False
                        self.basicBlocks[self.bIndex].attr["return"] = True

                    if type(res) == nx.DiGraph:
                        for i in lastGraphOpenNodes:
                            if self.basicBlocks[i].type == "conditional":
                                if self.CFG.out_degree(i) == 1:
                                    self.CFG.add_edge(i, min(res.nodes), label="false")
                            else:
                                if self.CFG.out_degree(i) == 0:
                                    self.CFG.add_edge(i, min(res.nodes))

                        lastGraphOpenNodes = []

                        for od in res.out_degree():
                            if od[1] == 0:
                                lastGraphOpenNodes.append(od[0])
                            if self.basicBlocks[od[0]].type == "conditional":
                                lastGraphOpenNodes.append(od[0])

                        self.CFG = nx.compose(self.CFG, res)

                        if not self.CFG.has_edge(lastBodyIndex, min(res.nodes)):
                            self.CFG.add_edge(lastBodyIndex, min(res.nodes))

                        if lastBodyIndex != self.bIndex and d.bodyBlock.body[-1] != s:
                            self.bIndex += 1
                            self.basicBlocks[self.bIndex] = BasicBlock()
                            lastBodyIndex = self.bIndex
                            self.CFG.add_node(lastBodyIndex)

                    else:
                        self.basicBlocks[lastBodyIndex].stmts.append(res)
                        gCopy = self.CFG.copy()
                        for i in gCopy.in_degree():
                            if i[0] == lastBodyIndex:
                                if i[1] == 0:
                                    for j in lastGraphOpenNodes:
                                        if self.basicBlocks[j].type == "conditional":
                                            if self.CFG.out_degree(j) == 1:
                                                self.CFG.add_edge(j, lastBodyIndex, label="false")
                                        else:
                                            if self.CFG.out_degree(j) == 0:
                                                self.CFG.add_edge(j, lastBodyIndex)

                self.prepareFinalCFG1()

                self.drawCFG(d, "CFG")

                if "getNextCase" in d.name:
                    continue

                # self.CFG = self.maxMerge(self.CFG)

                # self.fixNextBBs(self.CFG, cases, decryptedCases)

                ###########

                declsList, declsMap = self.extractVariableDeclarations(self.CFG)

                self.fixVariablesInExprs(self.CFG, declsMap)

                whileStmt, nextCase = self.constructSwitchCFG(self.CFG)

                self.genObfuscatedJavaFile(nextCase, whileStmt, d, declsList)

                self.prepareFinalCFG2()

                self.drawCFG(d, "OBFUSCATED_CFG")

    def genObfuscatedJavaFile(self, nextCase, whileStmt, method, declsList):
        res = """
        package %PKG%;
        
        public class %CLSNAME% {
        
            public %ISSTATIC% void %MTHDNAME%(String[] args) {
                %GLOBALDECLS%
            
                %nextCaseVar%;
            
                %WHILESTMT%
            }
        }
        """
        declsFinal = ""
        for decl in declsList:
            declsFinal += str(decl)
            declsFinal += ";\n"

        res = res.replace("%GLOBALDECLS%", declsFinal)

        res = res.replace("%PKG%", self.ast.package)
        res = res.replace("%CLSNAME%", method.scope)
        res = res.replace("%ISSTATIC%", "static")
        res = res.replace("%MTHDNAME%", method.name)
        res = res.replace("%nextCaseVar%", str(nextCase))
        res = res.replace("%WHILESTMT%", whileStmt.formatter())

        with open(f"{method.scope}.java", "w") as f:
            f.write(res)

    def extractVariableDeclarations(self, s):
        declsList = []
        declsMap = {}

        for node in list(s.nodes):
            if node == 0:
                continue
            if node == list(s.nodes)[-1]:
                continue

            mapCopy = self.basicBlocks[node].stmts.copy()

            for index, stmt in enumerate(mapCopy):
                if type(stmt) == DeclStmt:

                    declsMap[stmt.field.name] = stmt.field.name + "_" + stmt.field.scope

                    if stmt.field.type_ == "int":
                        declsList.append(DeclStmt(
                            Pos(0, 0),
                            Field(
                                Pos(0, 0),
                                stmt.field.name + "_" + stmt.field.scope,
                                stmt.field.type_,
                                stmt.field.kind,
                                "0"
                            )
                        ))
                    elif stmt.field.type_ == "float":
                        declsList.append(DeclStmt(
                            Pos(0, 0),
                            Field(
                                Pos(0, 0),
                                stmt.field.name + "_" + stmt.field.scope,
                                stmt.field.type_,
                                stmt.field.kind,
                                "0.0"
                            )
                        ))
                    elif stmt.field.type_ == "double":
                        declsList.append(DeclStmt(
                            Pos(0, 0),
                            Field(
                                Pos(0, 0),
                                stmt.field.name + "_" + stmt.field.scope,
                                stmt.field.type_,
                                stmt.field.kind,
                                "0.0"
                            )
                        ))
                    elif stmt.field.type_ == "char":
                        declsList.append(DeclStmt(
                            Pos(0, 0),
                            Field(
                                Pos(0, 0),
                                stmt.field.name + "_" + stmt.field.scope,
                                stmt.field.type_,
                                stmt.field.kind,
                                "''"
                            )
                        ))
                    elif stmt.field.type_ == "boolean":
                        declsList.append(DeclStmt(
                            Pos(0, 0),
                            Field(
                                Pos(0, 0),
                                stmt.field.name + "_" + stmt.field.scope,
                                stmt.field.type_,
                                stmt.field.kind,
                                "false"
                            )
                        ))
                    else:
                        declsList.append(DeclStmt(
                            Pos(0, 0),
                            Field(
                                Pos(0, 0),
                                stmt.field.name + "_" + stmt.field.scope,
                                stmt.field.type_,
                                stmt.field.kind,
                                "null"
                            )
                        ))

                    if stmt.field.expr == None:
                        del self.basicBlocks[node].stmts[index]
                    else:
                        if stmt.field.type_ not in ["int", "float", "double", "char", "boolean", "String"]:
                            stmt.field.expr = "new " + stmt.field.type_ + str(stmt.field.expr)

                        self.basicBlocks[node].stmts[index] = ExpressionStmt(
                            Pos(0, 0),
                            AssignExpr(
                                Pos(0, 0),
                                "=",
                                stmt.field.name,
                                stmt.field.expr
                            )
                        )

        return declsList, declsMap

    def fixVariablesInExprs(self, s, declsMap):
        def replaceName(expr):
            result = str(expr)
            for k in declsMap:
                pattern = f"(?<![0-9a-zA-Z]){k}(?![0-9a-zA-Z])"
                result = re.sub(pattern, declsMap[k], result)
            return result

        def handleExpr(expr):
            if type(expr) == UnaryExpr:
                expr.expr = replaceName(expr.expr)
            elif type(expr) == AssignExpr:
                expr.lhs = replaceName(expr.lhs)
                if type(expr.rhs) == UnaryExpr:
                    expr.rhs.expr = replaceName(expr.rhs.expr)
                elif type(expr.rhs) == MallocExpr:
                    expr.rhs.name = replaceName(expr.rhs.name)
                    for index, arg in enumerate(expr.rhs.args):
                        expr.rhs.args[index] = replaceName(arg)
                elif type(expr.rhs) == CastExpr:
                    expr.rhs.expr = replaceName(expr.rhs.expr)
                else:
                    expr.rhs = replaceName(expr.rhs)
            elif type(expr) == CallExpr:
                expr.package = replaceName(expr.package)
                expr.name = replaceName(expr.name)
                for index, arg in enumerate(expr.args):
                    expr.args[index] = replaceName(arg)
            elif type(expr) == BinaryExpr:
                expr.lhs = replaceName(expr.lhs)
                expr.rhs = replaceName(expr.rhs)

            elif type(expr) == ConditionalExpr:
                expr.cond = replaceName(expr.cond)
                expr.trueExpr = replaceName(expr.trueExpr)
                expr.falseExpr = replaceName(expr.falseExpr)

            elif type(expr) == MallocExpr:
                expr.name = replaceName(expr.name)
                for index, arg in enumerate(expr.args):
                    expr.args[index] = replaceName(arg)

            elif type(expr) == CastExpr:
                expr.expr = replaceName(expr.expr)

        for node in list(s.nodes):
            if node == 0:
                continue
            if node == list(s.nodes)[-1]:
                continue

            for index, stmt in enumerate(self.basicBlocks[node].stmts):
                if type(stmt) == ExpressionStmt:
                    handleExpr(stmt.expr)
                elif type(stmt) == BinaryExpr:
                    handleExpr(stmt)
                elif type(stmt) == UnaryExpr:
                    handleExpr(stmt)
                elif type(stmt) == AssignExpr:
                    handleExpr(stmt)

    def constructSwitchCFG(self, s):
        def genCaseKey(key):
            value = 0
            for i in range(16):
                bit = (key >> i) & 1
                value |= bit << (15 - i)
            return value

        global endNode
        g = nx.DiGraph()

        basicBlocks = {}
        bIndex = 0
        basicBlocks[0] = self.basicBlocks[0]

        bIndex += 1
        basicBlocks[bIndex] = BasicBlock()
        g.add_node(bIndex)

        nextCase = Field(
            Pos(0, 0),
            "nextCase",
            "int",
            Field.Type.LOCAL_VAR,
            None
        )

        basicBlocks[bIndex].stmts.append(
            ExpressionStmt(
                Pos(0, 0),
                nextCase
            )
        )

        g.add_edge(0, bIndex)

        initBlock = bIndex

        whileStmt = WhileStmt(
            Pos(0, 0),
            ExpressionStmt(
                Pos(0, 0),
                BinaryExpr(
                    Pos(0, 0),
                    nextCase.name,
                    ">",
                    "0"
                )
            )
        )

        whileStmt.bodyBlock = BlockStmt(
            Pos(0, 0)
        )

        se = SwitchStmt(
            Pos(0, 0),
            nextCase.name
        )

        casesEncrypted = {}

        startcase = None

        for node in list(s.nodes):
            if casesEncrypted.get(node) == None:
                rand = random.randint(156666, 999999)
                casesEncrypted[node] = [rand, genCaseKey(rand)]

        for node in list(s.nodes):
            if node == 0:
                continue
            if node == list(s.nodes)[-1]:
                endNode = bIndex
                continue

            if startcase == None:
                startcase = casesEncrypted[node][1]

            if self.basicBlocks[node].type == "conditional":
                trueRandomNumber = 0
                falseRandomNumber = 0

                gCopy = self.CFG.copy()
                for e in gCopy.out_edges(node):
                    if e[1] == list(s.nodes)[-1] and gCopy.get_edge_data(e[0], e[1])["label"] == "true":
                        trueRandomNumber = -random.randint(77, 65535)
                    elif e[1] == list(s.nodes)[-1] and gCopy.get_edge_data(e[0], e[1])["label"] == "false":
                        falseRandomNumber = -random.randint(77, 65535)
                    elif gCopy.get_edge_data(e[0], e[1])["label"] == "true":
                        trueRandomNumber = casesEncrypted[e[1]][0]
                    elif gCopy.get_edge_data(e[0], e[1])["label"] == "false":
                        falseRandomNumber = casesEncrypted[e[1]][0]
                    else:
                        trueRandomNumber = -random.randint(77, 65535)
                        falseRandomNumber = -random.randint(77, 65535)

                ifStmt = IfStmt(
                    Pos(0, 0),
                    self.basicBlocks[node].stmts[0]
                )

                ifStmt.bodyBlock = BlockStmt(
                    Pos(0, 0)
                )

                ce = CallExpr(
                    Pos(0, 0),
                    "Dispatcher",
                    "getNextCase",
                )
                ce.args = [str(trueRandomNumber)]

                ifStmt.bodyBlock.body.append(
                    ExpressionStmt(
                        Pos(0, 0),
                        BinaryExpr(
                            Pos(0, 0),
                            nextCase.name,
                            "=",
                            ce
                        )
                    )
                )

                ce2 = CallExpr(
                    Pos(0, 0),
                    "Dispatcher",
                    "getNextCase",
                )
                ce2.args = [str(falseRandomNumber)]

                ifStmt.elseBlock = BlockStmt(
                    Pos(0, 0)
                )

                ifStmt.elseBlock.body.append(
                    ExpressionStmt(
                        Pos(0, 0),
                        BinaryExpr(
                            Pos(0, 0),
                            nextCase.name,
                            "=",
                            ce2
                        )
                    )
                )

                se.caseBlocks[casesEncrypted[node][1]] = BlockStmt(
                    Pos(0, 0)
                )

                se.caseBlocks[casesEncrypted[node][1]].body.append(ifStmt)

                se.caseBlocks[casesEncrypted[node][1]].body.append(
                    ExpressionStmt(
                        Pos(0, 0),
                        BreakStmt(
                            Pos(0, 0)
                        )
                    )
                )

                bIndex += 1

            else:
                nextRandomNumber = 0
                gCopy = self.CFG.copy()
                for e in gCopy.out_edges(node):
                    if e[1] == list(s.nodes)[-1]:
                        nextRandomNumber = -random.randint(77, 65535)
                    else:
                        nextRandomNumber = casesEncrypted[e[1]][0]

                se.caseBlocks[casesEncrypted[node][1]] = BlockStmt(
                    Pos(0, 0)
                )
                se.caseBlocks[casesEncrypted[node][1]].attr = self.basicBlocks[node].attr

                se.caseBlocks[casesEncrypted[node][1]].body.extend(self.basicBlocks[node].stmts)

                ce = CallExpr(
                    Pos(0, 0),
                    "Dispatcher",
                    "getNextCase",
                )
                ce.args = [str(nextRandomNumber)]

                se.caseBlocks[casesEncrypted[node][1]].body.append(
                    ExpressionStmt(
                        Pos(0, 0),
                        BinaryExpr(
                            Pos(0, 0),
                            nextCase.name,
                            "=",
                            ce
                        )
                    )
                )

                se.caseBlocks[casesEncrypted[node][1]].body.append(
                    ExpressionStmt(
                        Pos(0, 0),
                        BreakStmt(
                            Pos(0, 0)
                        )
                    )
                )

                bIndex += 1

        l = list(se.caseBlocks.items())
        random.shuffle(l)
        se.caseBlocks = dict(l)

        whileStmt.bodyBlock.body.append(se)

        self.bIndex = bIndex
        self.basicBlocks = basicBlocks

        gg = self.genGenericStmt(whileStmt)

        g = nx.compose(g, gg)

        g.add_edge(initBlock, min(gg.nodes))

        basicBlocks[endNode] = BasicBlock()
        basicBlocks[endNode].type = "end"
        g.add_node(endNode)

        nextCase.expr = str(startcase)

        self.CFG = g
        return whileStmt, nextCase

    # def getNodeInputDegree(self, node):
    #     return self.CFG.in_degree(node)
    #
    # def getNodeOutputDegree(self, node):
    #     return self.CFG.out_degree(node)

    # def getSingleOutputEdge(self, node):
    #     for e in self.CFG.out_edges(node):
    #         return e[1]

    # def maxMerge(self, g):
    #     gCopy = g.copy()
    #     basicBlocks = self.basicBlocks.copy()
    #     edges = list(nx.edge_dfs(g))
    #     for edge in edges:
    #         if self.getNodeInputDegree(edge[0]) == self.getNodeOutputDegree(edge[0]):
    #             if self.getNodeInputDegree(edge[0]) != 1:
    #                 continue
    #             if self.basicBlocks[edge[0]].type == "conditional":
    #                 continue
    #             if self.getNodeInputDegree(edge[1]) == self.getNodeOutputDegree(edge[1]):
    #                 if self.getNodeInputDegree(edge[1]) != 1:
    #                     continue
    #
    #                 basicBlocks[edge[0]].stmts.extend(basicBlocks[edge[1]].stmts)
    #
    #                 newDstNode = self.getSingleOutputEdge(edge[1])
    #
    #                 del basicBlocks[edge[1]]
    #                 gCopy.remove_node(edge[1])
    #
    #                 gCopy.add_edge(edge[0], newDstNode)
    #
    #     self.basicBlocks = basicBlocks
    #
    #     return gCopy

    def genBlockStmt(self, stmt):
        g = nx.DiGraph()

        self.bIndex += 1
        self.basicBlocks[self.bIndex] = BasicBlock()
        g.add_node(self.bIndex)

        lastBodyIndex = self.bIndex

        lastGraphOpenNodes = []

        for od in g.out_degree():
            if od[1] == 0:
                lastGraphOpenNodes.append(od[0])

        for s in stmt.body:
            res = self.genGenericStmt(s)

            if self.isReturn:
                self.isReturn = False
                self.basicBlocks[self.bIndex].attr["return"] = True

            if type(res) == nx.DiGraph:
                g.add_edge(lastBodyIndex, min(res.nodes))

                for i in lastGraphOpenNodes:
                    if lastBodyIndex != i:
                        g.add_edge(i, lastBodyIndex)

                lastGraphOpenNodes = []
                for od in res.out_degree():
                    if od[1] == 0:
                        lastGraphOpenNodes.append(od[0])

                g = nx.compose(g, res)

                if lastBodyIndex != self.bIndex and stmt.body[-1] != s:
                    self.bIndex += 1

                    self.basicBlocks[self.bIndex] = BasicBlock()
                    lastBodyIndex = self.bIndex
                    g.add_node(lastBodyIndex)

                    for od in res.out_degree():
                        if self.basicBlocks[od[0]].type == "conditional":
                            if od[1] == 0:
                                if od[0] != lastBodyIndex:
                                    g.add_edge(od[0], lastBodyIndex)
                            if od[1] == 1:
                                g.add_edge(od[0], lastBodyIndex, label="false")

            else:
                self.basicBlocks[lastBodyIndex].stmts.append(res)

            if type(s) == BreakStmt or type(s) == ContinueStmt:
                break

        return g

    def genBasicForStmt(self, stmt):

        g = nx.DiGraph()

        if len(stmt.initStmtList) != 0:
            self.bIndex += 1
            self.basicBlocks[self.bIndex] = BasicBlock()

            initIndex = self.bIndex
            g.add_node(initIndex)

            for s in stmt.initStmtList:
                self.basicBlocks[self.bIndex].stmts.append(s)

            g.add_edge(initIndex, initIndex + 1)

        self.bIndex += 1
        condIndex = self.bIndex
        g.add_node(condIndex)
        self.basicBlocks[condIndex] = BasicBlock()
        self.basicBlocks[condIndex].type = "conditional"

        condIndex = self.bIndex

        self.basicBlocks[condIndex].stmts.append(stmt.condExpr)

        bodyGraph = self.genBlockStmt(stmt.bodyBlock)

        g = nx.compose(g, bodyGraph)

        g.add_edge(condIndex, min(bodyGraph.nodes), label="true")

        if len(stmt.updateStmtList) != 0:
            self.bIndex += 1
            updateIndex = self.bIndex
            self.basicBlocks[updateIndex] = BasicBlock()

            for s in stmt.updateStmtList:
                self.basicBlocks[updateIndex].stmts.append(s)

            g.add_edge(updateIndex, condIndex)

            gCopy = bodyGraph.copy()
            for od in gCopy.out_degree():
                if od[1] == 0 and od[0] != updateIndex:
                    g.add_edge(od[0], updateIndex)
                elif od[1] == 1 and self.basicBlocks[od[0]].type == "conditional":
                    g.add_edge(od[0], updateIndex, label="false")

        else:
            gCopy = g.copy()
            for od in gCopy.out_degree():
                if od[1] == 0:
                    g.add_edge(od[0], condIndex)

        return g

    def genIfStmt(self, stmt):

        g = nx.DiGraph()

        hasElif = stmt.hasElif

        self.bIndex += 1
        self.basicBlocks[self.bIndex] = BasicBlock()

        condIndex = self.bIndex
        g.add_node(condIndex)
        self.basicBlocks[condIndex].type = "conditional"
        self.basicBlocks[condIndex].stmts.append(stmt.condExpr)

        self.bIndex += 1
        bodyIndex = self.bIndex
        g.add_node(bodyIndex)
        self.basicBlocks[bodyIndex] = BasicBlock()

        g.add_edge(condIndex, bodyIndex, label="true")

        lastCondIndex = condIndex
        lastBodyIndex = bodyIndex

        lastGraphOpenNodes = []

        for od in g.out_degree():
            if od[1] == 0:
                lastGraphOpenNodes.append(od[0])

        for s in stmt.bodyBlock.body:

            if self.isReturn:
                self.isReturn = False
                self.basicBlocks[self.bIndex].attr["return"] = True

            if s == stmt.bodyBlock.body[-1] and type(s) == IfStmt:
                if not hasElif:
                    res = self.genGenericStmt(s)

                    if type(res) == nx.DiGraph:
                        g.add_edge(lastBodyIndex, min(res.nodes))

                        for i in lastGraphOpenNodes:
                            g.add_edge(i, min(res.nodes))

                        lastGraphOpenNodes = []
                        for od in res.out_degree():
                            if od[1] == 0:
                                lastGraphOpenNodes.append(od[0])

                        g = nx.compose(g, res)
                        if lastBodyIndex != self.bIndex:
                            self.bIndex += 1
                            self.basicBlocks[self.bIndex] = BasicBlock()
                            lastBodyIndex = self.bIndex
                            g.add_node(lastBodyIndex)

                            for od in res.out_degree():
                                if self.basicBlocks[od[0]].type == "conditional":
                                    if od[1] == 0:
                                        if od[0] != lastBodyIndex:
                                            g.add_edge(od[0], lastBodyIndex)
                                    if od[1] == 1:
                                        g.add_edge(od[0], lastBodyIndex, label="false")
                else:
                    res = self.genIfStmt(s)
                    g.add_edge(lastCondIndex, min(res.nodes), label="false")
                    lastCondIndex = max(res.nodes)
                    g = nx.compose(g, res)

            else:
                res = self.genGenericStmt(s)
                if type(res) == nx.DiGraph:
                    g.add_edge(lastBodyIndex, min(res.nodes))

                    for i in lastGraphOpenNodes:
                        g.add_edge(i, min(res.nodes))

                    lastGraphOpenNodes = []
                    for od in res.out_degree():
                        if od[1] == 0:
                            lastGraphOpenNodes.append(od[0])

                    g = nx.compose(g, res)
                    if lastBodyIndex != self.bIndex:
                        self.bIndex += 1
                        self.basicBlocks[self.bIndex] = BasicBlock()
                        lastBodyIndex = self.bIndex
                        g.add_node(lastBodyIndex)

                        for od in res.out_degree():
                            if self.basicBlocks[od[0]].type == "conditional":
                                if od[1] == 0:
                                    if od[0] != lastBodyIndex:
                                        g.add_edge(od[0], lastBodyIndex)
                                if od[1] == 1:
                                    g.add_edge(od[0], lastBodyIndex, label="false")



                else:
                    self.basicBlocks[self.bIndex].stmts.append(res)

        if stmt.elseBlock.body != []:
            self.bIndex += 1
            self.basicBlocks[self.bIndex] = BasicBlock()

            lastBodyIndex = self.bIndex

            g.add_edge(condIndex, lastBodyIndex, label="false")

            for s in stmt.elseBlock.body:

                res = self.genGenericStmt(s)

                if self.isReturn:
                    self.isReturn = False
                    self.basicBlocks[self.bIndex].attr["return"] = True

                if type(res) == nx.DiGraph:
                    g.add_edge(lastBodyIndex, min(res.nodes))

                    g = nx.compose(g, res)
                    if lastBodyIndex != self.bIndex:
                        self.bIndex += 1
                        self.basicBlocks[self.bIndex] = BasicBlock()
                        lastBodyIndex = self.bIndex

                        for od in res.out_degree():
                            if self.basicBlocks[od[0]].type == "conditional":
                                if od[1] == 0:
                                    if od[0] != lastBodyIndex:
                                        g.add_edge(od[0], lastBodyIndex)
                                if od[1] == 1:
                                    g.add_edge(od[0], lastBodyIndex, label="false")


                else:
                    self.basicBlocks[self.bIndex].stmts.append(res)

        return g

    def genWhileStmt(self, stmt):
        g = nx.DiGraph()

        self.bIndex += 1
        self.basicBlocks[self.bIndex] = BasicBlock()

        condIndex = self.bIndex
        g.add_node(condIndex)
        self.basicBlocks[condIndex].type = "conditional"
        self.basicBlocks[condIndex].stmts.append(stmt.condExpr)

        bodyGraph = self.genBlockStmt(stmt.bodyBlock)

        g.add_edge(condIndex, min(bodyGraph.nodes), label="true")

        g = nx.compose(g, bodyGraph)

        for od in bodyGraph.out_degree():
            if od[1] == 0:
                if od[0] != condIndex:
                    g.add_edge(od[0], condIndex)
            if od[1] == 1 and self.basicBlocks[od[0]].type == "conditional":
                g.add_edge(od[0], condIndex, label="false")

        return g

    def genDoWhileStmt(self, stmt):
        g = nx.DiGraph()

        bodyGraph = self.genBlockStmt(stmt.bodyBlock)
        g = nx.compose(g, bodyGraph)

        self.bIndex += 1
        self.basicBlocks[self.bIndex] = BasicBlock()
        condIndex = self.bIndex
        g.add_node(condIndex)
        self.basicBlocks[condIndex].type = "conditional"
        self.basicBlocks[condIndex].stmts.append(stmt.condExpr)

        for od in bodyGraph.out_degree():
            if od[1] == 0:
                if od[0] != condIndex:
                    g.add_edge(od[0], condIndex)
            if od[1] == 1 and self.basicBlocks[od[0]].type == "conditional":
                g.add_edge(od[0], condIndex, label="false")

        g.add_edge(condIndex, min(bodyGraph.nodes), label="true")

        return g

    def genSwitchStmt(self, stmt):
        g = nx.DiGraph()

        self.bIndex += 1
        switchIndex = self.bIndex
        g.add_node(switchIndex)
        self.basicBlocks[switchIndex] = BasicBlock()
        self.basicBlocks[switchIndex].type = "switch"

        es = ExpressionStmt(
            stmt.pos,
            f"switch({stmt.expr})"
        )

        self.basicBlocks[switchIndex].stmts.append(es)

        caseBodyStart = -1
        lastCaseHasBreak = False

        for k, v in stmt.caseBlocks.items():
            bodyGraph = self.genBlockStmt(v)

            g = nx.compose(g, bodyGraph)

            g.add_edge(switchIndex, min(bodyGraph.nodes), label=f"{k}")

            if not lastCaseHasBreak and caseBodyStart != -1:
                g.add_edge(caseBodyStart, min(bodyGraph.nodes))

            if len(self.basicBlocks[max(bodyGraph)].stmts) != 0:
                if str(self.basicBlocks[max(bodyGraph)].stmts[-1]) == "break":
                    del self.basicBlocks[max(bodyGraph)].stmts[-1]
                    lastCaseHasBreak = True
                caseBodyStart = min(bodyGraph.nodes)

        return g

    def genGenericStmt(self, stmt):

        if type(stmt) == BlockStmt:
            return self.genBlockStmt(stmt)

        elif type(stmt) == BasicForStmt:
            return self.genBasicForStmt(stmt)

        elif type(stmt) == IfStmt:
            return self.genIfStmt(stmt)

        elif type(stmt) == WhileStmt:
            return self.genWhileStmt(stmt)

        elif type(stmt) == DoWhileStmt:
            return self.genDoWhileStmt(stmt)

        elif type(stmt) == SwitchStmt:
            return self.genSwitchStmt(stmt)

        elif type(stmt) == ExpressionStmt:
            return stmt

        elif type(stmt) == ReturnStmt:
            self.isReturn = True
            return stmt

        elif type(stmt) == ContinueStmt:
            return stmt

        elif type(stmt) == BreakStmt:
            return stmt

        elif type(stmt) == DeclStmt:
            return stmt

        elif type(stmt) == UnaryExpr:
            return ExpressionStmt(
                stmt.pos,
                stmt
            )

        elif type(stmt) == BinaryExpr:
            return ExpressionStmt(
                stmt.pos,
                stmt,

            )

    def removeEmptyBlocks(self, g):
        global newEdgeStart, newEdgeEnd
        gCopy = g.copy()
        for node in gCopy.nodes:
            if gCopy.in_degree(node) == 1 and gCopy.out_degree(node) == 1:
                if len(self.basicBlocks[node].stmts) == 0:
                    label = None
                    for e in gCopy.in_edges(node):
                        newEdgeStart = e[0]
                        if self.basicBlocks[e[0]].type == "conditional":
                            label = gCopy.get_edge_data(e[0], e[1])["label"]

                    for e in gCopy.out_edges(node):
                        newEdgeEnd = e[1]

                    g.remove_node(node)
                    del self.basicBlocks[node]

                    g.add_edge(newEdgeStart, newEdgeEnd, label=label)
            elif gCopy.in_degree(node) > 1 and gCopy.out_degree(node) == 1:
                if len(self.basicBlocks[node].stmts) == 0:
                    labels = []
                    newEdgeStarts = []
                    for e in gCopy.in_edges(node):
                        newEdgeStarts.append(e[0])
                        labels.append("")
                        if self.basicBlocks[e[0]].type == "conditional":
                            labels[-1] = gCopy.get_edge_data(e[0], e[1])["label"]

                    for e in gCopy.out_edges(node):
                        newEdgeEnd = e[1]

                    g.remove_node(node)
                    del self.basicBlocks[node]

                    for i,j in enumerate(newEdgeStarts):
                        g.add_edge(j, newEdgeEnd, label=labels[i])
        return g

    def prepareFinalCFG1(self):
        self.bIndex += 1
        endNodeIndex = self.bIndex
        self.CFG.add_node(endNodeIndex)
        self.basicBlocks[endNodeIndex] = BasicBlock()
        self.basicBlocks[endNodeIndex].type = "end"

        returnNodes = []

        for node in self.CFG.nodes:
            if self.basicBlocks[node].attr.get("return") is not None:
                stmts = self.basicBlocks[node].stmts
                for stmt in self.basicBlocks[node].stmts:
                    if type(stmt) == ReturnStmt:
                        stmts = self.basicBlocks[node].stmts[:self.basicBlocks[node].stmts.index(stmt) + 1]
                        break
                self.basicBlocks[node].stmts = stmts
                returnNodes.append(node)

        for node in returnNodes:
            gCopy = self.CFG.copy()
            for _, target in gCopy.out_edges(node):
                self.CFG.remove_edge(node, target)
                self.CFG.remove_node(target)
                del self.basicBlocks[target]
                self.CFG.add_edge(node, endNodeIndex)

        garbageNodes = []
        gCopy = self.CFG.copy()
        for ind in gCopy.in_degree():
            if not nx.has_path(gCopy, 0, ind[0]) and ind[0] != 0 and ind[0] != endNodeIndex:
                for _, target in gCopy.out_edges(ind[0]):
                    self.CFG.remove_edge(ind[0], target)
                T = nx.dfs_tree(self.CFG, ind[0])
                for node in T.nodes:
                    garbageNodes.append(node)

        for node in garbageNodes:
            self.CFG.remove_node(node)
            del self.basicBlocks[node]

        gCopy = self.CFG.copy()
        for od in gCopy.out_degree():
            if self.basicBlocks[od[0]].type == "conditional":
                if od[1] == 1:
                    self.CFG.add_edge(od[0], endNodeIndex, label="false")

            elif not self.basicBlocks[od[0]].type == "end" and not self.basicBlocks[od[0]].type == "start":
                if od[1] == 0:
                    self.CFG.add_edge(od[0], endNodeIndex)

        # remove blocks with no input edge
        gCopy = self.CFG.copy()
        for i in gCopy.in_degree():
            if i[0] == 0 or i[0] == endNodeIndex:
                continue
            if i[1] == 0:
                if len(self.basicBlocks[i[0]].stmts) == 0:
                    self.CFG.remove_node(i[0])
                    del self.basicBlocks[i[0]]

        gCopy = self.CFG.copy()
        for i in gCopy.in_degree():
            if i[0] == 0 or i[0] == endNodeIndex:
                continue
            if i[1] == 0:
                counter = i[0]
                while counter != 0:
                    if self.CFG.has_edge(counter - 1, endNodeIndex):
                        self.CFG.remove_edge(counter - 1, endNodeIndex)
                        counter -= 1
                        self.CFG.add_edge(counter, i[0])
                        break
                    else:
                        counter -= 1

        self.CFG = self.removeEmptyBlocks(self.CFG)

    def prepareFinalCFG2(self):
        self.bIndex += 1
        endNodeIndex = self.bIndex
        self.CFG.add_node(endNodeIndex)
        self.basicBlocks[endNodeIndex] = BasicBlock()
        self.basicBlocks[endNodeIndex].type = "end"

        garbageNodes = []
        gCopy = self.CFG.copy()
        for ind in gCopy.in_degree():
            if not nx.has_path(gCopy, 0, ind[0]) and ind[0] != 0 and ind[0] != endNodeIndex:
                for _, target in gCopy.out_edges(ind[0]):
                    self.CFG.remove_edge(ind[0], target)
                T = nx.dfs_tree(self.CFG, ind[0])
                for node in T.nodes:
                    garbageNodes.append(node)

        for node in garbageNodes:
            self.CFG.remove_node(node)
            del self.basicBlocks[node]

        gCopy = self.CFG.copy()
        for od in gCopy.out_degree():
            if self.basicBlocks[od[0]].type == "conditional":
                if od[1] == 1:
                    self.CFG.add_edge(od[0], endNodeIndex, label="false")

            elif not self.basicBlocks[od[0]].type == "end" and not self.basicBlocks[od[0]].type == "start":
                if od[1] == 0:
                    self.CFG.add_edge(od[0], endNodeIndex)

        # remove blocks with no input edge
        gCopy = self.CFG.copy()
        for i in gCopy.in_degree():
            if i[0] == 0 or i[0] == endNodeIndex:
                continue
            if i[1] == 0:
                if len(self.basicBlocks[i[0]].stmts) == 0:
                    self.CFG.remove_node(i[0])
                    del self.basicBlocks[i[0]]

        gCopy = self.CFG.copy()
        for i in gCopy.in_degree():
            if i[0] == 0 or i[0] == endNodeIndex:
                continue
            if i[1] == 0:
                counter = i[0]
                while counter != 0:
                    if self.CFG.has_edge(counter - 1, endNodeIndex):
                        self.CFG.remove_edge(counter - 1, endNodeIndex)
                        counter -= 1
                        self.CFG.add_edge(counter, i[0])
                        break
                    else:
                        counter -= 1

        self.CFG = self.removeEmptyBlocks(self.CFG)

    def drawCFG(self, method, ext):
        gd = gv.Digraph(format="pdf", node_attr={"shape": "none"}, strict=True, graph_attr={"rankdir": "TD"})

        gd.node(f'package: {self.ast.package}\nclass: {method.scope}\nmethod: {method.name}', style="filled",
                fillcolor="#ffff00", shape="tab", fontsize="9")

        for k, v in self.basicBlocks.items():
            if v.type == "start":
                gd.node("start", style="filled", fillcolor="#aaffaa", shape="oval")
            elif v.type == "end":
                gd.node("end", style="filled", fillcolor="#FF0000", shape="oval")
            elif v.type == "conditional":
                gd.node(str(k), label=v.getHTMLBlock(k), style="filled", fillcolor="#6CB4EE")
            elif v.type == "switch":
                gd.node(str(k), label=v.getHTMLBlock(k), style="filled", fillcolor="#00FF00")
            else:
                gd.node(str(k), label=v.getHTMLBlock(k))

        for selfEdge in self.CFG.edges:
            edgeStartNode = selfEdge[0]
            edgeEndNode = selfEdge[1]
            if self.basicBlocks[edgeStartNode].type == "start":
                edgeStartNode = "start"
            if self.basicBlocks[edgeEndNode].type == "end":
                edgeEndNode = "end"

            edgeLabel = self.CFG.get_edge_data(selfEdge[0], selfEdge[1]).get("label")

            if edgeLabel is not None:
                if edgeLabel == "true":
                    gd.edge(str(edgeStartNode), str(edgeEndNode), label=edgeLabel, tailport="sw")
                elif edgeLabel == "false":
                    gd.edge(str(edgeStartNode), str(edgeEndNode), label=edgeLabel, tailport="se")
                else:
                    gd.edge(str(edgeStartNode), str(edgeEndNode), label=edgeLabel)
            else:
                gd.edge(str(edgeStartNode), str(edgeEndNode), tailport="s")

        gd.render(f"./{method.name}_{ext}.gv", view=True)
