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
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import networkx as nx
from networkx.algorithms.community import louvain_communities

sys.path.insert(0, str(Path(__file__).resolve().parent))

from csv_io import read_csv_path, write_csv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
SITE = ROOT / "site"

SIGNATURE_MIN_QUESTIONS = 15       # drop single-question flukes from the "signature ministry" list
MIN_PARTY_QUESTIONS = 30           # exclude parties too small to have a stable profile
PARTY_SIMILARITY_THRESHOLD = 0.15  # cosine similarity needed for a party-party edge
LOUVAIN_SEED = 42
COOCCURRENCE_TOP = 200

Row = Dict[str, object]


def pagerank_power_iteration(G, weight: str = "weight", alpha: float = 0.85,
                             max_iter: int = 200, tol: float = 1e-10) -> Dict[str, float]:
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


def load_all_rows(proc: Path = PROC) -> List[Dict[str, str]]:
    """Both chambers' enriched question rows (LS first, then RS)."""
    return read_csv_path(proc / "ls_questions_enriched.csv") + read_csv_path(proc / "rs_questions_enriched.csv")


def load_topics(proc: Path = PROC) -> Dict[str, List[Tuple[str, int]]]:
    """party -> [(term, count), ...] from build.py's topic_keywords.csv, excluding the ALL row."""
    by_party: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    for r in read_csv_path(proc / "topic_keywords.csv"):
        if r["party"] == "ALL":
            continue
        by_party[r["party"]].append((r["term"], int(r["count"])))
    return by_party


@dataclass
class Counts:
    """Question tallies the analyses share, built in one pass over the rows."""

    mp_party: Dict[str, str] = field(default_factory=dict)
    mp_state: Dict[str, str] = field(default_factory=dict)
    mp_chamber: Dict[str, str] = field(default_factory=dict)
    party_question_count: Counter = field(default_factory=Counter)
    party_ministry: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    ministry_total: Counter = field(default_factory=Counter)
    mp_ministry: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    # (chamber, ques_no, session_no) -> co-signing members, LS joint questions only
    joint_questions: Dict[tuple, List[str]] = field(default_factory=dict)


def build_base_graph(rows: Sequence[Dict[str, str]]) -> Tuple[nx.MultiDiGraph, Counts]:
    """Add MP/Party/Ministry/State nodes and MEMBER_OF/REPRESENTS edges; tally counts."""
    G = nx.MultiDiGraph()
    c = Counts()

    def add_node(node_id: str, ntype: str, **attrs) -> None:
        if not G.has_node(node_id):
            G.add_node(node_id, type=ntype, **attrs)

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

        c.mp_party[mp] = party
        c.mp_state[mp] = state
        c.mp_chamber[mp] = chamber

        c.party_question_count[party] += 1
        c.party_ministry[party][ministry] += 1
        c.ministry_total[ministry] += 1
        c.mp_ministry[mp][ministry] += 1

        if not G.has_edge(f"mp:{mp}", f"party:{party}", key="MEMBER_OF"):
            G.add_edge(f"mp:{mp}", f"party:{party}", key="MEMBER_OF", type="MEMBER_OF")
        if not G.has_edge(f"mp:{mp}", f"state:{state}", key="REPRESENTS"):
            G.add_edge(f"mp:{mp}", f"state:{state}", key="REPRESENTS", type="REPRESENTS")

        # LS joint questions: attribute co-asking edges among all listed members
        if chamber == "Lok Sabha" and r.get("all_members"):
            members = [m.strip() for m in r["all_members"].split(";") if m.strip()]
            if len(members) > 1:
                c.joint_questions[(chamber, r["ques_no"], r["session_no"])] = members
    return G, c


def add_weighted_edges(G: nx.MultiDiGraph, c: Counts, party_topics: Dict[str, List[Tuple[str, int]]]) -> None:
    """Add ASKED (MP->Ministry), FOCUSES_ON (Party->Ministry) and FOCUSES_ON_TOPIC edges."""
    for mp, counter in c.mp_ministry.items():
        for ministry, cnt in counter.items():
            G.add_edge(f"mp:{mp}", f"ministry:{ministry}", key="ASKED", type="ASKED", weight=cnt)
    for party, counter in c.party_ministry.items():
        for ministry, cnt in counter.items():
            G.add_edge(f"party:{party}", f"ministry:{ministry}", key="FOCUSES_ON", type="FOCUSES_ON", weight=cnt)
    for party, terms in party_topics.items():
        for term, cnt in terms:
            if not G.has_node(f"topic:{term}"):
                G.add_node(f"topic:{term}", type="Topic", label=term)
            G.add_edge(
                f"party:{party}", f"topic:{term}", key="FOCUSES_ON_TOPIC",
                type="FOCUSES_ON_TOPIC", weight=cnt,
            )


def lift_table(c: Counts) -> List[Row]:
    """Analysis 1: party x ministry lift = observed / (ministry total x party share), best first."""
    total_questions = sum(c.party_question_count.values())
    out: List[Row] = []
    for party, counter in c.party_ministry.items():
        party_share = c.party_question_count[party] / total_questions
        for ministry, cnt in counter.items():
            expected = c.ministry_total[ministry] * party_share
            lift = cnt / expected if expected > 0 else 0
            out.append(
                {
                    "party": party,
                    "ministry": ministry,
                    "questions": cnt,
                    "ministry_total": c.ministry_total[ministry],
                    "party_total": c.party_question_count[party],
                    "lift": round(lift, 3),
                }
            )
    out.sort(key=lambda r: (-r["lift"], -r["questions"]))
    return out


def pagerank_table(c: Counts, party_topics: Dict[str, List[Tuple[str, int]]]) -> List[Row]:
    """Analysis 2: PageRank over the Party-Ministry-Topic tripartite graph."""
    tri = nx.Graph()
    for party, counter in c.party_ministry.items():
        for ministry, cnt in counter.items():
            tri.add_edge(f"party:{party}", f"ministry:{ministry}", weight=cnt)
    for party, terms in party_topics.items():
        for term, cnt in terms:
            tri.add_edge(f"party:{party}", f"topic:{term}", weight=cnt)
    pagerank = pagerank_power_iteration(tri, weight="weight")
    return [
        {"node": n, "type": n.split(":", 1)[0], "label": n.split(":", 1)[1], "pagerank": round(v, 6)}
        for n, v in sorted(pagerank.items(), key=lambda kv: -kv[1])
    ]


def party_communities(c: Counts, lift_rows: Sequence[Row]) -> Tuple[List[Row], List[str], list]:
    """Analysis 3: Louvain communities on party-party cosine similarity of ministry *lift* vectors.

    Raw ministry-count vectors are dominated by every party's shared interest
    in big-ticket portfolios (Health, Railways, Education), which swamps any
    partisan signal and collapses everything into one community. Clustering
    on *lift* isolates each party's relative emphasis instead.
    Returns (csv rows, eligible parties, raw communities).
    """
    lift_by_party: Dict[object, Dict[object, float]] = defaultdict(dict)
    for r in lift_rows:
        lift_by_party[r["party"]][r["ministry"]] = r["lift"]

    parties = [p for p in c.party_ministry if c.party_question_count[p] >= MIN_PARTY_QUESTIONS]

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
            if sim > PARTY_SIMILARITY_THRESHOLD:
                party_graph.add_edge(p1, p2, weight=sim)

    communities = louvain_communities(party_graph, weight="weight", seed=LOUVAIN_SEED)
    rows: List[Row] = []
    for i, comm in enumerate(communities):
        for party in comm:
            rows.append(
                {
                    "community": i,
                    "party": party,
                    "questions": c.party_question_count[party],
                    "community_size": len(comm),
                }
            )
    rows.sort(key=lambda r: (r["community"], -r["questions"]))
    return rows, parties, communities


def ministry_cooccurrence(c: Counts, top: int = COOCCURRENCE_TOP) -> List[Row]:
    """Analysis 4: ministry pairs probed by the same MP, most shared MPs first."""
    pair_counts: Counter = Counter()
    for counter in c.mp_ministry.values():
        for m1, m2 in combinations(sorted(counter.keys()), 2):
            pair_counts[(m1, m2)] += 1
    return [{"ministry_a": a, "ministry_b": b, "shared_mps": n} for (a, b), n in pair_counts.most_common(top)]


def cross_party_bridges(c: Counts) -> List[Row]:
    """Analysis 5: pairs of MPs from different parties who co-signed LS questions."""
    coask: Counter = Counter()
    for members in c.joint_questions.values():
        for m1, m2 in combinations(sorted(set(members)), 2):
            coask[(m1, m2)] += 1
    rows: List[Row] = []
    for (m1, m2), cnt in coask.items():
        p1, p2 = c.mp_party.get(m1, "Unknown"), c.mp_party.get(m2, "Unknown")
        if p1 != p2:
            rows.append({"mp_a": m1, "party_a": p1, "mp_b": m2, "party_b": p2, "joint_questions": cnt})
    rows.sort(key=lambda r: -r["joint_questions"])
    return rows


def main(proc: Path = PROC, site: Path = SITE) -> None:
    """Run all five analyses over ``proc`` CSVs; write kg_*.csv, graph.graphml and site/graph.json."""
    rows = load_all_rows(proc)
    party_topics = load_topics(proc)

    G, c = build_base_graph(rows)
    add_weighted_edges(G, c, party_topics)

    lift_rows = lift_table(c)
    signature_rows = [r for r in lift_rows if r["questions"] >= SIGNATURE_MIN_QUESTIONS]
    write_csv(
        proc / "kg_party_ministry_lift.csv",
        lift_rows,
        ["party", "ministry", "questions", "ministry_total", "party_total", "lift"],
    )

    pr_rows = pagerank_table(c, party_topics)
    write_csv(proc / "kg_pagerank.csv", pr_rows, ["node", "type", "label", "pagerank"])

    community_rows, parties, communities = party_communities(c, lift_rows)
    write_csv(proc / "kg_party_communities.csv", community_rows, ["community", "party", "questions", "community_size"])

    co_rows = ministry_cooccurrence(c)
    write_csv(proc / "kg_ministry_cooccurrence.csv", co_rows, ["ministry_a", "ministry_b", "shared_mps"])

    bridge_rows = cross_party_bridges(c)
    write_csv(proc / "kg_mp_coasking_bridges.csv", bridge_rows, ["mp_a", "party_a", "mp_b", "party_b", "joint_questions"])

    nx.write_graphml(G, proc / "graph.graphml")

    graph_payload = {
        "stats": {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "parties": len(parties),
            "ministries": len(c.ministry_total),
            "mps": len(c.mp_party),
            "cross_party_coasking_pairs": len(bridge_rows),
        },
        "signature_ministries": signature_rows[:60],
        "pagerank_top": pr_rows[:40],
        "party_communities": community_rows,
        "ministry_cooccurrence_top": co_rows[:40],
        "cross_party_bridges_top": bridge_rows[:30],
    }
    (site / "graph.json").write_text(json.dumps(graph_payload, indent=2))

    print("Graph nodes:", G.number_of_nodes(), "edges:", G.number_of_edges())
    print("Communities:", len(communities), [len(x) for x in communities])
    print("Top signature ministries (lift, min 15 q):")
    for r in signature_rows[:15]:
        print(" ", r["party"], "->", r["ministry"], "lift", r["lift"], "n=", r["questions"])
    print("Cross-party co-asking bridges:", len(bridge_rows))


if __name__ == "__main__":
    main()
