"""Unit tests for web authentication security hardening (SEC-01 and SEC-02).

Verifies:
1. PBKDF2-HMAC-SHA256 password hashing generates expected hash format.
2. Hash verification correctly matches valid passwords and rejects invalid passwords.
3. Plaintext stored passwords are rejected with an error log naming hash_password.
4. Raw submitted passwords are NEVER logged on failed login attempts or exceptions (SEC-01).
5. Both list-of-tuples and dictionary credential formats are supported.
"""

import cherrypy
import pytest

from Pellmonweb.auth import (
    AuthController,
    SESSION_KEY,
    hash_password,
    verify_password,
)


def test_hash_password_format_and_verification():
    h = hash_password("correcthorsebatterystaple")
    assert h.startswith("pbkdf2:sha256:600000$")
    parts = h.split("$")
    assert len(parts) == 3
    # Check salt is 32-char hex (16 bytes)
    assert len(parts[1]) == 32
    # Check hash is 64-char hex (32 bytes SHA256)
    assert len(parts[2]) == 64
    assert verify_password(h, "correcthorsebatterystaple") is True
    assert verify_password(h, "wrongpassword") is False


def test_hash_password_custom_salt_and_iterations():
    custom_salt = "abcd1234efgh5678"
    h = hash_password("mysecret", salt=custom_salt, iterations=50000)
    assert h.startswith("pbkdf2:sha256:50000$abcd1234efgh5678$")
    assert verify_password(h, "mysecret") is True
    assert verify_password(h, "othersecret") is False


def test_verify_password_plaintext_rejected(caplog):
    import logging
    with caplog.at_level(logging.ERROR, logger="pellMon"):
        assert verify_password("plain_text_secret", "plain_text_secret") is False
    assert any("hash_password" in r.message for r in caplog.records)


def test_old_iteration_hash_still_verifies():
    h = hash_password("oldpw", iterations=100000)
    assert h.startswith("pbkdf2:sha256:100000$")
    assert verify_password(h, "oldpw") is True
    assert verify_password(h, "nope") is False


def test_verify_password_edge_cases():
    # Empty / None credentials
    assert verify_password(None, "password") is False
    assert verify_password("credential", None) is False
    assert verify_password("", "password") is False
    assert verify_password("credential", "") is False
    assert verify_password("", "") is False

    # Malformed pbkdf2 strings
    assert verify_password("pbkdf2:sha256:notanumber$salt$hash", "secret") is False
    assert verify_password("pbkdf2:sha256:100000$notenoughparts", "secret") is False
    assert verify_password("pbkdf2:sha512:100000$salt$hash", "secret") is False
    assert verify_password("pbkdf2:unsupported", "secret") is False


def test_check_credentials_with_pbkdf2_hash(cherrypy_request_ctx):
    hashed = hash_password("secret_pass")
    ctrl = AuthController(credentials=[("alice", hashed)], lookup=None)
    assert ctrl.check_credentials("alice", "secret_pass") is None
    assert ctrl.check_credentials("alice", "wrong_pass") == "Incorrect username or password."


def test_check_credentials_with_dict_credentials(cherrypy_request_ctx):
    hashed = hash_password("admin_pass")
    ctrl = AuthController(credentials={"admin": hashed, "user": "plaintext_user"}, lookup=None)
    assert ctrl.check_credentials("admin", "admin_pass") is None
    assert ctrl.check_credentials("admin", "wrong_pass") == "Incorrect username or password."
    assert ctrl.check_credentials("user", "plaintext_user") == "Incorrect username or password."
    assert ctrl.check_credentials("user", "wrong") == "Incorrect username or password."


def test_check_credentials_plaintext_rejected(cherrypy_request_ctx, caplog):
    import logging
    ctrl = AuthController(credentials=[("bob", "legacy_cleartext")], lookup=None)
    with caplog.at_level(logging.ERROR, logger="pellMon"):
        res = ctrl.check_credentials("bob", "legacy_cleartext")
    assert res == "Incorrect username or password."
    assert any("hash_password" in r.message for r in caplog.records)


def test_check_credentials_failure_never_logs_password(cherrypy_request_ctx):
    sensitive_submitted_password = "SUPER_SECRET_PLAINTEXT_PASSWORD_98765"
    ctrl = AuthController(credentials=[("alice", hash_password("correct_password"))], lookup=None)

    error = ctrl.check_credentials("alice", sensitive_submitted_password)
    assert error == "Incorrect username or password."

    # Verify cherrypy.log was called
    assert cherrypy.log.called
    for call_args in cherrypy.log.call_args_list:
        logged_str = " ".join(str(a) for a in call_args[0])
        # NEVER log the submitted password (SEC-01)
        assert sensitive_submitted_password not in logged_str
        assert "password:" not in logged_str.lower()
        # Verify Remote-Addr and username are logged
        assert "127.0.0.1" in logged_str
        assert "alice" in logged_str


def test_check_credentials_exception_never_logs_password(cherrypy_request_ctx, mocker):
    sensitive_submitted_password = "ANOTHER_HIGHLY_CONFIDENTIAL_SECRET"
    # Create credentials object whose iteration raises an exception
    broken_creds = mocker.MagicMock()
    broken_creds.__iter__.side_effect = RuntimeError("DB connection dropped")
    ctrl = AuthController(credentials=broken_creds, lookup=None)

    error = ctrl.check_credentials("alice", sensitive_submitted_password)
    assert error == "Incorrect username or password."

    assert cherrypy.log.called
    for call_args in cherrypy.log.call_args_list:
        logged_str = " ".join(str(a) for a in call_args[0])
        assert sensitive_submitted_password not in logged_str
        assert "password:" not in logged_str.lower()
        assert "127.0.0.1" in logged_str
        assert "alice" in logged_str
