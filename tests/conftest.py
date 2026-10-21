"""Shared fixtures.

The protocol package is loaded on its own (as `protocol`) so its tests do not
need Home Assistant. It is loaded by file location rather than by putting
custom_components/narwal_local on sys.path: that directory holds select.py
and time.py, which would shadow the standard library's modules.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
_PROTOCOL_DIR = ROOT / "custom_components" / "narwal_local" / "protocol"


def _load_protocol() -> None:
    if "protocol" in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        "protocol", _PROTOCOL_DIR / "__init__.py", submodule_search_locations=[str(_PROTOCOL_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["protocol"] = module
    spec.loader.exec_module(module)


_load_protocol()


try:  # The HA test plugin blocks sockets unless a test asks for `socket_enabled`.
    import pytest_homeassistant_custom_component  # noqa: F401
except ImportError:

    @pytest.fixture
    def socket_enabled():
        """No-op stand-in when the HA test plugin (which provides it) is absent."""
        yield

FIXTURES = Path(__file__).parent / "fixtures"


def load_bin(name: str) -> bytes:
    return (FIXTURES / f"{name}.bin").read_bytes()


def load_golden(name: str):
    """The Go client's decoding of the same payload (written by fixturedump)."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def fixture_bin():
    return load_bin


@pytest.fixture
def golden():
    return load_golden
