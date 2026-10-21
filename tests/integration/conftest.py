"""Integration test configuration."""

from __future__ import annotations

import pytest
from datalab.config import Conf


@pytest.fixture(autouse=True)
def _no_plugin_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep DataLab from loading this plugin when it is installed (editable mode):
    it would reload its modules, undoing the tests' patches, and unregister its
    formats when closing."""
    monkeypatch.setattr(Conf.plugins_enabled, "get", lambda *_args, **_kw: False)
