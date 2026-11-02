"""Characterisation tests: the refactored pipeline reproduces the ORIGINAL scripts' output byte for byte
on a tiny offline fixture (tests/fixtures/raw -> tests/fixtures/golden, produced by the pre-refactor code)."""
from __future__ import annotations

import shutil
from pathlib import Path

import build
import build_db
import build_graph

FIX = Path(__file__).parent / "fixtures"
GOLDEN = FIX / "golden"


def _assert_same_tree(actual: Path, expected: Path) -> None:
    names = sorted(p.name for p in expected.iterdir())
    assert sorted(p.name for p in actual.iterdir()) == names
    for n in names:
        assert (actual / n).read_bytes() == (expected / n).read_bytes(), n


def test_build_matches_original(tmp_path):
    out, site = tmp_path / "processed", tmp_path / "site"
    build.main(FIX / "raw", out, site)
    assert (site / "data.json").read_bytes() == (GOLDEN / "site" / "data.json").read_bytes()
    for p in out.iterdir():
        assert p.read_bytes() == (GOLDEN / "processed" / p.name).read_bytes(), p.name


def test_build_graph_matches_original(tmp_path):
    proc, site = tmp_path / "processed", tmp_path / "site"
    shutil.copytree(GOLDEN / "processed", proc)
    for n in ("kg_pagerank.csv", "kg_party_ministry_lift.csv", "kg_ministry_cooccurrence.csv",
              "kg_mp_coasking_bridges.csv", "kg_party_communities.csv", "graph.graphml"):
        (proc / n).unlink()
    site.mkdir()
    build_graph.main(proc, site)
    for n in ("kg_pagerank.csv", "kg_party_ministry_lift.csv", "kg_ministry_cooccurrence.csv",
              "kg_mp_coasking_bridges.csv", "kg_party_communities.csv", "graph.graphml"):
        assert (proc / n).read_bytes() == (GOLDEN / "processed" / n).read_bytes(), n
    assert (site / "graph.json").read_bytes() == (GOLDEN / "site" / "graph.json").read_bytes()


def test_build_db_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(build_db, "PROC", GOLDEN / "processed")
    monkeypatch.setattr(build_db, "DB_PATH", tmp_path / "t.duckdb")
    monkeypatch.setattr(build_db, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(build_db, "PARTY_DOCS", tmp_path / "docs" / "parties")
    build_db.main()
    import duckdb
    con = duckdb.connect(str(tmp_path / "t.duckdb"), read_only=True)
    assert con.execute("select count(*) from all_questions").fetchone()[0] == 24
    assert (tmp_path / "docs" / "ANALYSIS.md").exists()
