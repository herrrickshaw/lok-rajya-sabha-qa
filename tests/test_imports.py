"""Every script in scripts/ must be importable with scripts/ on sys.path (the
README invocation `python3 scripts/<x>.py`). No network, no data/raw: all
scripts guard their main() behind __name__ == "__main__"."""
import importlib
import socket

import pytest

SCRIPTS = [
    "build", "build_graph", "build_db", "build_xlsx", "ministry_registry",
    "compare_pib", "compare_pli", "compare_parivesh", "compare_wp_json_schemes",
]


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_imports_offline(name, monkeypatch):
    def _no_net(*a, **k):
        raise AssertionError("network access during import")
    monkeypatch.setattr(socket, "create_connection", _no_net)
    importlib.import_module(name)
