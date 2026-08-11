"""A Go-like AST for Java, built by :mod:`slcfg.astbuilder`.

Every node carries a source :class:`Pos`, renders itself with ``__str__`` (that
text is what appears inside a CFG basic block) and serializes with ``to_dict``.

Statement nodes fall into two groups:

* *Simple* statements -- :class:`ExpressionStmt`, :class:`DeclStmt`,
  :class:`ReturnStmt`, ... -- become a line inside a basic block.
* *Compound* statements -- :class:`IfStmt`, :class:`WhileStmt`,
  :class:`TryStmt`, ... -- become graph structure. They hold
  :class:`BlockStmt` bodies rather than rendering themselves.

Control transfers (:class:`BreakStmt`, :class:`ContinueStmt`) are statements
here but become *edges* in the CFG; they never appear inside a basic block.
"""

from enum import Enum


class Pos:
    """A source position (1-based line, 0-based column, as ANTLR reports them)."""

    def __init__(self, line=0, column=0):
        self.line = line
        self.column = column

    @classmethod
    def of(cls, ctx):
        """Build a Pos from an ANTLR context or token."""
        token = getattr(ctx, "start", ctx)
        return cls(token.line, token.column)

    def __str__(self):
        return f"{self.line}:{self.column}"

    def __eq__(self, other):
        return (
            isinstance(other, Pos)
            and self.line == other.line
            and self.column == other.column
        )

    def __hash__(self):
        return hash((self.line, self.column))


class Field:
    """Any named, typed storage location: class field, local, or parameter."""

    class Type(Enum):
        NONE = 0
        CLASS_FIELD = 1
        LOCAL_VAR = 2
        PARAM = 3

    def __init__(self, pos, name, type_, kind, expr):
        self.pos = pos
        self.name = name
        self.type_ = type_
        self.kind = kind
        self.expr = expr
        self.scope = ""

    def __str__(self):
        if self.expr is None:
            return f"{self.type_} {self.name}"
        return f"{self.type_} {self.name} = {self.expr}"

    def to_dict(self):
        return {
            "type": "field",
            "position": str(self.pos),
            "name": self.name,
            "var_type": self.type_,
            "kind": self.kind.name.lower(),
            "expr": None if self.expr is None else str(self.expr),
        }


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


class UnaryExpr:
    """``++x``, ``x--``, ``-x``, ``!x``, ``~x``, ..."""

    class Type(Enum):
        POST_INC = 0
        POST_DEC = 1
        PRE_INC = 2
        PRE_DEC = 3
        POS = 5
        NEG = 6
        LOGIC_NOT = 8
        BIT_NOT = 9

    # Operator spelling and whether it precedes the operand.
    _FORMS = {
        Type.POST_INC: ("++", False),
        Type.POST_DEC: ("--", False),
        Type.PRE_INC: ("++", True),
        Type.PRE_DEC: ("--", True),
        Type.POS: ("+", True),
        Type.NEG: ("-", True),
        Type.LOGIC_NOT: ("!", True),
        Type.BIT_NOT: ("~", True),
    }

    def __init__(self, pos, op, expr):
        self.pos = pos
        self.op = op
        self.expr = expr

    def __str__(self):
        token, prefix = self._FORMS[self.op]
        return f"{token}{self.expr}" if prefix else f"{self.expr}{token}"

    def to_dict(self):
        return {
            "type": "unary_expr",
            "position": str(self.pos),
            "op": self.op.name.lower(),
            "expr": str(self),
        }


class BinaryExpr:
    """``x + y``, ``x < y``, ``x && y``, ..."""

    def __init__(self, pos, lhs, op, rhs):
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
            "op": self.op,
            "expr": str(self),
        }


class AssignExpr:
    """``x = y``, ``x += y``, ..."""

    def __init__(self, pos, op, lhs, rhs):
        self.pos = pos
        self.op = op or "="
        self.lhs = lhs
        self.rhs = rhs

    def __str__(self):
        return f"{self.lhs} {self.op} {self.rhs}"

    def to_dict(self):
        return {
            "type": "assign_expr",
            "position": str(self.pos),
            "op": self.op,
            "expr": str(self),
        }


class CastExpr:
    """``(int) x``"""

    def __init__(self, pos, expr, newType):
        self.pos = pos
        self.expr = expr
        self.newType = newType

    def __str__(self):
        return f"({self.newType}) {self.expr}"

    def to_dict(self):
        return {
            "type": "cast_expr",
            "position": str(self.pos),
            "cast_to": self.newType,
            "expr": str(self),
        }


class MallocExpr:
    """``new MyClass(args)`` and ``new int[n]``."""

    def __init__(self, pos, name, dims=""):
        self.pos = pos
        self.name = name
        self.dims = dims
        self.args = []

    def __str__(self):
        if self.dims:
            return f"new {self.name}{self.dims}"
        args = ", ".join(str(a) for a in self.args)
        return f"new {self.name}({args})"

    def to_dict(self):
        return {
            "type": "malloc_expr",
            "position": str(self.pos),
            "name": self.name,
            "expr": str(self),
        }


class CallExpr:
    """A method invocation, with an optional qualifier (``System.out``)."""

    def __init__(self, pos, package, name):
        self.pos = pos
        self.package = package
        self.name = name
        self.args = []

    def __str__(self):
        args = ", ".join(str(a) for a in self.args)
        qualifier = f"{self.package}." if self.package else ""
        return f"{qualifier}{self.name}({args})"

    def to_dict(self):
        return {
            "type": "call_expr",
            "position": str(self.pos),
            "qualifier": self.package,
            "name": self.name,
            "expr": str(self),
        }


class ConditionalExpr:
    """``cond ? a : b``

    Kept as a single expression: this is a *source-level* CFG, so a ternary
    stays one statement rather than expanding into branches. See the README's
    non-goals.
    """

    def __init__(self, pos, cond, trueExpr, falseExpr):
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


class InstanceOfExpr:
    """``x instanceof T`` (including the pattern form ``x instanceof T t``)."""

    def __init__(self, pos, expr, type_, binding=None):
        self.pos = pos
        self.expr = expr
        self.type_ = type_
        self.binding = binding

    def __str__(self):
        tail = f" {self.binding}" if self.binding else ""
        return f"{self.expr} instanceof {self.type_}{tail}"

    def to_dict(self):
        return {
            "type": "instanceof_expr",
            "position": str(self.pos),
            "expr": str(self),
        }


class FieldAccessExpr:
    """``a.b`` -- a qualified name or field selection."""

    def __init__(self, pos, target, name):
        self.pos = pos
        self.target = target
        self.name = name

    def __str__(self):
        return f"{self.target}.{self.name}"

    def to_dict(self):
        return {
            "type": "field_access_expr",
            "position": str(self.pos),
            "expr": str(self),
        }


class ArrayAccessExpr:
    """``a[i]``"""

    def __init__(self, pos, target, index):
        self.pos = pos
        self.target = target
        self.index = index

    def __str__(self):
        return f"{self.target}[{self.index}]"

    def to_dict(self):
        return {
            "type": "array_access_expr",
            "position": str(self.pos),
            "expr": str(self),
        }


class ParenExpr:
    """``( expr )`` -- kept so the rendered text matches the source."""

    def __init__(self, pos, expr):
        self.pos = pos
        self.expr = expr

    def __str__(self):
        return f"({self.expr})"

    def to_dict(self):
        return {
            "type": "paren_expr",
            "position": str(self.pos),
            "expr": str(self),
        }


class MethodRefExpr:
    """``Type::method``"""

    def __init__(self, pos, text):
        self.pos = pos
        self.text = text

    def __str__(self):
        return self.text

    def to_dict(self):
        return {
            "type": "method_ref_expr",
            "position": str(self.pos),
            "expr": str(self),
        }


class RawExpr:
    """An expression kept verbatim as source text.

    Used for literals, simple names, and any construct with no dedicated node.
    Having an explicit node (rather than a bare ``str``) means every expression
    carries a position and serializes uniformly.
    """

    def __init__(self, pos, text):
        self.pos = pos
        self.text = text

    def __str__(self):
        return self.text

    def to_dict(self):
        return {
            "type": "raw_expr",
            "position": str(self.pos),
            "expr": self.text,
        }


# ---------------------------------------------------------------------------
# Simple statements -- these render as lines inside a basic block
# ---------------------------------------------------------------------------


class ExpressionStmt:
    def __init__(self, pos, expr):
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
    """A local variable declaration, one node per declarator."""

    def __init__(self, pos, field):
        self.pos = pos
        self.field = field

    def __str__(self):
        return str(self.field)

    def to_dict(self):
        return {
            "type": "decl_stmt",
            "position": str(self.pos),
            "expr": str(self),
            "field": self.field.to_dict(),
        }


class ReturnStmt:
    def __init__(self, pos, expr=None):
        self.pos = pos
        self.expr = expr

    def __str__(self):
        return "return" if self.expr is None else f"return {self.expr}"

    def to_dict(self):
        return {
            "type": "return_stmt",
            "position": str(self.pos),
            "expr": str(self),
        }


class ThrowStmt:
    def __init__(self, pos, expr):
        self.pos = pos
        self.expr = expr

    def __str__(self):
        return f"throw {self.expr}"

    def to_dict(self):
        return {
            "type": "throw_stmt",
            "position": str(self.pos),
            "expr": str(self),
        }


class YieldStmt:
    """``yield x`` inside a switch expression."""

    def __init__(self, pos, expr):
        self.pos = pos
        self.expr = expr

    def __str__(self):
        return f"yield {self.expr}"

    def to_dict(self):
        return {
            "type": "yield_stmt",
            "position": str(self.pos),
            "expr": str(self),
        }


class AssertStmt:
    def __init__(self, pos, cond, message=None):
        self.pos = pos
        self.cond = cond
        self.message = message

    def __str__(self):
        if self.message is None:
            return f"assert {self.cond}"
        return f"assert {self.cond} : {self.message}"

    def to_dict(self):
        return {
            "type": "assert_stmt",
            "position": str(self.pos),
            "expr": str(self),
        }


class BreakStmt:
    """``break`` / ``break label``.

    Becomes an edge in the CFG, never a statement inside a block.
    """

    def __init__(self, pos, targetLabel=None):
        self.pos = pos
        self.targetLabel = targetLabel

    def __str__(self):
        return "break" if self.targetLabel is None else f"break {self.targetLabel}"

    def to_dict(self):
        return {
            "type": "break_stmt",
            "position": str(self.pos),
            "label": self.targetLabel,
            "expr": str(self),
        }


class ContinueStmt:
    """``continue`` / ``continue label``. Becomes an edge, like `break`."""

    def __init__(self, pos, targetLabel=None):
        self.pos = pos
        self.targetLabel = targetLabel

    def __str__(self):
        return "continue" if self.targetLabel is None else f"continue {self.targetLabel}"

    def to_dict(self):
        return {
            "type": "continue_stmt",
            "position": str(self.pos),
            "label": self.targetLabel,
            "expr": str(self),
        }


class OpaqueStmt:
    """A statement the builder could not model, kept so flow stays honest.

    Emitted only alongside a diagnostic (see :mod:`slcfg.errors`); it marks the
    spot in the graph rather than silently dropping the source.
    """

    def __init__(self, pos, text):
        self.pos = pos
        self.text = text

    def __str__(self):
        return self.text

    def to_dict(self):
        return {
            "type": "opaque_stmt",
            "position": str(self.pos),
            "expr": self.text,
        }


# ---------------------------------------------------------------------------
# Compound statements -- these become graph structure
# ---------------------------------------------------------------------------


class BlockStmt:
    """A ``{ ... }`` body. Also used to wrap un-braced substatements."""

    def __init__(self, pos, body=None):
        self.pos = pos
        self.body = [] if body is None else body
        self.fields = {}
        self.scope = ""


class LabeledStmt:
    """``label: stmt`` -- the label is a `break`/`continue` target."""

    def __init__(self, pos, label, stmt):
        self.pos = pos
        self.label = label
        self.stmt = stmt


class IfStmt:
    """``if (cond) then else otherwise``.

    ``else if`` is represented uniformly: the chained ``IfStmt`` is simply the
    only element of ``elseBlock.body``. There is no ``hasElif`` flag, and the
    CFG builder needs no special case for it.
    """

    def __init__(self, pos, condExpr, bodyBlock=None, elseBlock=None):
        self.pos = pos
        self.condExpr = condExpr
        self.bodyBlock = bodyBlock if bodyBlock is not None else BlockStmt(pos)
        self.elseBlock = elseBlock if elseBlock is not None else BlockStmt(pos)


class BasicForStmt:
    """``for (init; cond; update) body``. A missing condition is ``true``."""

    def __init__(self, pos, condExpr, bodyBlock=None):
        self.pos = pos
        self.initStmtList = []
        self.condExpr = condExpr
        self.updateStmtList = []
        self.bodyBlock = bodyBlock if bodyBlock is not None else BlockStmt(pos)


class ForEachStmt:
    """``for (T v : iterable) body``.

    Modeled with an iterator rather than rewritten into an index loop: the
    header tests ``has next(iterable)`` and the body opens with
    ``v = next(iterable)``. This is correct for both arrays and any
    ``Iterable`` -- which matters because we have no type resolution and so
    cannot tell the two apart.
    """

    def __init__(self, pos, varField, iterableExpr, bodyBlock=None):
        self.pos = pos
        self.varField = varField
        self.iterableExpr = iterableExpr
        self.bodyBlock = bodyBlock if bodyBlock is not None else BlockStmt(pos)


class WhileStmt:
    def __init__(self, pos, condExpr, bodyBlock=None):
        self.pos = pos
        self.condExpr = condExpr
        self.bodyBlock = bodyBlock if bodyBlock is not None else BlockStmt(pos)


class DoWhileStmt:
    def __init__(self, pos, condExpr, bodyBlock=None):
        self.pos = pos
        self.condExpr = condExpr
        self.bodyBlock = bodyBlock if bodyBlock is not None else BlockStmt(pos)


class SwitchCase:
    """One case group of a switch.

    Args:
        labels: Every constant in the group -- ``case 1, 2:`` keeps both.
        isDefault: True for ``default``.
        isArrow: True for the ``->`` form, which never falls through.
    """

    def __init__(self, pos, labels, body=None, isDefault=False, isArrow=False):
        self.pos = pos
        self.labels = labels
        self.body = body if body is not None else BlockStmt(pos)
        self.isDefault = isDefault
        self.isArrow = isArrow

    def label_text(self):
        if self.isDefault and not self.labels:
            return "default"
        text = "case " + ", ".join(self.labels)
        return f"{text}, default" if self.isDefault else text


class SwitchStmt:
    """``switch (expr) { ... }``.

    Cases are an ordered *list*, not a dict keyed by label text: a dict loses
    both the ordering and the extra labels of a multi-label group.
    """

    def __init__(self, pos, expr):
        self.pos = pos
        self.expr = expr
        self.cases = []

    @property
    def isArrow(self):
        return bool(self.cases) and all(c.isArrow for c in self.cases)


class CatchClause:
    """``catch (A | B e) { ... }``"""

    def __init__(self, pos, types, param, body):
        self.pos = pos
        self.types = types
        self.param = param
        self.body = body

    def label_text(self):
        return " | ".join(self.types)


class TryStmt:
    """``try (resources) { } catch ... finally { }``

    Modeled with block-level exception edges: one ``exception``-labeled edge
    from the try region to each catch entry, and a ``finally`` reached from
    both the normal and every exceptional path.
    """

    def __init__(self, pos, bodyBlock=None):
        self.pos = pos
        self.resources = []
        self.bodyBlock = bodyBlock if bodyBlock is not None else BlockStmt(pos)
        self.catches = []
        self.finallyBlock = None


class SynchronizedStmt:
    """``synchronized (lock) { }`` -- body is inlined; flow is single-threaded."""

    def __init__(self, pos, lockExpr, bodyBlock=None):
        self.pos = pos
        self.lockExpr = lockExpr
        self.bodyBlock = bodyBlock if bodyBlock is not None else BlockStmt(pos)


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


class Method:
    """A method, constructor, initializer, or lambda pseudo-method.

    ``name`` is the plain identifier; ``scope`` is the qualified enclosing type
    (``Outer.Inner``). Filenames are derived from these, so no name scrubbing
    is needed at render time.
    """

    def __init__(self, pos, name, retType, isConstructor=False):
        self.pos = pos
        self.name = name
        self.retType = retType
        self.isConstructor = isConstructor
        self.params = []
        self.bodyBlock = None
        self.scope = ""
        # False for abstract and interface methods. An empty `{}` body is still a
        # body, and gets a (trivial) CFG.
        self.hasBody = False

    def signature(self):
        params = ", ".join(f"{p.type_} {p.name}" for p in self.params)
        if self.isConstructor:
            return f"{self.name}({params})"
        return f"{self.retType} {self.name}({params})"

    def qualified_name(self):
        return f"{self.scope}.{self.name}" if self.scope else self.name


class Class:
    """A class, interface, enum, or record declaration."""

    def __init__(self, pos, name, kind="class"):
        self.pos = pos
        self.name = name
        self.kind = kind
        self.modifiers = []
        self.fields = {}


class AST:
    def __init__(self):
        self.package = ""
        self.decls = []
        self.scopes = {}

    def methods(self):
        return [d for d in self.decls if isinstance(d, Method)]


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------

# Compound statements, and the attributes holding their nested bodies.
_COMPOUND_BODIES = {
    "IfStmt": ("bodyBlock", "elseBlock"),
    "WhileStmt": ("bodyBlock",),
    "DoWhileStmt": ("bodyBlock",),
    "BasicForStmt": ("initStmtList", "bodyBlock", "updateStmtList"),
    "ForEachStmt": ("bodyBlock",),
    "SynchronizedStmt": ("bodyBlock",),
    "LabeledStmt": ("stmt",),
    "TryStmt": ("resources", "bodyBlock", "catches", "finallyBlock"),
    "SwitchStmt": ("cases",),
}


def iter_simple_statements(node):
    """Yield every non-compound statement reachable from `node`.

    `node` may be a statement, a :class:`BlockStmt`, or a list. Compound
    statements are traversed but not themselves yielded -- they become graph
    structure, not block contents.

    Both the CFG builder (to account for unreachable code) and the invariant
    checker (to verify no statement was dropped) walk the AST this way, so they
    agree on what "every statement" means.
    """
    if node is None:
        return
    if isinstance(node, list):
        for item in node:
            yield from iter_simple_statements(item)
        return
    if isinstance(node, BlockStmt):
        yield from iter_simple_statements(node.body)
        return
    if isinstance(node, SwitchCase):
        yield from iter_simple_statements(node.body)
        return
    if isinstance(node, CatchClause):
        yield from iter_simple_statements(node.body)
        return

    bodies = _COMPOUND_BODIES.get(type(node).__name__)
    if bodies is None:
        yield node
        return
    for attr in bodies:
        yield from iter_simple_statements(getattr(node, attr, None))
