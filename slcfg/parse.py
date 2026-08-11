"""Front end: turn a .java file into an ANTLR parse tree."""

from antlr4 import CommonTokenStream, FileStream
from antlr4.error.ErrorListener import ErrorListener

from gen.Java20Lexer import Java20Lexer
from gen.Java20Parser import Java20Parser
from slcfg.errors import SyntaxErrorInSource


class RaisingErrorListener(ErrorListener):
    """Turns the first syntax error into an exception.

    Without this, ANTLR recovers from errors and hands back a partial tree,
    which then produces a partial CFG with no indication anything went wrong.
    """

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise SyntaxErrorInSource(f"line {line}:{column} {msg}")


def parse_file(java_file_path):
    """Parse a Java source file.

    Returns:
        The ``compilationUnit`` parse tree.

    Raises:
        SyntaxErrorInSource: if the file does not parse.
    """
    lexer = Java20Lexer(FileStream(java_file_path, encoding="utf8"))
    lexer.removeErrorListeners()
    lexer.addErrorListener(RaisingErrorListener())

    parser = Java20Parser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(RaisingErrorListener())

    return parser.compilationUnit()
