from __future__ import annotations

from build import cross_tab, party_summary, tokenize, top_terms
from build_graph import Counts, build_base_graph, cross_party_bridges, lift_table, pagerank_power_iteration

import networkx as nx


def _row(party, ministry, chamber="Lok Sabha", state="Goa", type_="STARRED", subject="x", **kw):
    r = {"party": party, "ministry": ministry, "chamber": chamber, "state": state, "type": type_,
         "subject": subject, "member": kw.get("member", party + "-mp"), "ques_no": kw.get("q", "1"),
         "session_no": "1", "all_members": kw.get("all_members", "")}
    return r


def test_party_summary_orders_by_total():
    rows = [_row("A", "M"), _row("B", "M", "Rajya Sabha"), _row("B", "M")]
    assert party_summary(rows)[0] == {"party": "B", "lok_sabha_questions": 1,
                                      "rajya_sabha_questions": 1, "total_questions": 2}


def test_cross_tab_columns_and_fixed_columns():
    rows = [_row("A", "X"), _row("A", "Y"), _row("B", "Y")]
    tab, cols = cross_tab(rows, "party", lambda r: r["party"], lambda r: r["ministry"])
    assert cols == ["X", "Y"] and tab == [{"party": "A", "X": 1, "Y": 1}, {"party": "B", "X": 0, "Y": 1}]
    tab2, cols2 = cross_tab(rows, "party", lambda r: r["party"], lambda r: r["ministry"], columns=["Y", "Z"])
    assert tab2[0] == {"party": "A", "Y": 1, "Z": 0} and cols2 == ["Y", "Z"]


def test_tokenize_and_top_terms_keep_repeated_bigrams():
    assert tokenize("The Railway of the State 12") == ["railway"]
    rows = [{"subject": "railway safety measures"}] * 3
    terms = dict(top_terms(rows))
    assert terms["railway safety"] == 3 and "railway" not in terms


def test_lift_and_bridges():
    rows = [_row("A", "X", member="m1", all_members="m1; m2", q="7"),
            _row("A", "X", member="m2"), _row("B", "Y", member="m3")]
    rows[1]["party"] = "B"
    _, c = build_base_graph(rows)
    lifts = lift_table(c)
    assert {(r["party"], r["ministry"]) for r in lifts} == {("A", "X"), ("B", "X"), ("B", "Y")}
    # m1 (A) and m2 (B) co-signed question 7
    assert cross_party_bridges(c) == [
        {"mp_a": "m1", "party_a": "A", "mp_b": "m2", "party_b": "B", "joint_questions": 1}]
    assert isinstance(c, Counts)


def test_pagerank_sums_to_one_and_ranks_hub_first():
    g = nx.Graph()
    g.add_edge("hub", "a", weight=1)
    g.add_edge("hub", "b", weight=1)
    g.add_edge("hub", "c", weight=1)
    pr = pagerank_power_iteration(g)
    assert abs(sum(pr.values()) - 1) < 1e-6 and max(pr, key=pr.get) == "hub"
    assert pagerank_power_iteration(nx.Graph()) == {}
