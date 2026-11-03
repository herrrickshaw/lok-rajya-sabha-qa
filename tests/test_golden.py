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


def test_build_markdown_matches_committed_docs(tmp_path, monkeypatch):
    """ANALYSIS.md (all sections) and every party brief regenerate byte-identically from data/processed."""
    repo = Path(__file__).resolve().parent.parent
    monkeypatch.setattr(build_db, "PROC", repo / "data" / "processed")
    monkeypatch.setattr(build_db, "DOCS", tmp_path)
    monkeypatch.setattr(build_db, "PARTY_DOCS", tmp_path / "parties")
    (tmp_path / "parties").mkdir()
    build_db.build_markdown()
    assert (tmp_path / "ANALYSIS.md").read_bytes() == (repo / "docs" / "ANALYSIS.md").read_bytes()
    names = sorted(p.name for p in (repo / "docs" / "parties").iterdir())
    assert sorted(p.name for p in (tmp_path / "parties").iterdir()) == names
    for n in names:
        assert (tmp_path / "parties" / n).read_bytes() == (repo / "docs" / "parties" / n).read_bytes(), n
