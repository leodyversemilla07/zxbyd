"""CLI smoke tests."""

from typer.testing import CliRunner

from zxbyd.main import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "zxbyd" in result.output


def test_no_args_shows_banner():
    result = runner.invoke(app)
    assert result.exit_code == 0
    assert "zxbyd" in result.output.lower()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "procurement" in result.output.lower()
