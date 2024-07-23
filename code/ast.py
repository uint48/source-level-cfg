from enum import Enum


class Pos:
    def __init__(self, line=0, column=0):
        """
        Initialize a Position object with line and column values.

        Args:
            line (int): The line number.
            column (int): The column number.
        """
        self.line = line
        self.column = column

    def __str__(self):
        return f"{self.line}:{self.column}"


class Field:
    def __init__(self, pos, name, type_, kind, expr):
        """
        Initialize a field (any type of variable or parameter).
        """
        self.pos = pos
        self.name = name
        self.type_ = type_
        self.kind = kind
        self.expr = expr
        self.scope = ""

    class Type(Enum):
        NONE = 0
        CLASS_FIELD = 1
        LOCAL_VAR = 2
        PARAM = 3

    def __str__(self):
        if self.expr is None:
            return f"{self.type_} {self.name}"
        else:
            return f"{self.type_} {self.name} = {self.expr}"

    def to_dict(self):
        return {
            "type": "field",
            "position": str(self.pos),
            "name": self.name,
            "expr": str(self.expr),
        }

class UnaryExpr:
    def __init__(self, pos, op, expr):
        """
        Initialize unary expressions like ++x, --x, +x, -x, ~x, !x, ...
        """
        self.pos = pos
        self.op = op
        self.expr = expr

    class Type(Enum):
        POST_INC = 0
        POST_DEC = 1
        PRE_INC = 2
        PRE_DEC = 3
        POS = 5
        NEG = 6
        TILDE = 7
        LOGIC_NOT = 8
        BIT_NOT = 9

    def __str__(self):
        if self.op == self.Type.POST_INC:
            return f"{self.expr}++"
        elif self.op == self.Type.POST_DEC:
            return f"{self.expr}--"
        if self.op == self.Type.PRE_INC:
            return f"++{self.expr}"
        elif self.op == self.Type.PRE_DEC:
            return f"--{self.expr}"
        elif self.op == self.Type.POS:
            return f"+{self.expr}"
        elif self.op == self.Type.NEG:
            return f"-{self.expr}"
        elif self.op == self.Type.BIT_NOT:
            return f"~{self.expr}"
        elif self.op == self.Type.LOGIC_NOT:
            return f"!{self.expr}"

    def to_dict(self):
        return {
            "type": "unary_expr",
            "position": str(self.pos),
            "expr": str(self),
        }

class BinaryExpr:
    def __init__(self, pos, lhs, op, rhs):
        """
        Initialize binary expressions like x + y, x - y, x * y, x / y, ...
        """
        self.pos = pos
        self.lhs = lhs
        self.op = op
        self.rhs = rhs

    def __str__(self):
        return f"{self.lhs} {self.op} {self.rhs}"

    def to_dict(self):
        return {
            "type": "binary_expr",
            "position": str(self.pos),
            "expr": str(self),
        }

class AssignExpr:
    def __init__(self, pos, op, lhs, rhs):
        """
        Initialize assign expressions like x = y, x += y, x -= y, ...
        """
        self.pos = pos
        self.op = op
        self.lhs = lhs
        self.rhs = rhs

    def __str__(self):
        if self.op == "":
            return f"{self.lhs} = {self.rhs}"
        else:
            return f"{self.lhs} {self.op} {self.rhs}"

    def to_dict(self):
        return {
            "type": "assign_expr",
            "position": str(self.pos),
            "expr": str(self),
        }

class CastExpr:
    def __init__(self, pos, expr, newType):
        """
        Initialize cast expressions like (int)x, (float)x, ...
        """
        self.pos = pos
        self.expr = expr
        self.newType = newType

    def __str__(self):
        return f"({self.newType}) {self.expr}"

    def to_dict(self):
        return {
            "type": "cast_expr",
            "position": str(self.pos),
            "expr": str(self),
        }

class MallocExpr:
    def __init__(self, pos, name):
        """
        Initialize allocate expressions like new MyClass()
        """
        self.pos = pos
        self.name = name
        self.args = []

    def __str__(self):
        args_ = ""
        for arg in self.args:
            if arg == self.args[-1]:
                args_ += f"{arg}"
            else:
                args_ += f"{arg},"
        return f"new {self.name}({args_})"

    def to_dict(self):
        return {
            "type": "malloc_expr",
            "position": str(self.pos),
            "expr": str(self),
        }

class CallExpr:
    def __init__(self, pos, package, name):
        """
        Initialize call expressions like mypackage.MyClass(myarg)
        """
        self.pos = pos
        self.package = package
        self.name = name
        self.args = []

    def __str__(self):
        args_ = ""
        for arg in self.args:
            if arg == self.args[-1]:
                args_ += f"{arg}"
            else:
                args_ += f"{arg},"
        return f"{self.package}.{self.name}({args_})"

    def to_dict(self):
        return {
            "type": "call_expr",
            "position": str(self.pos),
            "expr": str(self),
        }

class ConditionalExpr:
    def __init__(self, pos, cond, trueExpr, falseExpr):
        """
        Initialize conditional expressions like x ? y : z
        """
        self.pos = pos
        self.cond = cond
        self.trueExpr = trueExpr
        self.falseExpr = falseExpr

    def __str__(self):
        return f"{self.cond} ? {self.trueExpr} : {self.falseExpr}"

    def to_dict(self):
        return {
            "type": "conditional_expr",
            "position": str(self.pos),
            "expr": str(self),
        }

class ExpressionStmt:
    def __init__(self, pos, expr):
        """
        Initialize expression statements like x = y, x += y, x -= y, ...
        """
        self.pos = pos
        self.expr = expr

    def __str__(self):
        return f"{self.expr}"

    def to_dict(self):
        return {
            "type": "expr_stmt",
            "position": str(self.pos),
            "expr": str(self.expr),
        }

class DeclStmt:
    def __init__(self, pos, field):
        """
        Initialize declarations like int x, float y, ...
        """
        self.pos = pos
        self.field = field

    def __str__(self):
        if self.field.expr is None:
            return f"{self.field.type_} {self.field.name}"
        else:
            return f"{self.field.type_} {self.field.name} = {self.field.expr}"

    def to_dict(self):
        return {
            "type": "decl_stmt",
            "position": str(self.pos),
            "field": self.field.to_dict(),
        }

class ReturnStmt:
    def __init__(self, pos, expr):
        """
        Initialize return statements like return x, return y, ...
        """
        self.pos = pos
        self.expr = expr

    def __str__(self):
        if self.expr is None:
            return "return"
        else:
            return f"return {self.expr}"

    def to_dict(self):
        return {
            "type": "return_stmt",
            "position": str(self.pos),
            "expr": str(self.expr),
        }

###################################

class BlockStmt:
    def __init__(self, pos):
        """
        Initialize block statements like { x = y; }
        """
        self.pos = pos
        self.body = []
        self.fields = {}
        self.scope = ""

class BreakStmt:
    def __init__(self, pos, targetLabel=None):
        """
        Initialize break statements
        """
        self.pos = pos
        self.targetLabel = targetLabel

    def __str__(self):
        if self.targetLabel is None:
            return "break"
        else:
            return f"break {self.targetLabel}"

    def to_dict(self):
        return {
            "type": "break_stmt",
            "position": str(self.pos)
        }

class ContinueStmt:
    def __init__(self, pos, targetLabel=None):
        """
        Initialize continue statements
        """
        self.pos = pos
        self.targetLabel = targetLabel

    def __str__(self):
        if self.targetLabel is None:
            return "continue"
        else:
            return f"continue {self.targetLabel}"

    def to_dict(self):
        return {
            "type": "continue_stmt",
            "position": str(self.pos)
        }


class LabeledStmt:
    def __init__(self, pos, label, stmt):
        """
        Initialize labeled statements
        """
        self.pos = pos
        self.label = label
        self.stmt = stmt

    # Not implemented
    # def to_dict(self):
    #     return {
    #         "type": "!",
    #         "position": str(self.pos)
    #     }

class BasicForStmt:
    def __init__(self, pos, condExpr):
        """
        Initialize basic for statements
        """
        self.pos = pos
        self.initStmtList = []
        self.condExpr = condExpr
        self.updateStmtList = []
        self.bodyBlock = None

class IfStmt:
    def __init__(self, pos, condExpr):
        """
        Initialize if statements
        """
        self.pos = pos
        self.condExpr = condExpr
        self.bodyBlock = None
        self.elseBlock = None
        self.currentBlock = ""
        self.hasElif = False

class WhileStmt:
    def __init__(self, pos, condExpr):
        """
        Initialize while statements
        """
        self.pos = pos
        self.condExpr = condExpr
        self.bodyBlock = None

class DoWhileStmt:
    def __init__(self, pos, condExpr):
        """
        Initialize do-while statements
        """
        self.pos = pos
        self.condExpr = condExpr
        self.bodyBlock = None

class SwitchStmt:
    def __init__(self, pos, expr):
        """
        Initialize switch statements
        """
        self.pos = pos
        self.expr = expr
        self.caseBlocks = {}


class Method:
    def __init__(self, pos, name, retType):
        self.pos = pos
        self.name = name
        self.bodyBlock = None
        self.retType = retType
        self.scope = ""


class Class:
    def __init__(self, pos, name):
        self.pos = pos
        self.name = name
        self.modifiers = []
        self.fields = {}


class AST:
    def __init__(self):
        self.package = ""
        self.decls = []
        self.scopes = {}
