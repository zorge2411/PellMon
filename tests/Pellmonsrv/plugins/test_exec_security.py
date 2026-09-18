"""Unit tests for Exec plugin security hardening (SEC-03).

Verifies:
1. `execute_readscript` parses command string with `shlex.split`.
2. `execute_readscript` invokes `subprocess.check_output` with `shell=False`.
3. `execute_readscript` catches `subprocess.CalledProcessError` properly without NameError.
4. `execute_readscript` catches unexpected exceptions and logs them.
5. `execute_writescript` invokes `subprocess.check_call` with `shell=False`.
6. `execute_writescript` handles errors and exceptions gracefully.
"""

import inspect
import subprocess
import pytest

from Pellmonsrv.plugins.exec import execplugin


@pytest.fixture
def plugin():
    return execplugin()


def test_execute_readscript_source_security():
    """Verify source code does not contain shell=True and uses shlex.split."""
    src = inspect.getsource(execplugin.execute_readscript)
    assert "shell=False" in src
    assert "shell=True" not in src
    assert "shlex.split" in src


def test_execute_readscript_calls_subprocess_with_shell_false(plugin, mocker):
    mock_check_output = mocker.patch(
        "subprocess.check_output", return_value=b" 123.45 \n"
    )
    result = plugin.execute_readscript(None, "echo 'hello world' --flag=1")

    mock_check_output.assert_called_once_with(
        ["echo", "hello world", "--flag=1"], shell=False
    )
    assert result == "123.45"


def test_execute_readscript_handles_called_process_error(plugin, mocker):
    mocker.patch(
        "subprocess.check_output",
        side_effect=subprocess.CalledProcessError(returncode=1, cmd=["false"]),
    )
    result = plugin.execute_readscript(None, "false")
    assert result == "error"


def test_execute_readscript_handles_generic_exception(plugin, mocker):
    mocker.patch(
        "subprocess.check_output",
        side_effect=FileNotFoundError("command not found"),
    )
    result = plugin.execute_readscript(None, "nonexistent_binary --arg")
    assert result == "error"


def test_execute_writescript_calls_subprocess_with_shell_false(plugin, mocker):
    mock_check_call = mocker.patch("subprocess.check_call", return_value=0)
    result = plugin.execute_writescript(
        None, "100", "/usr/bin/set_power --level {}"
    )

    mock_check_call.assert_called_once_with(
        ["/usr/bin/set_power", "--level", "100"], shell=False
    )
    assert result == "ok"


def test_execute_writescript_handles_called_process_error(plugin, mocker):
    mocker.patch(
        "subprocess.check_call",
        side_effect=subprocess.CalledProcessError(returncode=2, cmd=["cmd"]),
    )
    result = plugin.execute_writescript(None, "val", "bad_script {}")
    assert result == "error"


def test_execute_writescript_handles_generic_exception(plugin, mocker):
    mocker.patch(
        "subprocess.check_call",
        side_effect=PermissionError("Permission denied"),
    )
    result = plugin.execute_writescript(None, "val", "restricted_cmd {}")
    assert result == "error"
