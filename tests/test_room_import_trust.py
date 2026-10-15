"""Q11 · TLS that trusts what this computer trusts (room_import/trust.py, moved
from EM Tools' sync_manager/trust.py on 15 Oct 2026).

Measured on 4 Oct 2026: Blender's Python verifies with its own certifi bundle,
so the dev node behind Caddy answered CERTIFICATE_VERIFY_FAILED — «Find» never
proposed it and a sign-in died at the code exchange."""
import importlib.util
import pathlib
import ssl
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
from s3dgraphy.room_import import trust  # noqa: E402


def test_verification_is_never_turned_off():
    ctx = trust.context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    source = (_REPO / "src" / "s3dgraphy" / "room_import" / "trust.py").read_text(encoding="utf-8")
    assert "CERT_NONE" not in source and "_create_unverified_context" not in source


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS trust settings")
def test_only_what_the_settings_allow_and_never_a_denied_one(monkeypatch, tmp_path):
    import plistlib
    settings = {"trustList": {
        "AA" * 20: {},                                                  # always
        "BB" * 20: {"trustSettings": [{"kSecTrustSettingsPolicyName": "sslServer"}]},
        "CC" * 20: {"trustSettings": [{"kSecTrustSettingsResult": 3,
                                       "kSecTrustSettingsPolicyName": "sslServer"}]},
        "DD" * 20: {"trustSettings": [{"kSecTrustSettingsPolicyName": "SMIME"}]},
    }}

    def fake_run(cmd, **kw):
        plistlib.dump(settings, open(cmd[-1], "wb"))

        class R:
            stdout = ""
        return R()
    monkeypatch.setattr(trust.subprocess, "run", fake_run)
    assert trust._trusted_hashes(["-d"]) == {"AA" * 20, "BB" * 20}


def test_every_call_to_a_node_goes_through_it():
    """No bare stdlib call to a node: `node.py` opens through `access.urlopen`
    (which renews the access and sends through `trust`); `access` sends through
    `trust` too. Moved from EM Tools with the code (its other modules stay
    measured there)."""
    pkg = _REPO / "src" / "s3dgraphy" / "room_import"
    node = (pkg / "node.py").read_text(encoding="utf-8")
    assert "from .access import urlopen" in node
    assert "urllib.request.urlopen(" not in node
    access = (pkg / "access.py").read_text(encoding="utf-8")
    assert "from .trust import urlopen" in access
    assert "urllib.request.urlopen(" not in access
