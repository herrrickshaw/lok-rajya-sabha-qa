"""scripts/compare_pib.py: PQ vs PIB ministry ratios and scheme-name extraction (PIB sqlite built in tmp)."""
import csv
import json
import sqlite3
from collections import Counter

import pytest


@pytest.fixture
def P(load):
    return load("compare_pib")


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def test_paths_never_point_at_the_owner_home(P):
    assert not str(P.PIB_DB).startswith("/Users/")


def rec(R, name, q, pib, minister=""):
    return R.MinistryRecord(pq_ministry=name, pq_total_questions=q, pib_releases_since_2024_06=pib, minister_name=minister,
                            minister_designation="Minister" if minister else "")


def test_ministry_comparison(P, repo, capsys):
    import ministry_registry as R
    reg = {"A": rec(R, "A", 10, 4, "Shri A"), "B": rec(R, "B", 5, 0), "C": rec(R, "C", 9, 3), "D": rec(R, "D", 1, 3)}
    rows = P.ministry_comparison(reg)
    assert [r["ministry"] for r in rows] == ["C", "A", "D", "B"]                         # descending ratio; no PIB releases sorts last
    by = {r["ministry"]: r for r in rows}
    assert by["A"]["pq_per_pib_release"] == 2.5 and by["C"]["pq_per_pib_release"] == 3.0 and by["D"]["pq_per_pib_release"] == 0.333
    assert by["B"]["pq_per_pib_release"] is None and by["A"]["minister_in_charge"] == "Shri A"
    with open(repo / "data/processed/pib_ministry_comparison.csv", newline="") as f:
        out = list(csv.DictReader(f))
    assert [r["ministry"] for r in out] == ["C", "A", "D", "B"]
    assert out[-1]["pq_per_pib_release"] == "" and list(out[0]) == ["ministry", "minister_in_charge", "minister_designation", "pq_questions", "pib_releases_since_2024_06", "pq_per_pib_release"]
    assert "Ministry comparison: 3/4 PQ ministries matched to a PIB label, 1/4 matched to a minister-in-charge" in capsys.readouterr().out


@pytest.mark.parametrize("text,expected", [
    ("Pradhan Mantri Awas Yojana funds", ["Pradhan Mantri Awas Yojana"]),
    ("Status of PM-KISAN and PMAY", ["PM-KISAN"]),
    ("Digital India Mission progress", ["Digital India Mission"]),
    ("Swachh Bharat Abhiyan", ["Swachh Bharat Abhiyan"]),
    ("PLI Scheme for Textiles Sector", ["PLI Scheme for Textiles Sector"]),
    ("the government and State Government", []),
    ("PM-ABC", ["PM-ABC"]),
    ("PM-AB", []),                                    # 5 characters: shorter than 6 is dropped
    ("", []), (None, []),
])
def test_extract_schemes(P, text, expected):
    c = Counter()
    P.extract_schemes(text, c)
    assert sorted(c) == sorted(expected)


def test_extract_schemes_counts_repeats(P):
    c = Counter()
    P.extract_schemes("Awas Yojana and Awas Yojana", c)
    assert c["Awas Yojana"] == 2


def make_pib(repo, rows):
    p = repo / "ext/pib_index.sqlite"
    p.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE pib_items(id INTEGER, kind TEXT, date TEXT, ministry TEXT, title TEXT)")
    con.executemany("INSERT INTO pib_items VALUES (?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return con


def test_scheme_comparison_threshold_collapse_and_pib_counts(P, repo, capsys):
    cols = ["subject", "question_text"]
    write_csv(repo / "data/processed/ls_questions_enriched.csv", [dict(subject="Awas Yojana status") for _ in range(5)] + [dict(subject="Rare Abhiyan")], cols)
    write_csv(repo / "data/processed/rs_questions_enriched.csv",
              [dict(subject="Awas Scheme", question_text="about the Awas Mission and Swachh Mission") for _ in range(3)]
              + [dict(subject="Swachh Mission", question_text="") for _ in range(5)], cols)
    make_pib(repo, [(1, "release", "2024-06-01", "m", "Awas Yojana launched"), (2, "release", "2024-05-31", "m", "Awas Yojana old"),
                    (3, "factsheet", "2025-01-01", "m", "Awas Yojana factsheet"), (4, "release", "2025-01-01", "m", "Other news")])
    import sqlite3 as sq
    con = sq.connect(P.PIB_DB)
    rows = P.scheme_comparison(con)
    # 'Awas Yojana' (5+...) is collapsed with trailing-word variants; Rare Abhiyan (1) is below the >= 8 cut-off
    by = {r["term"]: r for r in rows}
    assert "Rare Abhiyan" not in by
    awas = next(r for t, r in by.items() if t.lower().startswith("awas"))
    assert awas["pib_release_mentions"] == 1                                                 # date >= since, kind = release, title LIKE
    swachh = next(r for t, r in by.items() if t.lower().startswith("swachh"))
    assert swachh["pq_mentions"] == 8 and swachh["pib_release_mentions"] == 0
    assert [r["pq_mentions"] for r in rows] == sorted((r["pq_mentions"] for r in rows), reverse=True)
    with open(repo / "data/processed/pib_scheme_comparison.csv", newline="") as f:
        assert list(csv.DictReader(f))[0].keys() == {"term", "pq_mentions", "pib_release_mentions"}
    out = capsys.readouterr().out
    assert f"Scheme/topic terms extracted: {len(rows)}" in out
    pq_only_block = out.split("Top PQ-only")[1].split("Top overlapping")[0]
    overlap_block = out.split("Top overlapping")[1]
    assert "Swachh Mission 8" in pq_only_block and "Awas" not in pq_only_block
    assert "Awas" in overlap_block and "pib= 1" in overlap_block and "Swachh" not in overlap_block


def test_scheme_comparison_cutoff_is_inclusive_at_eight(P, repo):
    cols = ["subject", "question_text"]
    write_csv(repo / "data/processed/ls_questions_enriched.csv", [dict(subject="Seven Mission") for _ in range(7)] + [dict(subject="Eight Abhiyan") for _ in range(8)], cols)
    write_csv(repo / "data/processed/rs_questions_enriched.csv", [], cols)
    make_pib(repo, [])
    rows = P.scheme_comparison(sqlite3.connect(P.PIB_DB))
    assert [r["term"] for r in rows] == ["Eight Abhiyan"]


def test_main(P, repo, capsys, monkeypatch):
    import ministry_registry as R
    monkeypatch.setattr(P, "load_registry", lambda: {"A": rec(R, "A", 10, 4, "Shri A")})
    with pytest.raises(SystemExit) as e:
        P.main()
    assert "PIB index not found at" in str(e.value)
    cols = ["subject", "question_text"]
    write_csv(repo / "data/processed/ls_questions_enriched.csv", [dict(subject="Eight Abhiyan") for _ in range(8)], cols)
    write_csv(repo / "data/processed/rs_questions_enriched.csv", [], cols)
    make_pib(repo, [])
    P.main()
    data = json.loads((repo / "site/pib.json").read_text())
    assert data["since"] == "2024-06-01" and data["ministry_comparison"][0]["ministry"] == "A"
    assert data["scheme_comparison"] == [{"term": "Eight Abhiyan", "pq_mentions": 8, "pib_release_mentions": 0}] and "note" in data
    assert capsys.readouterr().out.strip().endswith("pib.json")
