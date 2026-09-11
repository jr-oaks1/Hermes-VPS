"""H9 (S23): check_cloud_firewall_cidr_drift() is the mitigation for S28 §13.2's
rejection reason ('a hand-maintained CIDR list drifts silently'). It doesn't
avoid the duplication S28 worried about — it makes the duplication's drift
visible instead of invisible, by re-diffing live on every guardrail run.
"""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "audit"))

import hermes_vps_guardrail as g  # noqa: E402

_CF_JSON = {
    "result": {
        "ipv4_cidrs": ["173.245.48.0/20", "103.21.244.0/22"],
        "ipv6_cidrs": ["2400:cb00::/32"],
    }
}


def _hc_rules(source_ips_80, source_ips_443=None):
    if source_ips_443 is None:
        source_ips_443 = source_ips_80
    return {
        "firewall": {
            "rules": [
                {"port": None, "protocol": "icmp", "source_ips": ["0.0.0.0/0"]},
                {"port": "80", "protocol": "tcp", "source_ips": source_ips_80},
                {"port": "443", "protocol": "tcp", "source_ips": source_ips_443},
                {"port": "52222", "protocol": "tcp", "source_ips": ["0.0.0.0/0", "::/0"]},
            ]
        }
    }


def _mock_env_and_requests(cf_json, hc_json, cf_ok=True, hc_ok=True):
    env = mock.patch.dict(os.environ, {"HCLOUD_API_TOKEN": "t", "HCLOUD_FIREWALL_ID": "1"})
    cf_resp = mock.Mock()
    cf_resp.json.return_value = cf_json
    cf_resp.raise_for_status = mock.Mock() if cf_ok else mock.Mock(side_effect=Exception("cf down"))
    hc_resp = mock.Mock()
    hc_resp.json.return_value = hc_json
    hc_resp.raise_for_status = mock.Mock() if hc_ok else mock.Mock(side_effect=Exception("hc down"))
    req = mock.patch.object(g.requests, "get", side_effect=[cf_resp, hc_resp])
    return env, req


def test_skips_when_credential_not_configured():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HCLOUD_API_TOKEN", None)
        os.environ.pop("HCLOUD_FIREWALL_ID", None)
        out = g.check_cloud_firewall_cidr_drift()
    assert out[0].severity == "info"
    assert "skipped" in out[0].summary


def test_in_sync_is_info():
    ranges = ["173.245.48.0/20", "103.21.244.0/22", "2400:cb00::/32"]
    env, req = _mock_env_and_requests(_CF_JSON, _hc_rules(ranges))
    with env, req:
        out = g.check_cloud_firewall_cidr_drift()
    assert out[0].severity == "info"
    assert "in sync" in out[0].summary


def test_missing_cloudflare_range_is_warning():
    # Cloud firewall only allows one of the two IPv4 ranges + the IPv6 one
    ranges = ["173.245.48.0/20", "2400:cb00::/32"]
    env, req = _mock_env_and_requests(_CF_JSON, _hc_rules(ranges))
    with env, req:
        out = g.check_cloud_firewall_cidr_drift()
    assert out[0].severity == "warning"
    assert "1 missing" in out[0].summary
    assert "103.21.244.0/22" in out[0].detail


def test_stale_extra_range_is_warning():
    # Cloud firewall allows an old range Cloudflare no longer publishes
    ranges = ["173.245.48.0/20", "103.21.244.0/22", "2400:cb00::/32", "1.2.3.0/24"]
    env, req = _mock_env_and_requests(_CF_JSON, _hc_rules(ranges))
    with env, req:
        out = g.check_cloud_firewall_cidr_drift()
    assert out[0].severity == "warning"
    assert "1 stale" in out[0].summary
    assert "1.2.3.0/24" in out[0].detail


def test_cloudflare_unreachable_is_a_graceful_warning_not_a_crash():
    env, req = _mock_env_and_requests(_CF_JSON, {}, cf_ok=False)
    with env, req:
        out = g.check_cloud_firewall_cidr_drift()
    assert len(out) == 1
    assert out[0].severity == "warning"
    assert out[0].category == "error"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
