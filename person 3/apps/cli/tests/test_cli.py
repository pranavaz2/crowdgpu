"""
Tests for the CLI entry point.
"""

from click.testing import CliRunner

from cli.main import cli
from cli import __version__


def test_help_exits_zero() -> None:
    """--help should exit with code 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0


def test_help_contains_crowdgpu() -> None:
    """--help output should mention CrowdGPU."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "CrowdGPU" in result.output


def test_version_exits_zero() -> None:
    """--version should exit with code 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0


def test_version_output_contains_version_string() -> None:
    """--version output should contain the current version."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert __version__ in result.output


def test_jobs_group_help() -> None:
    """jobs --help should exit zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "--help"])
    assert result.exit_code == 0


def test_sessions_group_help() -> None:
    """sessions --help should exit zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["sessions", "--help"])
    assert result.exit_code == 0


def test_peers_group_help() -> None:
    """peers --help should exit zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["peers", "--help"])
    assert result.exit_code == 0
