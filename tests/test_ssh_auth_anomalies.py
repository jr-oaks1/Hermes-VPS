"""H6 (S23): check_ssh_auth_anomalies() folds SSH auth-failure signals into the
Tier 3 guardrail, including the failed-*key*-auth class fail2ban cannot see on
this key-only host (§13.3: 'Connection closed by authenticating user ...
[preauth]' does not match fail2ban's filter).
"""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "audit"))

import hermes_vps_guardrail as g  # noqa: E402


def _mock_calls(journal_text: str, fail2ban_text: str = "|- Currently banned:\t0\n"):
    return mock.patch.object(
        g.subprocess, "run",
        side_effect=[
            mock.Mock(stdout=journal_text, returncode=0),
            mock.Mock(stdout=fail2ban_text, returncode=0),
        ],
    )


def test_quiet_host_is_info():
    with _mock_calls(""):
        out = g.check_ssh_auth_anomalies()
    assert len(out) == 1
    assert out[0].severity == "info"
    assert "0 auth-anomaly event(s)" in out[0].summary
    assert "invalid-user/failed-password=0" in out[0].detail
    assert "preauth-key-fail=0" in out[0].detail
    assert "fail2ban-currently-banned=0" in out[0].detail


def test_counts_invalid_user_and_failed_password():
    text = "Invalid user admin from 1.2.3.4\n" * 5 + "Failed password for root from 1.2.3.4\n" * 5
    with _mock_calls(text):
        out = g.check_ssh_auth_anomalies()
    assert out[0].severity == "info"  # 10 < _SSH_AUTH_WARN (20)
    assert "invalid-user/failed-password=10" in out[0].detail


def test_counts_preauth_key_failures_fail2ban_cannot_see():
    text = "Connection closed by authenticating user root 1.2.3.4 port 4444 [preauth]\n" * 3
    with _mock_calls(text):
        out = g.check_ssh_auth_anomalies()
    assert "preauth-key-fail=3" in out[0].detail
    assert "invalid-user/failed-password=0" in out[0].detail


def test_warning_threshold():
    text = "Invalid user admin from 1.2.3.4\n" * g._SSH_AUTH_WARN
    with _mock_calls(text):
        out = g.check_ssh_auth_anomalies()
    assert out[0].severity == "warning"
    assert out[0].category == "finding"


def test_critical_threshold():
    text = "Failed password for root from 1.2.3.4\n" * g._SSH_AUTH_CRIT
    with _mock_calls(text):
        out = g.check_ssh_auth_anomalies()
    assert out[0].severity == "critical"
    assert out[0].category == "alert"


def test_fail2ban_lookup_failure_does_not_break_the_check():
    with mock.patch.object(
        g.subprocess, "run",
        side_effect=[mock.Mock(stdout="", returncode=0), Exception("fail2ban-client not found")],
    ):
        out = g.check_ssh_auth_anomalies()
    assert out[0].severity == "info"
    assert "fail2ban-currently-banned" not in out[0].detail  # gracefully omitted, not a crash


def test_journalctl_failure_is_a_warning_error_not_a_crash():
    with mock.patch.object(g.subprocess, "run", side_effect=Exception("journalctl unavailable")):
        out = g.check_ssh_auth_anomalies()
    assert len(out) == 1
    assert out[0].severity == "warning"
    assert out[0].category == "error"
    assert "ssh.auth: check failed" in out[0].summary


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
