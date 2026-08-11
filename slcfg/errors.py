"""Diagnostics for the AST and CFG stages.

The point of this module is that gaps in coverage are *visible*. The previous
implementation wrapped its tree walking in bare ``except: pass`` blocks, so a
construct it could not handle produced a graph that was quietly wrong rather
than an error. Every unsupported construct now goes through
:class:`Diagnostics`, which either raises (``strict``) or records a warning that
is printed and surfaced in the output.
"""


class SyntaxErrorInSource(Exception):
    """Raised when ANTLR reports a syntax error in the input file."""


class UnsupportedConstruct(Exception):
    """Raised for a Java construct the AST/CFG builder does not model.

    Attributes:
        pos: Source position of the construct.
        what: Short description of what was not handled.
    """

    def __init__(self, pos, what):
        self.pos = pos
        self.what = what
        super().__init__(f"{pos}: unsupported construct: {what}")


class Diagnostics:
    """Collects warnings, or raises immediately in strict mode."""

    def __init__(self, filename="<input>", strict=False, quiet=False):
        self.filename = filename
        self.strict = strict
        self.quiet = quiet
        self.warnings = []

    def unsupported(self, pos, what):
        """Report an unsupported construct.

        Raises:
            UnsupportedConstruct: if this Diagnostics is in strict mode.
        """
        err = UnsupportedConstruct(pos, what)
        if self.strict:
            raise err
        self.warn(pos, f"unsupported construct: {what}")

    def warn(self, pos, message):
        record = (str(pos), message)
        self.warnings.append(record)
        if not self.quiet:
            print(f"WARNING {self.filename}:{pos}: {message}")

    # Deliberately no __len__/__bool__: an empty Diagnostics must stay truthy.
    # With __len__ defined, `diagnostics or Diagnostics()` silently replaced a
    # caller's instance whenever it had no warnings yet, which disabled --strict.
