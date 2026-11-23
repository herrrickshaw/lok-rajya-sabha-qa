"""scripts/build_db.py: DuckDB load + per-party briefs + docs/ANALYSIS.md from synthetic processed CSVs."""
import csv

import duckdb
import pytest


@pytest.fixture
def DB(load):
    return load("build_db")


def write_csv(repo, name, rows, cols):
    p = repo / "data/processed" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


QCOLS = ["chamber", "ques_no", "session_no", "date", "type", "ministry", "subject", "member", "all_members", "party", "party_full", "state",
         "question_text", "answer_text", "answer_pdf_url"]


def qrow(chamber, no, party="BJP", text=""):
    return dict(chamber=chamber, ques_no=no, session_no="1", date="d", type="STARRED", ministry="HEALTH", subject="s", member="m", all_members="m",
                party=party, party_full=party, state="Goa", question_text=text, answer_text="", answer_pdf_url="")


@pytest.fixture
def processed(repo):
    write_csv(repo, "ls_questions_enriched.csv", [qrow("Lok Sabha", 1), qrow("Lok Sabha", 2, "INC")], QCOLS)
    write_csv(repo, "rs_questions_enriched.csv", [qrow("Rajya Sabha", 1, text="full text")], QCOLS)
    write_csv(repo, "party_summary.csv", [
        dict(party="BJP", lok_sabha_questions=60, rajya_sabha_questions=40, total_questions=100),
        dict(party="INC", lok_sabha_questions=30, rajya_sabha_questions=20, total_questions=50),
        dict(party="Tiny", lok_sabha_questions=10, rajya_sabha_questions=39, total_questions=49),
        dict(party="Unknown", lok_sabha_questions=300, rajya_sabha_questions=0, total_questions=300),
        dict(party="Odd/Name & Co.", lok_sabha_questions=80, rajya_sabha_questions=0, total_questions=80)],
        ["party", "lok_sabha_questions", "rajya_sabha_questions", "total_questions"])
    write_csv(repo, "ministry_summary.csv", [dict(ministry="HEALTH", questions=7), dict(ministry="RAIL", questions=900)], ["ministry", "questions"])
    write_csv(repo, "state_summary.csv", [dict(state="Goa", questions=2), dict(state="Kerala", questions=10)], ["state", "questions"])
    write_csv(repo, "party_type_matrix.csv", [dict(party="BJP", STARRED=30, UNSTARRED=70), dict(party="INC", STARRED=3, UNSTARRED=6)], ["party", "STARRED", "UNSTARRED"])
    write_csv(repo, "kg_party_ministry_lift.csv", [
        dict(party="BJP", ministry="RAIL", questions=40, ministry_total=100, party_total=100, lift=2.5),
        dict(party="BJP", ministry="HEALTH", questions=10, ministry_total=100, party_total=100, lift=3.0),
        dict(party="BJP", ministry="LOW", questions=9, ministry_total=100, party_total=100, lift=9.9),
        dict(party="BJP", ministry="MID", questions=20, ministry_total=100, party_total=100, lift=1.25)],
        ["party", "ministry", "questions", "ministry_total", "party_total", "lift"])
    write_csv(repo, "kg_party_communities.csv", [dict(community=0, party="BJP", questions=100, community_size=1), dict(community=1, party="INC", questions=50, community_size=1),
                                                dict(community=7, party="Odd/Name & Co.", questions=80, community_size=1)],
              ["community", "party", "questions", "community_size"])
    write_csv(repo, "topic_keywords.csv", [dict(party="ALL", term="skip", count=99), dict(party="BJP", term="rail safety", count=5), dict(party="BJP", term="hospital", count=9)],
              ["party", "term", "count"])
    write_csv(repo, "kg_mp_coasking_bridges.csv", [dict(mp_a="A", party_a="BJP", mp_b="B", party_b="INC", joint_questions=1),
                                                  dict(mp_a="C", party_a="BJP", mp_b="D", party_b="INC", joint_questions=5)],
              ["mp_a", "party_a", "mp_b", "party_b", "joint_questions"])
    write_csv(repo, "kg_pagerank.csv", [dict(node="party:BJP", type="party", label="BJP", pagerank=0.1), dict(node="ministry:RAIL", type="ministry", label="RAIL", pagerank=0.2)],
              ["node", "type", "label", "pagerank"])
    write_csv(repo, "pib_ministry_comparison.csv", [
        dict(ministry="RAIL", minister_in_charge="", minister_designation="", pq_questions=900, pib_releases_since_2024_06=10, pq_per_pib_release=90.0),
        dict(ministry="HEALTH", minister_in_charge="", minister_designation="", pq_questions=7, pib_releases_since_2024_06=70, pq_per_pib_release=0.1),
        dict(ministry="NONE", minister_in_charge="", minister_designation="", pq_questions=3, pib_releases_since_2024_06=0, pq_per_pib_release="")],
        ["ministry", "minister_in_charge", "minister_designation", "pq_questions", "pib_releases_since_2024_06", "pq_per_pib_release"])
    write_csv(repo, "pib_scheme_comparison.csv", [dict(term="PM-KISAN", pq_mentions=12, pib_release_mentions=0), dict(term="Awas Yojana", pq_mentions=9, pib_release_mentions=4)],
              ["term", "pq_mentions", "pib_release_mentions"])
    write_csv(repo, "pli_scheme_scrutiny.csv", [
        dict(scheme="PLI Drones", pq_ministry="CIVIL AVIATION", minister_in_charge="", ministry_total_pq=1, scheme_pq_mentions=3, outlay_rs_cr=120, disbursed_rs_cr=30, disbursed_pct=25.0, grade="B", grade_evidence=""),
        dict(scheme="PLI Steel", pq_ministry="STEEL", minister_in_charge="Shri S", ministry_total_pq=1, scheme_pq_mentions=0, outlay_rs_cr=0, disbursed_rs_cr=0, disbursed_pct="", grade="F", grade_evidence="")],
        ["scheme", "pq_ministry", "minister_in_charge", "ministry_total_pq", "scheme_pq_mentions", "outlay_rs_cr", "disbursed_rs_cr", "disbursed_pct", "grade", "grade_evidence"])
    write_csv(repo, "ministry_scheme_scrutiny.csv", [
        dict(ministry="MeitY", scheme="SPECS", pq_mentions=0, months_since_update=30, outlay_rs_cr_mentioned=""),
        dict(ministry="MeitY", scheme="Other", pq_mentions=5, months_since_update=2, outlay_rs_cr_mentioned=100),
        dict(ministry="DoT", scheme="BharatNet", pq_mentions=9, months_since_update="", outlay_rs_cr_mentioned=""),
        dict(ministry="DoT", scheme="Exactly a year", pq_mentions=1, months_since_update=12, outlay_rs_cr_mentioned="")],
        ["ministry", "scheme", "pq_mentions", "months_since_update", "outlay_rs_cr_mentioned"])
    write_csv(repo, "parivesh_state_comparison.csv", [dict(state="Gujarat", ec_proposals=900, environment_pqs=10, pq_per_ec_proposal=""), dict(state="Goa", ec_proposals=5, environment_pqs=10, pq_per_ec_proposal=2.0)],
              ["state", "ec_proposals", "environment_pqs", "pq_per_ec_proposal"])
    write_csv(repo, "parivesh_mega_projects.csv", [
        dict(company="Adani Power", investment_cost_rs=5e10, company_mentioned_in_pq="False"), dict(company="Vedanta", investment_cost_rs=1e10, company_mentioned_in_pq="True"),
        dict(company="", investment_cost_rs="", company_mentioned_in_pq="")], ["company", "investment_cost_rs", "company_mentioned_in_pq"])


def test_main_builds_database(DB, repo, processed, capsys):
    (repo / "data/pq_ledger.duckdb").write_text("stale")
    DB.main()
    con = duckdb.connect(str(repo / "data/pq_ledger.duckdb"), read_only=True)
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert {"ls_questions", "rs_questions", "party_summary", "ministry_summary", "state_summary", "party_type_matrix_wide",
            "kg_party_ministry_lift", "kg_pagerank", "kg_party_communities", "all_questions", "party_ranking", "pib_scheme_comparison",
            "pli_scheme_scrutiny", "ministry_scheme_scrutiny", "parivesh_state_comparison", "parivesh_mega_projects", "topic_keywords", "kg_mp_coasking_bridges"} <= tables
    assert "party_ministry_matrix_wide" not in tables and "unmatched_members" not in tables          # no CSV on disk -> table skipped
    assert con.execute("SELECT COUNT(*) FROM all_questions").fetchone()[0] == 3
    assert con.execute("SELECT chamber, COUNT(*) FROM all_questions GROUP BY 1 ORDER BY 1").fetchall() == [("Lok Sabha", 2), ("Rajya Sabha", 1)]
    ranking = con.execute("SELECT party, rank FROM party_ranking ORDER BY rank, party").fetchall()
    assert ranking == [("Unknown", 1), ("BJP", 2), ("Odd/Name & Co.", 3), ("INC", 4), ("Tiny", 5)]
    out = capsys.readouterr().out
    assert "all_questions: 3 rows, 1 with full question text (Rajya Sabha only)" in out
    assert "Wrote " + str(repo / "data/pq_ledger.duckdb") in out
    assert "Wrote docs/ANALYSIS.md and 3 party briefs in docs/parties/" in out


def test_party_briefs(DB, repo, processed):
    DB.main()
    briefs = sorted(p.name for p in (repo / "docs/parties").iterdir())
    assert briefs == ["bjp.md", "inc.md", "odd-name-co.md"]                                   # >= 50 only, never Unknown/Tiny
    bjp = (repo / "docs/parties/bjp.md").read_text()
    assert bjp.startswith("# BJP\n\n**Total Parliament Questions:** 100  \n**Lok Sabha:** 60 · **Rajya Sabha:** 40\n")
    assert "**Knowledge-graph community:** 1 " in bjp
    assert "**Starred vs. unstarred:** 30 starred / 70 unstarred (30.0% starred" in bjp
    table = bjp[bjp.index("| Ministry | Questions | Lift |"):].split("\n\n")[0].splitlines()
    assert table[2:] == ["| HEALTH | 10 | 3.00x |", "| RAIL | 40 | 2.50x |", "| MID | 20 | 1.25x |"]      # >= 10 questions, lift descending; LOW (9) excluded
    assert "rail safety" not in bjp.split("## Recurring subject-line topics")[0]
    assert "hospital (9), rail safety (5)" in bjp and "skip" not in bjp
    inc = (repo / "docs/parties/inc.md").read_text()
    assert "**Starred vs. unstarred:**" not in inc                                              # 9 typed questions < 10
    assert "## Signature ministries" not in inc and "## Recurring subject-line topics" not in inc
    assert "**Knowledge-graph community:** 2 " in inc
    assert "**Knowledge-graph community:** 8 " in (repo / "docs/parties/odd-name-co.md").read_text()


def test_party_brief_starred_share_needs_ten_questions(DB, repo, processed):
    write_csv(repo, "party_type_matrix.csv", [dict(party="BJP", STARRED=5, UNSTARRED=4), dict(party="INC", STARRED=5, UNSTARRED=5)], ["party", "STARRED", "UNSTARRED"])
    DB.main()
    assert "Starred vs. unstarred" not in (repo / "docs/parties/bjp.md").read_text()
    assert "5 starred / 5 unstarred (50.0% starred" in (repo / "docs/parties/inc.md").read_text()


def test_analysis_document(DB, repo, processed):
    DB.main()
    md = (repo / "docs/ANALYSIS.md").read_text()
    top = md[md.index("## Top parties by total questions"):].split("\n\n")[1].splitlines()
    assert top[0] == "| Rank | Party | Lok Sabha | Rajya Sabha | Total |"
    assert top[2] == "| 1 | Unknown | 300 | 0 | 300 |" and top[3] == "| 2 | BJP | 60 | 40 | 100 |"
    assert "| RAIL | 900 |\n| HEALTH | 7 |" in md and "| Kerala | 10 |\n| Goa | 2 |" in md
    assert "- **Community 1** (1 parties, a left- and minority-interest bloc): BJP" in md
    assert "- **Community 8** (1 parties, ): Odd/Name & Co." in md
    assert "| C | BJP | D | INC | 5 |" in md and md.index("| C | BJP | D | INC | 5 |") < md.index("| A | BJP | B | INC | 1 |")
    assert "| RAIL | 900 | 10 | 90.0x |" in md and "| HEALTH | 7 | 70 | 0.10x |" in md and "NONE" not in md
    assert "| PM-KISAN | 12 | 0 |" not in md.split("*PQ-scrutinised")[0].split("PIB release-title mentions |")[1] and "| Awas Yojana | 9 | 4 |" in md
    assert "- PM-KISAN (12 PQ mentions)" in md
    assert "| B | PLI Drones | — | 3 | 120 | 25.0% |" in md and "| F | PLI Steel | Shri S | 0 | 0 | — |" in md
    assert "**1 of 4 schemes across 2 ministries" in md and "**1 of 4** haven't been touched" in md
    assert "By ministry: DoT 0/2 stale; MeitY 1/2 stale." in md                                      # exactly 12 months is not stale
    assert "| MeitY | Other | 5 | 2 | 100 |" in md and "| DoT | BharatNet | 9 | — | — |" in md
    assert md.index("| DoT | BharatNet | 9") < md.index("| MeitY | Other | 5")
    assert "| Gujarat | 900 | 10 | — |" in md and "| Goa | 5 | 10 | 2.0 |" in md
    assert "| Adani Power | 5000.0 | No |" in md and "| Vedanta | 1000.0 | Yes |" in md and "| *(none named in title)* | — | — |" in md
    assert md.rstrip().endswith("excluded from the mention check rather than falsely counted as unmentioned.")


def test_main_with_no_processed_files_still_builds(DB, repo, capsys):
    (repo / "data/processed").mkdir(parents=True, exist_ok=True)
    with pytest.raises(Exception):
        DB.main()                                           # all_questions view needs ls_questions/rs_questions
