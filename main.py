import sys

from antlr4 import CommonTokenStream, FileStream, ParseTreeWalker

from code.listener import ASTListener, MyErrorListener
from gen.Java20Lexer import Java20Lexer
from gen.Java20Parser import Java20Parser


def run(javaFilePath):
    tokenStream = FileStream(javaFilePath, encoding="utf8")
    lexer = Java20Lexer(tokenStream)
    token_stream = CommonTokenStream(lexer)
    parser = Java20Parser(token_stream)
    parser.removeErrorListeners()
    parser.addErrorListener(MyErrorListener())

    try:
        parseTree = parser.compilationUnit()
        astListener = ASTListener()
        walker = ParseTreeWalker()
        walker.walk(astListener, parseTree)
    except Exception as e:
        print(e)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        run(sys.argv[1])
    else:
        print("Usage: python main.py <path_to_java_file>")


