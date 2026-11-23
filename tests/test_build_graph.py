"""scripts/build_graph.py: power-iteration PageRank and the party/ministry/MP knowledge-graph analyses on synthetic questions."""
import csv
import json

import networkx as nx
import pytest


@pytest.fixture
def G(load):
    return load("build_graph")


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ pagerank
def test_pagerank_empty_and_single_node(G):
    assert G.pagerank_power_iteration(nx.Graph()) == {}
    g = nx.Graph()
    g.add_node("a")
    assert G.pagerank_power_iteration(g) == {"a": pytest.approx(1.0)}               # dangling node keeps all the mass


def test_pagerank_symmetric_pair_and_sum_to_one(G):
    g = nx.Graph()
    g.add_edge("a", "b", weight=3)
    r = G.pagerank_power_iteration(g)
    assert r["a"] == pytest.approx(0.5) and r["b"] == pytest.approx(0.5)
    g.add_edge("b", "c", weight=1)
    r = G.pagerank_power_iteration(g)
    assert sum(r.values()) == pytest.approx(1.0) and r["b"] > r["a"] > r["c"]


def test_pagerank_matches_networkx_on_a_path(G):
    g = nx.path_graph(4)
    for u, v in g.edges:
        g[u][v]["weight"] = 1
    ours = G.pagerank_power_iteration(g)
    expected = {0: 0.1754, 1: 0.3246, 2: 0.3246, 3: 0.1754}
    for k, v in expected.items():
        assert ours[k] == pytest.approx(v, abs=1e-3)


def test_pagerank_weights_and_alpha(G):
    g = nx.Graph()
    g.add_edge("hub", "x", weight=10)
    g.add_edge("hub", "y", weight=1)
    r = G.pagerank_power_iteration(g)
    assert r["x"] > r["y"]
    g2 = nx.Graph()
    g2.add_edge("a", "b")                                                           # missing weight attr defaults to 1.0
    g2.add_edge("b", "c", weight=0)                                                 # zero weight is treated as 1.0
    r2 = G.pagerank_power_iteration(g2)
    assert r2["b"] > r2["a"] and r2["a"] == pytest.approx(r2["c"])
    iso = nx.Graph()
    iso.add_edge("a", "b")
    iso.add_node("z")
    r3 = G.pagerank_power_iteration(iso, alpha=0.5)
    assert sum(r3.values()) == pytest.approx(1.0) and r3["z"] < r3["a"] + 1


# ------------------------------------------------------------------ main
ROW_COLS = ["chamber", "ques_no", "session_no", "party", "ministry", "state", "member", "all_members"]


def q(chamber, no, party, ministry, state, member, all_members=""):
    return dict(chamber=chamber, ques_no=no, session_no="1", party=party, ministry=ministry, state=state, member=member, all_members=all_members)


@pytest.fixture
def corpus(repo):
    ls = []
    n = 0
    # three parties of 40 questions each, with different ministry emphasis; A and B overlap, C is distinct
    plan = {"A": {"HEALTH": 25, "RAIL": 15}, "B": {"HEALTH": 20, "RAIL": 15, "EDU": 5}, "C": {"EDU": 30, "RAIL": 10}}
    for party, mins in plan.items():
        for ministry, cnt in mins.items():
            for _ in range(cnt):
                n += 1
                ls.append(q("Lok Sabha", n, party, ministry, "Kerala" if party == "A" else "Goa", f"MP {party}{n % 3}"))
    ls.append(q("Lok Sabha", 900, "A", "HEALTH", "Kerala", "MP A0", "MP A0; MP B0; MP C0"))
    ls.append(q("Lok Sabha", 901, "A", "HEALTH", "Kerala", "MP A0", "MP A0; MP B0"))
    ls.append(q("Lok Sabha", 902, "A", "HEALTH", "Kerala", "MP A0", "MP A0"))                    # single member: no co-asking
    rs = [q("Rajya Sabha", 1, "B", "RAIL", "Goa", "RS B", "RS B; RS X")]                          # RS joint members are not used for co-asking
    write_csv(repo / "data/processed/ls_questions_enriched.csv", ls, ROW_COLS)
    write_csv(repo / "data/processed/rs_questions_enriched.csv", rs, ROW_COLS)
    write_csv(repo / "data/processed/topic_keywords.csv", [
        dict(party="ALL", term="ignored", count=99), dict(party="A", term="hospital", count=7), dict(party="C", term="school", count=9)], ["party", "term", "count"])
    return repo


def test_load_helpers(G, corpus):
    assert len(G.load_all_rows()) == 3 * 40 + 3 + 1
    assert dict(G.load_topics()) == {"A": [("hospital", 7)], "C": [("school", 9)]}
    p = corpus / "x.csv"
    G.write_csv(p, [{"a": 1}], ["a"])
    assert G.read_csv(p) == [{"a": "1"}]


def test_main_lift_pagerank_and_graph_outputs(G, corpus, capsys):
    G.main()
    proc = corpus / "data/processed"
    lift = read_csv(proc / "kg_party_ministry_lift.csv")
    assert list(lift[0]) == ["party", "ministry", "questions", "ministry_total", "party_total", "lift"]
    by = {(r["party"], r["ministry"]): r for r in lift}
    total = 124                                                                      # 3 x 40 + 3 LS joint + 1 RS
    a_health = by[("A", "HEALTH")]
    # A: 43 questions, HEALTH total 25+20+3 = 48; expected = 48 * 43/124 ; lift = 28 / expected
    assert (a_health["questions"], a_health["ministry_total"], a_health["party_total"]) == ("28", "48", "43")
    assert a_health["lift"] == str(round(28 / (48 * 43 / 124), 3))
    lifts = [float(r["lift"]) for r in lift]
    assert lifts == sorted(lifts, reverse=True)                                       # strongest signature first
    pr = read_csv(proc / "kg_pagerank.csv")
    assert list(pr[0]) == ["node", "type", "label", "pagerank"] and {r["type"] for r in pr} == {"party", "ministry", "topic"}
    assert float(pr[0]["pagerank"]) >= float(pr[-1]["pagerank"])
    assert sum(float(r["pagerank"]) for r in pr) == pytest.approx(1.0, abs=1e-3)
    comm = read_csv(proc / "kg_party_communities.csv")
    assert {r["party"] for r in comm} == {"A", "B", "C"} and list(comm[0]) == ["community", "party", "questions", "community_size"]
    assert all(int(r["community_size"]) >= 1 for r in comm)
    co = read_csv(proc / "kg_ministry_cooccurrence.csv")
    assert all(r["ministry_a"] < r["ministry_b"] for r in co) and any(r["shared_mps"] != "0" for r in co)
    bridges = read_csv(proc / "kg_mp_coasking_bridges.csv")
    got = {(r["mp_a"], r["mp_b"]): (r["party_a"], r["party_b"], r["joint_questions"]) for r in bridges}
    assert got == {("MP A0", "MP B0"): ("A", "B", "2"), ("MP A0", "MP C0"): ("A", "C", "1"),
                   ("MP B0", "MP C0"): ("B", "C", "1")}      # Lok Sabha only; same-party pairs excluded
    assert [r["joint_questions"] for r in bridges] == ["2", "1", "1"]
    assert (proc / "graph.graphml").exists() and nx.read_graphml(proc / "graph.graphml").number_of_nodes() > 10
    payload = json.loads((corpus / "site/graph.json").read_text())
    assert payload["stats"]["parties"] == 3 and payload["stats"]["ministries"] == 3 and payload["stats"]["cross_party_coasking_pairs"] == 3
    assert all(r["questions"] >= 15 for r in payload["signature_ministries"]) and len(payload["signature_ministries"]) == 5
    assert payload["stats"]["mps"] == len({r["member"] for r in G.load_all_rows()})
    out = capsys.readouterr().out
    assert "Cross-party co-asking bridges: 3" in out and out.startswith("Graph nodes: ")


def test_main_excludes_small_parties_from_communities(G, repo):
    rows = [q("Lok Sabha", i, "Big", "HEALTH" if i % 2 else "RAIL", "Goa", f"M{i % 2}") for i in range(30)]
    rows += [q("Lok Sabha", 100 + i, "Tiny", "HEALTH", "Goa", "T") for i in range(29)]          # one short of MIN_PARTY_QUESTIONS
    rows += [q("Lok Sabha", 200 + i, "Edge", "RAIL", "Goa", "E") for i in range(30)]             # exactly 30: included
    write_csv(repo / "data/processed/ls_questions_enriched.csv", rows, ROW_COLS)
    write_csv(repo / "data/processed/rs_questions_enriched.csv", [], ROW_COLS)
    write_csv(repo / "data/processed/topic_keywords.csv", [], ["party", "term", "count"])
    G.main()
    comm = read_csv(repo / "data/processed/kg_party_communities.csv")
    assert {r["party"] for r in comm} == {"Big", "Edge"}


def test_main_blank_fields_become_unknown(G, repo):
    rows = [dict(chamber="Lok Sabha", ques_no="1", session_no="1", party="", ministry="", state="", member="", all_members="")]
    write_csv(repo / "data/processed/ls_questions_enriched.csv", rows, ROW_COLS)
    write_csv(repo / "data/processed/rs_questions_enriched.csv", [], ROW_COLS)
    write_csv(repo / "data/processed/topic_keywords.csv", [], ["party", "term", "count"])
    G.main()
    lift = read_csv(repo / "data/processed/kg_party_ministry_lift.csv")
    assert lift == [{"party": "Unknown", "ministry": "Unknown", "questions": "1", "ministry_total": "1", "party_total": "1", "lift": "1.0"}]
    assert json.loads((repo / "site/graph.json").read_text())["stats"]["mps"] == 1


def test_main_parties_with_no_shared_ministry_land_in_separate_communities(G, repo):
    rows = [q("Lok Sabha", i, "P1", "HEALTH", "Goa", "M1") for i in range(30)] + [q("Lok Sabha", 100 + i, "P2", "RAIL", "Goa", "M2") for i in range(30)]
    write_csv(repo / "data/processed/ls_questions_enriched.csv", rows, ROW_COLS)
    write_csv(repo / "data/processed/rs_questions_enriched.csv", [], ROW_COLS)
    write_csv(repo / "data/processed/topic_keywords.csv", [], ["party", "term", "count"])
    G.main()
    comm = read_csv(repo / "data/processed/kg_party_communities.csv")
    assert {r["party"] for r in comm} == {"P1", "P2"} and {r["community_size"] for r in comm} == {"1"}
    assert len({r["community"] for r in comm}) == 2
