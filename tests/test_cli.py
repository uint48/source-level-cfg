"""CLI behaviour: output shape, --check, and per-file error isolation."""

import json

import pytest

import main as cli
from tests.helpers import ROOT


def test_check_mode_passes_on_all_samples(capsys):
    assert cli.main([str(ROOT / "javasamples"), "--check", "--quiet"]) == 0
    assert capsys.readouterr().err == ""


def test_single_file_writes_json_and_dot(tmp_path):
    code = cli.main(
        [
            str(ROOT / "javasamples" / "Example12.java"),
            "--out",
            str(tmp_path),
            "--format",
            "dot",
            "--quiet",
        ]
    )
    assert code == 0

    out_dir = tmp_path / "Example12"
    assert (out_dir / "Example12.main.json").exists()
    assert (out_dir / "Example12.main.dot").exists()

    data = json.loads((out_dir / "Example12.main.json").read_text())
    assert data["class"] == "Example12"
    assert data["signature"] == "void main(String[] args)"
    # Every edge carries an explicit label key, even when unconditional.
    assert all("label" in edge for edge in data["edges"])
    assert data["nodes"][0]["type"] == "start"


def test_no_json_and_no_render_write_nothing(tmp_path):
    code = cli.main(
        [
            str(ROOT / "javasamples" / "Example1.java"),
            "--out",
            str(tmp_path),
            "--no-json",
            "--no-render",
            "--quiet",
        ]
    )
    assert code == 0
    assert not list(tmp_path.rglob("*.json"))


def test_directory_run_isolates_a_broken_file(tmp_path, capsys):
    good = tmp_path / "Good.java"
    good.write_text("class Good { void f() { int x = 1; } }")
    bad = tmp_path / "Bad.java"
    bad.write_text("class Bad { void f( }")

    out = tmp_path / "out"
    code = cli.main([str(tmp_path), "--out", str(out), "--no-render", "--quiet"])

    assert code == 1  # the broken file is reported as a failure
    captured = capsys.readouterr()
    assert "Bad.java" in captured.err
    # ...and the good file still produced output.
    assert (out / "Good" / "Good.f.json").exists()


def test_missing_path_is_reported(capsys):
    assert cli.main([str(ROOT / "does-not-exist.java")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_directory_with_no_java_files_is_reported(tmp_path, capsys):
    assert cli.main([str(tmp_path)]) == 2
    assert "no .java files" in capsys.readouterr().err


def test_strict_mode_raises_on_an_unmodeled_construct(tmp_path):
    """A switch *expression* carries flow we render as text rather than branches."""
    source = tmp_path / "SwitchExpr.java"
    source.write_text(
        "class SwitchExpr {\n"
        "  int f(int n) {\n"
        "    return switch (n) { case 1 -> 10; default -> 0; };\n"
        "  }\n"
        "}\n"
    )

    lenient = cli.main([str(source), "--out", str(tmp_path / "a"), "--no-render", "--quiet"])
    assert lenient == 0

    strict = cli.main(
        [str(source), "--out", str(tmp_path / "b"), "--no-render", "--quiet", "--strict"]
    )
    assert strict == 1


@pytest.mark.parametrize("fmt", ["dot"])
def test_format_option(tmp_path, fmt):
    cli.main(
        [
            str(ROOT / "javasamples" / "Example5.java"),
            "--out",
            str(tmp_path),
            "--format",
            fmt,
            "--quiet",
        ]
    )
    assert list((tmp_path / "Example5").glob(f"*.{fmt}"))
