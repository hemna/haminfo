#!/usr/bin/env python

"""Tests for the haminfo CLI entry point."""

import pytest
from click.testing import CliRunner
from haminfo.main import cli, load_commands


@pytest.fixture(autouse=True)
def _load_cli_commands():
    """Ensure all CLI subcommands are registered before tests run."""
    load_commands()


def test_cli_help():
    """Test that the top-level CLI --help works."""
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert '--help' in result.output
    assert '--version' in result.output


def test_cli_version():
    """Test that --version flag works."""
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0


def test_cli_no_args():
    """Test invoking CLI with no arguments shows usage info."""
    runner = CliRunner()
    result = runner.invoke(cli, [])
    # Click group with no default command shows usage (exit code 0 or 2)
    assert result.exit_code in (0, 2)
    # Should contain usage information regardless
    assert 'Usage' in result.output or 'help' in result.output.lower()


def test_cli_subcommands_registered():
    """Test that expected subcommands are registered."""
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    # These subcommands should be registered after load_commands()
    assert 'db' in result.output
    assert 'mcp' in result.output
