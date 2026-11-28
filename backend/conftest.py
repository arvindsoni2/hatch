"""Test-suite defaults that must be in place before the application imports."""

from __future__ import annotations

import os

_DEFAULT_HOSTS = "localhost,127.0.0.1,[::1],backend,frontend"
_hosts = os.environ.get("HATCH_TRUSTED_HOSTS", _DEFAULT_HOSTS)
if "test" not in {host.strip() for host in _hosts.split(",")}:
    os.environ["HATCH_TRUSTED_HOSTS"] = f"{_hosts},test"
