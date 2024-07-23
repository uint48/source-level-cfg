import os
import shutil
import sys
import time
import multiprocessing as mp
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path

from antlr4 import CommonTokenStream, FileStream, ParseTreeWalker

from code.listener import ASTListener, MyErrorListener
from gen.Java20Lexer import Java20Lexer
from gen.Java20Parser import Java20Parser


def run(javaFilePath,output_dir):
    tokenStream = FileStream(javaFilePath, encoding="utf8")
    lexer = Java20Lexer(tokenStream)
    token_stream = CommonTokenStream(lexer)
    parser = Java20Parser(token_stream)
    parser.removeErrorListeners()
    parser.addErrorListener(MyErrorListener())

    parseTree = parser.compilationUnit()
    astListener = ASTListener(output_dir)
    walker = ParseTreeWalker()
    walker.walk(astListener, parseTree)

# for a directory (project)
def process_file(file_path, dest_subdir):
    try:
        run(file_path, dest_subdir)
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))} File processed: '{Path(file_path).name}'")
    except Exception as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))} error: {e} file: '{Path(file_path).name}' skipping...")

def generate_directory_cfg(source_dir, destination_dir):
    source_path = Path(source_dir)
    dest_path = Path(destination_dir)

    # Use a context object for multiprocessing operations
    ctx = mp.get_context("spawn")

    # Create a ThreadPoolExecutor using the custom context
    with ThreadPoolExecutor(max_workers=mp.cpu_count(), initializer=lambda: ctx) as executor:
        futures = []
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                if file.endswith('.java'):
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(source_path)
                    dest_subdir = dest_path / rel_path.parent / file
                    dest_subdir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(file_path, os.path.join(dest_subdir.absolute(), "source.java"))

                    future = executor.submit(process_file, file_path, dest_subdir)
                    futures.append(future)

        for future in futures:
            future.result()


source_directory = "javasamples/SF110/"
destination_directory = "output/SF110/"

# generate_directory_cfg(source_directory, destination_directory)

# for one sample
run("javasamples/Example1.java","output")


