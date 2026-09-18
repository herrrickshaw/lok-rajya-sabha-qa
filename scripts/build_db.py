"""
Load the enriched PQ data, summaries, and knowledge-graph outputs into a
single DuckDB file, and render per-party markdown briefs plus an overall
analysis summary.

Run after build.py and build_graph.py.
"""
import csv
import re
from pathlib import Path
from collections import defaultdict

import duckdb

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
DB_PATH = ROOT / "data" / "pq_ledger.duckdb"
DOCS = ROOT / "docs"
PARTY_DOCS = DOCS / "parties"
DOCS.mkdir(exist_ok=True)
PARTY_DOCS.mkdir(exist_ok=True)


def read_csv(name):
    with open(PROC / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_table(con, name, csv_name):
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.execute(
        f"CREATE TABLE {name} AS SELECT * FROM read_csv_auto(?, header=true, sample_size=-1)",
        [str(PROC / csv_name)],
    )


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))

    load_table(con, "ls_questions", "ls_questions_enriched.csv")
    load_table(con, "rs_questions", "rs_questions_enriched.csv")
    load_table(con, "party_summary", "party_summary.csv")
    load_table(con, "ministry_summary", "ministry_summary.csv")
    load_table(con, "state_summary", "state_summary.csv")
    load_table(con, "party_ministry_matrix_wide", "party_ministry_matrix.csv")
    load_table(con, "party_type_matrix_wide", "party_type_matrix.csv")
    load_table(con, "state_party_matrix_wide", "state_party_matrix.csv")
    load_table(con, "state_ministry_matrix_wide", "state_ministry_matrix.csv")
    load_table(con, "topic_keywords", "topic_keywords.csv")
    load_table(con, "unmatched_members", "unmatched_members.csv")
    load_table(con, "kg_party_ministry_lift", "kg_party_ministry_lift.csv")
    load_table(con, "kg_pagerank", "kg_pagerank.csv")
    load_table(con, "kg_party_communities", "kg_party_communities.csv")
    load_table(con, "kg_ministry_cooccurrence", "kg_ministry_cooccurrence.csv")
    load_table(con, "kg_mp_coasking_bridges", "kg_mp_coasking_bridges.csv")

    # A single tidy view across both chambers -- the "queries and answers" table.
    con.execute(
        """
        CREATE OR REPLACE VIEW all_questions AS
        SELECT chamber, ques_no, session_no, date, type, ministry, subject, member,
               all_members, party, party_full, state, question_text, answer_text, answer_pdf_url
        FROM ls_questions
        UNION ALL
        SELECT chamber, ques_no, session_no, date, type, ministry, subject, member,
               all_members, party, party_full, state, question_text, answer_text, answer_pdf_url
        FROM rs_questions
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW party_ranking AS
        SELECT party, lok_sabha_questions, rajya_sabha_questions, total_questions,
               RANK() OVER (ORDER BY total_questions DESC) AS rank
        FROM party_summary
        ORDER BY rank
        """
    )

    n_all = con.execute("SELECT COUNT(*) FROM all_questions").fetchone()[0]
    n_with_text = con.execute("SELECT COUNT(*) FROM all_questions WHERE question_text IS NOT NULL").fetchone()[0]
    print(f"all_questions: {n_all} rows, {n_with_text} with full question text (Rajya Sabha only)")

    tables = con.execute("SHOW TABLES").fetchall()
    print("Tables/views:", [t[0] for t in tables])

    con.close()
    print("Wrote", DB_PATH)

    build_markdown(con=None)


def build_markdown(con):
    party_summary = {r["party"]: r for r in read_csv("party_summary.csv")}
    lift_rows = read_csv("kg_party_ministry_lift.csv")
    communities = read_csv("kg_party_communities.csv")
    topic_rows = read_csv("topic_keywords.csv")
    type_matrix = read_csv("party_type_matrix.csv")
    bridges = read_csv("kg_mp_coasking_bridges.csv")
    pagerank = read_csv("kg_pagerank.csv")
    ministry_summary = read_csv("ministry_summary.csv")
    state_summary = read_csv("state_summary.csv")

    community_by_party = {r["party"]: r["community"] for r in communities}
    lift_by_party = defaultdict(list)
    for r in lift_rows:
        lift_by_party[r["party"]].append(r)
    topics_by_party = defaultdict(list)
    for r in topic_rows:
        if r["party"] != "ALL":
            topics_by_party[r["party"]].append(r)
    type_by_party = {r["party"]: r for r in type_matrix}

    def slugify(name):
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "party"

    # ---- Per-party briefs (parties with >= 50 questions -- keeps it to the
    # ones with enough volume for a stable profile, ~30 parties) ----
    briefed = []
    for party, s in sorted(party_summary.items(), key=lambda kv: -int(kv[1]["total_questions"])):
        total = int(s["total_questions"])
        if total < 50 or party == "Unknown":
            continue
        briefed.append(party)
        slug = slugify(party)
        signature = sorted(
            [r for r in lift_by_party.get(party, []) if int(r["questions"]) >= 10],
            key=lambda r: -float(r["lift"]),
        )[:8]
        topics = sorted(topics_by_party.get(party, []), key=lambda r: -int(r["count"]))[:12]
        t = type_by_party.get(party, {})
        starred = int(t.get("STARRED", 0) or 0)
        unstarred = int(t.get("UNSTARRED", 0) or 0)
        starred_share = (100 * starred / (starred + unstarred)) if (starred + unstarred) else 0
        comm = community_by_party.get(party)

        lines = [
            f"# {party}",
            "",
            f"**Total Parliament Questions:** {total:,}  ",
            f"**Lok Sabha:** {int(s['lok_sabha_questions']):,} · **Rajya Sabha:** {int(s['rajya_sabha_questions']):,}",
            "",
        ]
        if comm is not None:
            lines += [f"**Knowledge-graph community:** {int(comm)+1} (see `docs/ANALYSIS.md` for what the communities mean)", ""]
        if starred + unstarred >= 10:
            lines += [
                f"**Starred vs. unstarred:** {starred:,} starred / {unstarred:,} unstarred ({starred_share:.1f}% starred — "
                "starred questions get an oral answer and floor follow-up; each MP may ask only one per sitting day).",
                "",
            ]
        if signature:
            lines += ["## Signature ministries", "", "Ministries this party asks about disproportionately more than its overall share of questions predicts:", ""]
            lines += ["| Ministry | Questions | Lift |", "|---|---:|---:|"]
            for r in signature:
                lines.append(f"| {r['ministry']} | {r['questions']} | {float(r['lift']):.2f}x |")
            lines.append("")
        if topics:
            lines += ["## Recurring subject-line topics", "", ", ".join(f"{r['term']} ({r['count']})" for r in topics), ""]
        (PARTY_DOCS / f"{slug}.md").write_text("\n".join(lines))

    # ---- Overall analysis ----
    top_parties = sorted(party_summary.values(), key=lambda r: -int(r["total_questions"]))[:15]
    top_ministries = sorted(ministry_summary, key=lambda r: -int(r["questions"]))[:15]
    top_states = sorted(state_summary, key=lambda r: -int(r["questions"]))[:15]
    top_pagerank_ministries = [r for r in pagerank if r["type"] == "ministry"][:10]
    top_bridges = sorted(bridges, key=lambda r: -int(r["joint_questions"]))[:10]

    by_comm = defaultdict(list)
    for r in communities:
        by_comm[int(r["community"])].append(r["party"])

    lines = [
        "# Parliament Questions, 18th Lok Sabha term — analysis",
        "",
        "Source data: `sansad.in` (`api_ls`) for Lok Sabha, `rsdoc.nic.in` for Rajya Sabha (sessions 265-271, "
        "the sessions covering the same period as the 18th Lok Sabha), both chambers' member rosters for "
        "party/state attribution. Full methodology in the repository README.",
        "",
        "## What a Parliament Question actually is",
        "",
        "Per Rules 32-54 of the Lok Sabha's Rules of Procedure (Rules 47-50 in the Rajya Sabha), an MP files a "
        "notice — max 150 words, no policy-level or sub-judice matters, no more than 5 notices a day — at least "
        "15 days ahead (10 for a short-notice question). The Speaker/Chairman rules on admissibility. A "
        "**starred** question gets an oral answer and allows follow-up supplementaries on the floor, capped at "
        "one per MP per sitting day; an **unstarred** question gets only a written reply tabled on the record. "
        "(Source: Drishti IAS, \"Questioning in Parliament\", drishtiias.com — a standard UPSC-prep civics "
        "reference, used here only to confirm procedural definitions against a reliable secondary source, not "
        "as a data source.)",
        "",
        "## Top parties by total questions",
        "",
        "| Rank | Party | Lok Sabha | Rajya Sabha | Total |",
        "|---:|---|---:|---:|---:|",
    ]
    for i, p in enumerate(top_parties, 1):
        lines.append(f"| {i} | {p['party']} | {int(p['lok_sabha_questions']):,} | {int(p['rajya_sabha_questions']):,} | {int(p['total_questions']):,} |")

    lines += ["", "## Top ministries by questions received", "", "| Ministry | Questions |", "|---|---:|"]
    for m in top_ministries:
        lines.append(f"| {m['ministry']} | {int(m['questions']):,} |")

    lines += ["", "## Top states by their MPs' question volume", "", "| State/UT | Questions |", "|---|---:|"]
    for s in top_states:
        lines.append(f"| {s['state']} | {int(s['questions']):,} |")

    lines += [
        "",
        "## Knowledge-graph findings",
        "",
        "The flat rankings above answer \"who asks the most\" and \"about what, in aggregate\". Building a "
        "heterogeneous graph (MP / Party / Ministry / Topic nodes, weighted question-count edges) and running "
        "standard graph analyses on it answers three questions the pivot tables can't:",
        "",
        "**1. Which ministries are a party's genuine signature** — not just its biggest by raw count, but where "
        "it asks disproportionately more than its overall share of questions would predict (\"lift\"). See each "
        "party's brief in `docs/parties/` for its own list, or `data/processed/kg_party_ministry_lift.csv` for "
        "all of them.",
        "",
        "**2. Which parties cluster together by what they ask about**, independent of size or stated ideology — "
        "Louvain community detection on party-ministry lift vectors (not raw counts, which are swamped by every "
        "party's shared interest in Health/Railways/Education) finds:",
        "",
    ]
    community_notes = {
        0: "a left- and minority-interest bloc",
        1: "a broad mainstream bloc containing both the ruling party and the principal opposition",
        2: "a smaller regional-development cluster",
        3: "outlier(s) whose profile doesn't resemble any cluster closely enough",
    }
    for c in sorted(by_comm):
        parties = by_comm[c]
        note = community_notes.get(c, "")
        lines.append(f"- **Community {c+1}** ({len(parties)} parties, {note}): {', '.join(sorted(parties))}")

    lines += [
        "",
        "**3. Where MPs cross party lines** — Lok Sabha questions are occasionally tabled jointly by several "
        "MPs; a handful of those pairings cross party lines. Top cross-party co-asking pairs:",
        "",
        "| MP | Party | MP | Party | Joint questions |",
        "|---|---|---|---|---:|",
    ]
    for b in top_bridges:
        lines.append(f"| {b['mp_a']} | {b['party_a']} | {b['mp_b']} | {b['party_b']} | {b['joint_questions']} |")

    lines += [
        "",
        "## Known gaps",
        "",
        "- **Lok Sabha question/answer full text is not in this dataset.** The `api_ls` listing endpoint used to "
        "fetch all 34,720 LS questions only exposes the subject line, not the question or answer body — those "
        "live only in per-question PDFs (a different URL per question, with a random filename suffix on the "
        "18th LS). Fetching and OCR'ing ~34,700 PDFs was out of scope for this pass; `docs/parties/*.md` and "
        "the topic tab work from subject-line text only for the Lok Sabha side.",
        "- **Rajya Sabha has full question text** (`question_text` in `rs_questions` / `all_questions`) but "
        "**not answer text** — `rsdoc.nic.in` returns `ans_text: null` for every record; answers are PDF-only "
        "there too (`answer_pdf_url`).",
        f"- {138} of 34,720 Lok Sabha questions (0.4%) could not be matched to a roster member by name (honorific "
        "variants and, in a couple of cases, MPs who left office without a public former-member record) and are "
        "excluded from party/state breakdowns.",
        "- Party attribution for a jointly-tabled Lok Sabha question uses the first-listed (lead) member only, "
        "to avoid one question inflating multiple parties' counts.",
        "",
    ]
    (DOCS / "ANALYSIS.md").write_text("\n".join(lines))
    print(f"Wrote docs/ANALYSIS.md and {len(briefed)} party briefs in docs/parties/")


if __name__ == "__main__":
    main()
