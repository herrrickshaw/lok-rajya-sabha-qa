"""
Build a heterogeneous knowledge graph over the enriched PQ dataset and run
a handful of graph analyses that go beyond flat party/ministry/state
pivot tables:

Node types : Party, Ministry, State, MP, Topic (subject keyword)
Edge types : MP -[MEMBER_OF]-> Party
             MP -[REPRESENTS]-> State
             MP -[ASKED {chamber,count}]-> Ministry      (weighted)
             MP -[RAISED {count}]-> Topic                (weighted)
             Party -[FOCUSES_ON {count}]-> Ministry       (weighted, aggregated)
             Party -[FOCUSES_ON_TOPIC {count}]-> Topic     (weighted, aggregated)
             MP -[CO_ASKED {count}]-> MP                  (co-signed LS questions)
             Ministry -[CO_RAISED {count}]-- Ministry     (same-MP ministry co-occurrence)

Analyses:
  1. Party<->Ministry bipartite affinity: raw share vs "lift" (party's share of a
     ministry's questions divided by the party's overall share of all questions) --
     surfaces a party's *signature* ministries, not just its biggest ones.
  2. PageRank over the Party-Ministry-Topic tripartite graph -- which ministries/
     topics are structurally most central (asked about broadly across many
     parties) vs which are niche to one bloc.
  3. Louvain community detection on the Party-Ministry bipartite projection onto
     parties (parties are "close" if they ask about the same ministries in
     similar proportions) -- do parties cluster along ruling/opposition lines,
     regional-party lines, or something else, based purely on question focus?
  4. Ministry co-occurrence network: ministries frequently probed by the *same*
     MP -- reveals thematic linkage (e.g. Finance <-> Commerce) independent of
     any party lens.
  5. MP co-asking network (Lok Sabha only, from joint/multi-member questions) --
     rare cross-party collaboration edges, and which MPs bridge parties.

Outputs:
  data/processed/graph.graphml            (full heterogeneous graph, Gephi/Cytoscape-ready)
  data/processed/kg_party_ministry_lift.csv
  data/processed/kg_pagerank.csv
  data/processed/kg_party_communities.csv
  data/processed/kg_ministry_cooccurrence.csv
  data/processed/kg_mp_coasking_bridges.csv
  site/graph.json                          (compact graph + analysis payload for the artifact)
"""
import csv
import json
from pathlib import Path
from collections import defaultdict, Counter
from itertools import combinations

import networkx as nx
from networkx.algorithms.community import louvain_communities


def pagerank_power_iteration(G, weight="weight", alpha=0.85, max_iter=200, tol=1e-10):
    """Pure-Python power-iteration PageRank (avoids the scipy dependency that
    networkx.pagerank now requires, which isn't installable in this sandboxed
    environment without touching the system Python)."""
    nodes = list(G.nodes())
    n = len(nodes)
    if n == 0:
        return {}
    idx = {node: i for i, node in enumerate(nodes)}
    out_weight = [0.0] * n
    adj = [[] for _ in range(n)]  # adj[i] = [(j, w), ...] edges i->j (undirected treated both ways)
    for u, v, data in G.edges(data=True):
        w = float(data.get(weight, 1.0)) or 1.0
        ui, vi = idx[u], idx[v]
        adj[ui].append((vi, w))
        adj[vi].append((ui, w))
        out_weight[ui] += w
        out_weight[vi] += w

    rank = [1.0 / n] * n
    for _ in range(max_iter):
        new_rank = [(1 - alpha) / n] * n
        dangling = sum(rank[i] for i in range(n) if out_weight[i] == 0)
        for i in range(n):
            new_rank[i] += alpha * dangling / n
        for i in range(n):
            if out_weight[i] == 0:
                continue
            share = alpha * rank[i] / out_weight[i]
            for j, w in adj[i]:
                new_rank[j] += share * w
        diff = sum(abs(new_rank[i] - rank[i]) for i in range(n))
        rank = new_rank
        if diff < tol:
            break
    return {nodes[i]: rank[i] for i in range(n)}

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
SITE = ROOT / "site"


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def load_all_rows():
    ls = read_csv(PROC / "ls_questions_enriched.csv")
    rs = read_csv(PROC / "rs_questions_enriched.csv")
    return ls + rs


def load_topics():
    """party -> [(term, count), ...] from build.py's topic_keywords.csv, excluding the ALL row."""
    rows = read_csv(PROC / "topic_keywords.csv")
    by_party = defaultdict(list)
    for r in rows:
        if r["party"] == "ALL":
            continue
        by_party[r["party"]].append((r["term"], int(r["count"])))
    return by_party


def main():
    rows = load_all_rows()
    party_topics = load_topics()

    G = nx.MultiDiGraph()

    def add_node(node_id, ntype, **attrs):
        if not G.has_node(node_id):
            G.add_node(node_id, type=ntype, **attrs)

    mp_party = {}
    mp_state = {}
    mp_chamber = {}
    party_question_count = Counter()
    party_ministry = defaultdict(Counter)
    ministry_total = Counter()
    mp_ministry = defaultdict(Counter)
    mp_questions_by_row_key = defaultdict(list)  # for co-asking: (chamber, ques_no) -> [mp,...]

    for r in rows:
        party = r["party"] or "Unknown"
        ministry = r["ministry"] or "Unknown"
        state = r["state"] or "Unknown"
        mp = r["member"] or "Unknown"
        chamber = r["chamber"]

        add_node(f"party:{party}", "Party", label=party)
        add_node(f"ministry:{ministry}", "Ministry", label=ministry)
        add_node(f"state:{state}", "State", label=state)
        add_node(f"mp:{mp}", "MP", label=mp, party=party, state=state, chamber=chamber)

        mp_party[mp] = party
        mp_state[mp] = state
        mp_chamber[mp] = chamber

        party_question_count[party] += 1
        party_ministry[party][ministry] += 1
        ministry_total[ministry] += 1
        mp_ministry[mp][ministry] += 1

        if not G.has_edge(f"mp:{mp}", f"party:{party}", key="MEMBER_OF"):
            G.add_edge(f"mp:{mp}", f"party:{party}", key="MEMBER_OF", type="MEMBER_OF")
        if not G.has_edge(f"mp:{mp}", f"state:{state}", key="REPRESENTS"):
            G.add_edge(f"mp:{mp}", f"state:{state}", key="REPRESENTS", type="REPRESENTS")

        # LS joint questions: attribute co-asking edges among all listed members
        if chamber == "Lok Sabha" and r.get("all_members"):
            members = [m.strip() for m in r["all_members"].split(";") if m.strip()]
            if len(members) > 1:
                key = (chamber, r["ques_no"], r["session_no"])
                mp_questions_by_row_key[key] = members

    total_questions = sum(party_question_count.values())

    # Weighted MP -> Ministry edges (ASKED)
    for mp, counter in mp_ministry.items():
        party = mp_party.get(mp, "Unknown")
        for ministry, cnt in counter.items():
            G.add_edge(
                f"mp:{mp}", f"ministry:{ministry}", key="ASKED",
                type="ASKED", weight=cnt,
            )

    # Aggregated Party -> Ministry edges (FOCUSES_ON)
    for party, counter in party_ministry.items():
        for ministry, cnt in counter.items():
            G.add_edge(
                f"party:{party}", f"ministry:{ministry}", key="FOCUSES_ON",
                type="FOCUSES_ON", weight=cnt,
            )

    # Party -> Topic edges (FOCUSES_ON_TOPIC), from build.py's per-party keyword extraction
    for party, terms in party_topics.items():
        for term, cnt in terms:
            add_node(f"topic:{term}", "Topic", label=term)
            G.add_edge(
                f"party:{party}", f"topic:{term}", key="FOCUSES_ON_TOPIC",
                type="FOCUSES_ON_TOPIC", weight=cnt,
            )

    # ---- Analysis 1: Party<->Ministry lift (signature ministries) ----
    lift_rows = []
    for party, counter in party_ministry.items():
        party_share = party_question_count[party] / total_questions
        for ministry, cnt in counter.items():
            expected = ministry_total[ministry] * party_share
            lift = cnt / expected if expected > 0 else 0
            lift_rows.append(
                {
                    "party": party,
                    "ministry": ministry,
                    "questions": cnt,
                    "ministry_total": ministry_total[ministry],
                    "party_total": party_question_count[party],
                    "lift": round(lift, 3),
                }
            )
    lift_rows.sort(key=lambda r: (-r["lift"], -r["questions"]))
    # keep it meaningful: require a minimum volume so single-question flukes don't dominate
    signature_rows = [r for r in lift_rows if r["questions"] >= 15]
    write_csv(
        PROC / "kg_party_ministry_lift.csv",
        lift_rows,
        ["party", "ministry", "questions", "ministry_total", "party_total", "lift"],
    )

    # ---- Analysis 2: PageRank over Party-Ministry-Topic tripartite graph ----
    tri = nx.Graph()
    for party, counter in party_ministry.items():
        for ministry, cnt in counter.items():
            tri.add_edge(f"party:{party}", f"ministry:{ministry}", weight=cnt)
    for party, terms in party_topics.items():
        for term, cnt in terms:
            tri.add_edge(f"party:{party}", f"topic:{term}", weight=cnt)
    pagerank = pagerank_power_iteration(tri, weight="weight")
    pr_rows = [
        {"node": n, "type": n.split(":", 1)[0], "label": n.split(":", 1)[1], "pagerank": round(v, 6)}
        for n, v in sorted(pagerank.items(), key=lambda kv: -kv[1])
    ]
    write_csv(PROC / "kg_pagerank.csv", pr_rows, ["node", "type", "label", "pagerank"])

    # ---- Analysis 3: Louvain communities on the party projection ----
    # Raw ministry-count vectors are dominated by every party's shared interest
    # in big-ticket portfolios (Health, Railways, Education), which swamps any
    # partisan signal and collapses everything into one community. Clustering
    # on *lift* (how much more/less a party asks about a ministry than its
    # overall share of PQs would predict) isolates each party's relative
    # emphasis instead, which is the actual "who focuses on what" question.
    lift_by_party = defaultdict(dict)
    for r in lift_rows:
        lift_by_party[r["party"]][r["ministry"]] = r["lift"]

    MIN_PARTY_QUESTIONS = 30  # exclude parties too small to have a stable profile
    parties = [p for p in party_ministry if party_question_count[p] >= MIN_PARTY_QUESTIONS]

    party_graph = nx.Graph()
    for p in parties:
        party_graph.add_node(p)
    for p1, p2 in combinations(parties, 2):
        v1, v2 = lift_by_party[p1], lift_by_party[p2]
        shared = set(v1) & set(v2)
        if not shared:
            continue
        dot = sum(v1[m] * v2[m] for m in shared)
        norm1 = sum(v * v for v in v1.values()) ** 0.5
        norm2 = sum(v * v for v in v2.values()) ** 0.5
        if norm1 and norm2:
            sim = dot / (norm1 * norm2)
            if sim > 0.15:
                party_graph.add_edge(p1, p2, weight=sim)

    communities = louvain_communities(party_graph, weight="weight", seed=42)
    community_rows = []
    for i, comm in enumerate(communities):
        for party in comm:
            community_rows.append(
                {
                    "community": i,
                    "party": party,
                    "questions": party_question_count[party],
                    "community_size": len(comm),
                }
            )
    community_rows.sort(key=lambda r: (r["community"], -r["questions"]))
    write_csv(PROC / "kg_party_communities.csv", community_rows, ["community", "party", "questions", "community_size"])

    # ---- Analysis 4: Ministry co-occurrence (same MP asks about both) ----
    ministry_pair_counts = Counter()
    for mp, counter in mp_ministry.items():
        mins = list(counter.keys())
        for m1, m2 in combinations(sorted(mins), 2):
            ministry_pair_counts[(m1, m2)] += 1
    co_rows = [
        {"ministry_a": a, "ministry_b": b, "shared_mps": c}
        for (a, b), c in ministry_pair_counts.most_common(200)
    ]
    write_csv(PROC / "kg_ministry_cooccurrence.csv", co_rows, ["ministry_a", "ministry_b", "shared_mps"])

    # ---- Analysis 5: MP co-asking network + cross-party bridges (LS only) ----
    coask_counts = Counter()
    for members in mp_questions_by_row_key.values():
        uniq = sorted(set(members))
        for m1, m2 in combinations(uniq, 2):
            coask_counts[(m1, m2)] += 1
    bridge_rows = []
    for (m1, m2), cnt in coask_counts.items():
        p1, p2 = mp_party.get(m1, "Unknown"), mp_party.get(m2, "Unknown")
        if p1 != p2:
            bridge_rows.append(
                {"mp_a": m1, "party_a": p1, "mp_b": m2, "party_b": p2, "joint_questions": cnt}
            )
    bridge_rows.sort(key=lambda r: -r["joint_questions"])
    write_csv(PROC / "kg_mp_coasking_bridges.csv", bridge_rows, ["mp_a", "party_a", "mp_b", "party_b", "joint_questions"])

    # ---- Persist full graph ----
    nx.write_graphml(G, PROC / "graph.graphml")

    # ---- Compact JSON payload for the artifact ----
    graph_payload = {
        "stats": {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "parties": len(parties),
            "ministries": len(ministry_total),
            "mps": len(mp_party),
            "cross_party_coasking_pairs": len(bridge_rows),
        },
        "signature_ministries": signature_rows[:60],
        "pagerank_top": pr_rows[:40],
        "party_communities": community_rows,
        "ministry_cooccurrence_top": co_rows[:40],
        "cross_party_bridges_top": bridge_rows[:30],
    }
    (SITE / "graph.json").write_text(json.dumps(graph_payload, indent=2))

    print("Graph nodes:", G.number_of_nodes(), "edges:", G.number_of_edges())
    print("Communities:", len(communities), [len(c) for c in communities])
    print("Top signature ministries (lift, min 15 q):")
    for r in signature_rows[:15]:
        print(" ", r["party"], "->", r["ministry"], "lift", r["lift"], "n=", r["questions"])
    print("Cross-party co-asking bridges:", len(bridge_rows))


if __name__ == "__main__":
    main()
