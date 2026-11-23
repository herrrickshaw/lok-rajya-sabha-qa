"""Test harness for the scripts/ directory.

Most of ``scripts/`` are command-line programs that resolve their data directory from ``__file__``
(``Path(__file__).resolve().parent.parent``) and have import-time side effects.  To test them offline without
touching the real ``data/`` tree, scripts are loaded through a meta-path finder that executes the REAL source
(compiled under its real filename so coverage is attributed to it) while presenting a throw-away ``__file__``
inside ``tmp_path``.  Sibling imports (``import signatory_matrix as S``) go through the same finder.
"""
import importlib
import os
import importlib.abc
import importlib.util
import runpy  # noqa: F401  (kept for tests that want it)
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# module name -> path relative to the repo root
REGISTRY = {p.stem: p.relative_to(ROOT) for p in (ROOT / "scripts").glob("*.py")}


class _Ctx:
    root = ROOT  # replaced per test by the ``repo`` fixture


CTX = _Ctx()


class _Loader(importlib.abc.Loader):
    def __init__(self, name):
        self.name = name

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        rel = REGISTRY[self.name]
        real = ROOT / rel
        module.__file__ = str(real)
        code = compile(real.read_text(encoding="utf-8"), str(real), "exec")
        exec(code, module.__dict__)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if path is None and fullname in REGISTRY:
            return importlib.util.spec_from_loader(fullname, _Loader(fullname))
        return None


sys.meta_path.insert(0, _Finder())


def _purge():
    for n in list(sys.modules):
        if n in REGISTRY:
            del sys.modules[n]


def run_script(name, argv=(), root=None):
    """Execute the real script as ``__main__`` (argv patched); returns the globals."""
    rel = REGISTRY[name]
    real = ROOT / rel
    g = {"__name__": "__main__", "__file__": str(real)}
    old = sys.argv
    sys.argv = [str(real), *argv]
    try:
        exec(compile(real.read_text(encoding="utf-8"), str(real), "exec"), g)
    finally:
        sys.argv = old
    return g


_REAL = {str(ROOT / rel): rel for rel in REGISTRY.values()}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throw-away repo root; ``load(name)`` imports a script bound to it.

    coverage.py keys tracing on the module's ``__file__`` (not only ``co_filename``), so scripts keep their real
    ``__file__``; ``Path.resolve`` is redirected for exactly those real script paths so that
    ``Path(__file__).resolve().parent.parent`` points at ``tmp_path`` instead of the checkout.
    """
    import pathlib
    orig = pathlib.Path.resolve

    def resolve(self, strict=False):
        rel = _REAL.get(str(self))
        if rel is not None and sys._getframe(1).f_code.co_filename in _REAL:     # only for the script itself, never for coverage.py
            return CTX.root / rel
        return orig(self, strict=strict)
    monkeypatch.setattr(pathlib.Path, "resolve", resolve)
    home = tmp_path / "_home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    import os.path as osp
    orig_abs = osp.abspath

    def abspath(p):
        rel = _REAL.get(os.fspath(p)) if isinstance(p, (str, os.PathLike)) else None
        if rel is not None and sys._getframe(1).f_code.co_filename not in _REAL:
            rel = None
        return str(CTX.root / rel) if rel is not None else orig_abs(p)
    monkeypatch.setattr(osp, "abspath", abspath)
    for d in ("scripts", "data/raw", "data/processed", "site", "docs/parties"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    CTX.root = tmp_path
    _purge()
    yield tmp_path
    _purge()
    CTX.root = ROOT


@pytest.fixture
def load(repo):
    def _load(name):
        return importlib.import_module(name)
    return _load
