# SECURITY CONSTRAINT: check_credentials()'s failure branch currently logs
# the raw submitted password via cherrypy.log (src/Pellmonweb/auth.py:147,150).
# That is SEC-01, fixed in Phase 5. Tests in this module assert ONLY on
# return values and session state -- do NOT add assertions on
# cherrypy.log.call_args or log message content. Doing so would codify the
# insecure behavior and force these tests to be rewritten when SEC-01 lands.

import cherrypy
import pytest

from Pellmonweb.auth import AuthController, SESSION_KEY


def test_check_credentials_success(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    assert ctrl.check_credentials("alice", "s3cret") is None


def test_check_credentials_wrong_password(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    assert ctrl.check_credentials("alice", "wrong") == "Incorrect username or password."


def test_check_credentials_unknown_user(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    assert ctrl.check_credentials("bob", "whatever") == "Incorrect username or password."


def test_login_sets_session_and_redirects_on_success(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)

    # HTTPRedirect is this code's success control flow (auth.py:167), not an error.
    with pytest.raises(cherrypy.HTTPRedirect):
        ctrl.login(username="alice", password="s3cret", from_page="/dashboard")

    assert cherrypy.session[SESSION_KEY] == "alice"


def test_login_failure_renders_loginform_without_session(cherrypy_request_ctx, mocker):
    lookup = mocker.MagicMock()
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=lookup)

    # No HTTPRedirect on failure -- get_loginform() renders inline instead.
    ctrl.login(username="alice", password="wrong", from_page="/dashboard")

    assert cherrypy.session.get(SESSION_KEY) is None
    lookup.get_template.assert_called_once_with("login.html")


def test_logout_clears_session(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    cherrypy.session[SESSION_KEY] = "alice"

    with pytest.raises(cherrypy.HTTPRedirect):
        ctrl.logout(from_page="/")

    # auth.py:173 sets it to None rather than deleting the key.
    assert cherrypy.session[SESSION_KEY] is None
