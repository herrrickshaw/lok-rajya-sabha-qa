"""PageRank and lift checks for scripts/build_graph.py against networkx and
hand-computed values."""
import networkx as nx
import pytest

import build_graph as g


def test_pagerank_matches_networkx_on_weighted_graph_with_isolated_node():
    G = nx.Graph()
    G.add_edge("party:A", "ministry:X", weight=3)
    G.add_edge("party:A", "ministry:Y", weight=1)
    G.add_edge("party:B", "ministry:Y", weight=5)
    G.add_edge("party:B", "topic:rail", weight=2)
    G.add_node("ministry:Z")  # dangling
    ours = g.pagerank_power_iteration(G)
    ref = nx.pagerank(G, weight="weight", tol=1e-12, max_iter=10000)
    for n in G:
        assert ours[n] == pytest.approx(ref[n], abs=1e-8)
    assert sum(ours.values()) == pytest.approx(1.0)


def test_pagerank_symmetric_pair_and_empty():
    G = nx.Graph()
    G.add_edge("a", "b", weight=7)
    pr = g.pagerank_power_iteration(G)
    assert pr["a"] == pytest.approx(0.5) and pr["b"] == pytest.approx(0.5)
    assert g.pagerank_power_iteration(nx.Graph()) == {}


def test_pagerank_star_centre_by_hand():
    # Star with centre c and 3 leaves, unit weights. Stationary solution:
    # leaf = (1-a)/4 + a*c/3 ; c = (1-a)/4 + a*3*leaf  -> with a=0.85
    G = nx.Graph([("c", "l1"), ("c", "l2"), ("c", "l3")])
    pr = g.pagerank_power_iteration(G)
    a = 0.85
    leaf = pr["l1"]
    c = pr["c"]
    assert c == pytest.approx((1 - a) / 4 + a * 3 * leaf)
    assert leaf == pytest.approx((1 - a) / 4 + a * c / 3)
