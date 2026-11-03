"""
Build party-wise / ministry-wise rankings of Parliament Questions (PQs)
for the 18th Lok Sabha (since June 2024) and the corresponding Rajya
Sabha sessions (265-271), from the undocumented sansad.in / rsdoc.nic.in
JSON APIs.

Inputs (fetched separately, see scripts/fetch_*.py notes in README):
  data/raw/ls_questions.json     - list of {quesNo, subjects, lokNo, member, ministry, type, date, sessionNo}
  data/raw/ls_members.json       - LS-18 sitting members (name variants + party)
  data/raw/rs_questions_raw.json - RS PQ records with mp_code, min_name, ses_no, etc.
  data/raw/rs_members.json       - RS sitting members (mpsno, party, partyCode)
  data/raw/rs_members_former.json- RS members who exited mid-term (covers retired MPs)

Outputs:
  data/processed/ls_questions_enriched.csv
  data/processed/rs_questions_enriched.csv
  data/processed/party_summary.csv
  data/processed/party_ministry_matrix.csv
  data/processed/unmatched_ls_members.csv   (caveat list)
  site/data.json                            (feeds the HTML artifact)
  Lok_Rajya_Sabha_PQ_Analysis.xlsx
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from csv_io import write_csv  # noqa: E402
from pq_text import (  # noqa: E402,F401  (re-exported: other code imported these from build)
    HONORIFICS, MINISTRY_ALIASES, PARTY_ALIASES, STATE_ALIASES,
    canonical_ministry, canonical_party, canonical_state, fuzzy_match,
    normalize_name, strip_html,
)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
SITE = ROOT / "site"

Row = Dict[str, object]

ENRICHED_FIELDS = [
    "chamber", "ques_no", "session_no", "date", "type", "ministry",
    "subject", "member", "all_members", "party", "party_full", "state",
    "question_text", "answer_text", "answer_pdf_url",
]

STOPWORDS = set(
    "the a an of in on for to and or is are was were be been being with "
    "by at as from this that these those it its their his her our your "
    "under regarding about state government india national scheme "
    "schemes details status number year years since current"
    .split()
)
BIGRAM_MIN_COUNT = 3  # a bigram must occur this often to be kept as a topic term
OVERALL_TOPIC_COUNT = 30
PARTY_TOPIC_COUNT = 12
SITE_TOP_MINISTRIES = 25
SITE_TOP_STATES = 40

SITE_NOTE = (
    "18th Lok Sabha PQs since formation (Jun 2024); Rajya Sabha sessions 265-271 (same period). "
    "Source: sansad.in / rsdoc.nic.in public APIs, member rosters cross-referenced for party and state."
)


# ---- Loading (I/O) ---------------------------------------------------------


def load_ls_member_index(raw: Path = RAW) -> Tuple[Dict[str, dict], Dict[str, list]]:
    """Index the LS roster by normalised name (plus a word index for fuzzy fallback)."""
    members = json.loads((raw / "ls_members.json").read_text())
    return index_ls_members(members)


def index_ls_members(members: Iterable[dict]) -> Tuple[Dict[str, dict], Dict[str, list]]:
    """Pure part of ``load_ls_member_index``: roster dicts in, (name index, word index) out."""
    index: Dict[str, dict] = {}
    word_index: Dict[str, list] = defaultdict(list)  # word -> normalized-name keys
    for m in members:
        party = canonical_party(m.get("partySname") or m.get("partyFname") or "Unknown")
        record = {
            "party": party,
            "party_full": m.get("partyFname"),
            "state": canonical_state(m.get("stateName")),
            "constituency": m.get("constName"),
            "canonical_name": m.get("mpFirstLastName"),
        }
        for key in (m.get("mpFirstLastName"), m.get("mpLastFirstName")):
            if not key:
                continue
            norm = normalize_name(key)
            index[norm] = record
            for w in set(norm.split()):
                if len(w) > 2:
                    word_index[w].append(norm)
    return index, word_index


def load_rs_member_index(raw: Path = RAW) -> Dict[object, dict]:
    """Index current + former RS members by ``mpsno``."""
    index: Dict[object, dict] = {}
    for fname in ("rs_members.json", "rs_members_former.json"):
        p = raw / fname
        if not p.exists():
            continue
        for m in json.loads(p.read_text()):
            index[m["mpsno"]] = {
                "party": canonical_party(m.get("partyCode") or "Unknown"),
                "party_full": m.get("party"),
                "state": canonical_state(m.get("state")),
                "canonical_name": (m.get("name") or "").strip(),
            }
    return index


# ---- Enrichment (pure) -----------------------------------------------------


def enrich_ls(raw: Iterable[dict], ls_index: dict, ls_word_index: dict) -> Tuple[List[Row], Counter]:
    """Turn raw LS question records into enriched rows; count unmatched lead members."""
    rows: List[Row] = []
    unmatched: Counter = Counter()
    for q in raw:
        members = q.get("member") or []
        primary = members[0] if members else None
        party, party_full, state = "Unknown", None, "Unknown"
        if primary:
            norm = normalize_name(primary)
            hit = ls_index.get(norm) or fuzzy_match(primary, ls_index, ls_word_index)
            if hit:
                party, party_full = hit["party"], hit["party_full"]
                state = hit.get("state") or "Unknown"
            else:
                unmatched[primary] += 1
        rows.append(
            {
                "chamber": "Lok Sabha",
                "ques_no": q.get("quesNo"),
                "session_no": q.get("sessionNo"),
                "date": q.get("date"),
                "type": q.get("type"),
                "ministry": canonical_ministry(q.get("ministry")),
                "subject": (q.get("subjects") or "").strip(),
                "member": primary,
                "all_members": "; ".join(members),
                "party": party,
                "party_full": party_full,
                "state": (state or "Unknown").strip() or "Unknown",
                "question_text": None,  # sansad.in's LS listing API doesn't expose full text, only the PDF
                "answer_text": None,
                "answer_pdf_url": None,
            }
        )
    return rows, unmatched


def enrich_rs(raw: Iterable[dict], rs_index: dict) -> Tuple[List[Row], Counter]:
    """Turn raw RS question records into enriched rows; count unmatched MP codes by name."""
    rows: List[Row] = []
    unmatched: Counter = Counter()
    for q in raw:
        mp_code = q.get("mp_code")
        hit = rs_index.get(mp_code)
        if hit:
            party, party_full, state = hit["party"], hit["party_full"], hit.get("state") or "Unknown"
        else:
            party, party_full, state = "Unknown", None, "Unknown"
            unmatched[q.get("name")] += 1
        rows.append(
            {
                "chamber": "Rajya Sabha",
                "ques_no": q.get("qno"),
                "session_no": q.get("ses_no"),
                "date": q.get("ans_date"),
                "type": (q.get("qtype") or "").strip(),
                "ministry": canonical_ministry(q.get("min_name")),
                "subject": (q.get("qtitle") or "").strip(),
                "member": (q.get("name") or "").strip(),
                "all_members": (q.get("name") or "").strip(),
                "party": party,
                "party_full": party_full,
                "state": (state or "Unknown").strip() or "Unknown",
                "question_text": strip_html(q.get("qn_text")),
                "answer_text": strip_html(q.get("ans_text")),  # rsdoc doesn't populate this inline either; always None as of this run
                "answer_pdf_url": q.get("files"),
            }
        )
    return rows, unmatched


def build_ls(ls_index: dict, ls_word_index: dict, raw: Path = RAW) -> Tuple[List[Row], Counter]:
    """Read ``ls_questions.json`` from ``raw`` and enrich it."""
    return enrich_ls(json.loads((raw / "ls_questions.json").read_text()), ls_index, ls_word_index)


def build_rs(rs_index: dict, raw: Path = RAW) -> Tuple[List[Row], Counter]:
    """Read ``rs_questions_raw.json`` from ``raw`` and enrich it."""
    return enrich_rs(json.loads((raw / "rs_questions_raw.json").read_text()), rs_index)


# ---- Aggregation (pure) ----------------------------------------------------


def party_summary(all_rows: Sequence[Row]) -> List[Row]:
    """Per-party question counts for each chamber, biggest first."""
    totals: Dict[object, Dict[str, int]] = defaultdict(lambda: {"Lok Sabha": 0, "Rajya Sabha": 0})
    for r in all_rows:
        totals[r["party"]][r["chamber"]] += 1
    out: List[Row] = []
    for party, counts in sorted(totals.items(), key=lambda kv: -(kv[1]["Lok Sabha"] + kv[1]["Rajya Sabha"])):
        out.append(
            {
                "party": party,
                "lok_sabha_questions": counts["Lok Sabha"],
                "rajya_sabha_questions": counts["Rajya Sabha"],
                "total_questions": counts["Lok Sabha"] + counts["Rajya Sabha"],
            }
        )
    return out


def cross_tab(
    all_rows: Sequence[Row],
    label: str,
    row_key: Callable[[Row], object],
    col_key: Callable[[Row], object],
    columns: Optional[Sequence[object]] = None,
) -> Tuple[List[Row], List[object]]:
    """Count rows into a wide matrix: one dict per row key, one column per col key.

    Row order is first-seen; columns are sorted unless ``columns`` is given.
    """
    counts: Dict[object, Counter] = defaultdict(Counter)
    seen_cols = set()
    for r in all_rows:
        c = col_key(r)
        counts[row_key(r)][c] += 1
        seen_cols.add(c)
    cols = list(columns) if columns is not None else sorted(seen_cols)
    rows: List[Row] = []
    for key in counts:
        row: Row = {label: key}
        for c in cols:
            row[c] = counts[key].get(c, 0)
        rows.append(row)
    return rows, cols


def _type_of(r: Row) -> str:
    return (r["type"] or "UNKNOWN").strip().upper() or "UNKNOWN"  # type: ignore[union-attr]


def tokenize(text: Optional[str]) -> List[str]:
    """Lower-case alphabetic tokens (3+ letters) of ``text`` minus STOPWORDS."""
    words = re.findall(r"[a-zA-Z]{3,}", (text or "").lower())
    return [w for w in words if w not in STOPWORDS]


def top_terms(rows_subset: Iterable[Row], n: int = 20) -> List[Tuple[str, int]]:
    """Most frequent subject-line bigrams (>= BIGRAM_MIN_COUNT) plus unigrams not inside a kept bigram."""
    uni: Counter = Counter()
    bi: Counter = Counter()
    for r in rows_subset:
        toks = tokenize(r["subject"])  # type: ignore[arg-type]
        uni.update(toks)
        bi.update(" ".join(pair) for pair in zip(toks, toks[1:]))
    combined: Counter = Counter()
    combined.update({k: v for k, v in bi.items() if v >= BIGRAM_MIN_COUNT})
    for k, v in uni.items():
        if k not in " ".join(combined.keys()):
            combined[k] = v
    return combined.most_common(n)


def _ordered_party_totals(all_rows: Sequence[Row]) -> List[object]:
    """Parties in first-seen order (the iteration order the original dict gave)."""
    return list(dict.fromkeys(r["party"] for r in all_rows))


def topic_rows(all_rows: Sequence[Row]) -> Tuple[List[Row], List[Tuple[str, int]], Dict[object, List[Tuple[str, int]]]]:
    """CSV rows for topic_keywords.csv plus the overall and per-party term lists."""
    overall = top_terms(all_rows, OVERALL_TOPIC_COUNT)
    rows: List[Row] = [{"party": "ALL", "term": t, "count": c} for t, c in overall]
    by_party: Dict[object, List[Tuple[str, int]]] = {}
    for party in _ordered_party_totals(all_rows):
        terms = top_terms([r for r in all_rows if r["party"] == party], PARTY_TOPIC_COUNT)
        by_party[party] = terms
        rows += [{"party": party, "term": t, "count": c} for t, c in terms]
    return rows, overall, by_party


def _weight(row: Row, label: str) -> int:
    return sum(v for k, v in row.items() if k != label)  # type: ignore[misc]


def site_payload(
    *,
    ls_rows: Sequence[Row],
    rs_rows: Sequence[Row],
    ls_unmatched: Counter,
    rs_unmatched: Counter,
    party_rows: List[Row],
    ministry_totals: Counter,
    state_totals: Counter,
    pm_rows: List[Row],
    sp_rows: List[Row],
    sm_rows: List[Row],
    pt_rows: List[Row],
    parties_for_state: List[object],
    types: List[object],
    overall_topics: List[Tuple[str, int]],
    by_party_topics: Dict[object, List[Tuple[str, int]]],
) -> dict:
    """Assemble the dict serialised to ``site/data.json``."""
    top_ministries = [m for m, _ in ministry_totals.most_common(SITE_TOP_MINISTRIES)]
    top_states = [s for s, _ in state_totals.most_common(SITE_TOP_STATES)]
    return {
        "generated_note": SITE_NOTE,
        "party_summary": party_rows,
        "ministry_summary": [{"ministry": m, "questions": c} for m, c in ministry_totals.most_common()],
        "state_summary": [{"state": s, "questions": c} for s, c in state_totals.most_common()],
        "party_ministry_matrix": {
            "ministries": top_ministries,
            "rows": [
                {"party": row["party"], "values": [row.get(m, 0) for m in top_ministries]}
                for row in sorted(pm_rows, key=lambda r: -_weight(r, "party"))
            ],
        },
        "state_party_matrix": {
            "parties": parties_for_state,
            "rows": [
                {"state": row["state"], "values": [row.get(p, 0) for p in parties_for_state]}
                for row in sorted(sp_rows, key=lambda r: -_weight(r, "state"))
                if row["state"] in top_states
            ],
        },
        "state_ministry_matrix": {
            "ministries": top_ministries,
            "rows": [
                {"state": row["state"], "values": [row.get(m, 0) for m in top_ministries]}
                for row in sorted(sm_rows, key=lambda r: -_weight(r, "state"))
                if row["state"] in top_states
            ],
        },
        "party_type_matrix": {
            "types": types,
            "rows": sorted(pt_rows, key=lambda r: -_weight(r, "party")),
        },
        "overall_topics": [{"term": t, "count": c} for t, c in overall_topics],
        "party_topics": {
            party: [{"term": t, "count": c} for t, c in terms]
            for party, terms in by_party_topics.items()
        },
        "totals": {
            "lok_sabha": len(ls_rows),
            "rajya_sabha": len(rs_rows),
            "combined": len(ls_rows) + len(rs_rows),
            "unmatched_ls": sum(ls_unmatched.values()),
            "unmatched_rs": sum(rs_unmatched.values()),
        },
    }


# ---- Orchestration (I/O at the edge) --------------------------------------


def main(raw: Path = RAW, out: Path = OUT, site: Path = SITE) -> None:
    """Read ``raw`` JSON, write enriched CSVs / summaries to ``out`` and ``site/data.json``."""
    out.mkdir(parents=True, exist_ok=True)
    site.mkdir(parents=True, exist_ok=True)

    ls_index, ls_word_index = load_ls_member_index(raw)
    rs_index = load_rs_member_index(raw)

    ls_rows, ls_unmatched = build_ls(ls_index, ls_word_index, raw)
    rs_rows, rs_unmatched = build_rs(rs_index, raw)

    write_csv(out / "ls_questions_enriched.csv", ls_rows, ENRICHED_FIELDS)
    write_csv(out / "rs_questions_enriched.csv", rs_rows, ENRICHED_FIELDS)

    all_rows = ls_rows + rs_rows

    party_rows = party_summary(all_rows)
    write_csv(
        out / "party_summary.csv",
        party_rows,
        ["party", "lok_sabha_questions", "rajya_sabha_questions", "total_questions"],
    )

    # Party x Ministry matrix (combined)
    pm_rows, ministries = cross_tab(all_rows, "party", lambda r: r["party"], lambda r: r["ministry"])
    write_csv(out / "party_ministry_matrix.csv", pm_rows, ["party"] + ministries)

    ministry_totals = Counter(r["ministry"] for r in all_rows)
    write_csv(
        out / "ministry_summary.csv",
        [{"ministry": m, "questions": c} for m, c in ministry_totals.most_common()],
        ["ministry", "questions"],
    )

    # State summary -- which states' MPs raise the most questions
    state_totals = Counter((r["state"] or "Unknown") for r in all_rows)
    write_csv(
        out / "state_summary.csv",
        [{"state": s, "questions": c} for s, c in state_totals.most_common()],
        ["state", "questions"],
    )

    def state_of(r: Row) -> object:
        return r["state"] or "Unknown"

    sp_rows, parties_for_state = cross_tab(all_rows, "state", state_of, lambda r: r["party"])
    write_csv(out / "state_party_matrix.csv", sp_rows, ["state"] + parties_for_state)

    # State x Ministry -- same column set as the party x ministry matrix
    sm_rows, _ = cross_tab(all_rows, "state", state_of, lambda r: r["ministry"], columns=ministries)
    write_csv(out / "state_ministry_matrix.csv", sm_rows, ["state"] + ministries)

    # Party x type (STARRED/UNSTARRED) breakdown -- "kinds of queries"
    pt_rows, types = cross_tab(all_rows, "party", lambda r: r["party"], _type_of)
    write_csv(out / "party_type_matrix.csv", pt_rows, ["party"] + types)

    # Topic keywords (finer-grained than ministry)
    t_rows, overall_topics, by_party_topics = topic_rows(all_rows)
    write_csv(out / "topic_keywords.csv", t_rows, ["party", "term", "count"])

    unmatched_rows = [{"chamber": "Lok Sabha", "name": n, "count": c} for n, c in ls_unmatched.most_common()]
    unmatched_rows += [{"chamber": "Rajya Sabha", "name": n, "count": c} for n, c in rs_unmatched.most_common()]
    write_csv(out / "unmatched_members.csv", unmatched_rows, ["chamber", "name", "count"])

    payload = site_payload(
        ls_rows=ls_rows, rs_rows=rs_rows, ls_unmatched=ls_unmatched, rs_unmatched=rs_unmatched,
        party_rows=party_rows, ministry_totals=ministry_totals, state_totals=state_totals,
        pm_rows=pm_rows, sp_rows=sp_rows, sm_rows=sm_rows, pt_rows=pt_rows,
        parties_for_state=parties_for_state, types=types,
        overall_topics=overall_topics, by_party_topics=by_party_topics,
    )
    (site / "data.json").write_text(json.dumps(payload, indent=2))

    print("LS rows:", len(ls_rows), "unmatched:", sum(ls_unmatched.values()))
    print("RS rows:", len(rs_rows), "unmatched:", sum(rs_unmatched.values()))
    print("Parties:", len(party_rows))
    print("Ministries:", len(ministries))
    print("States:", len(state_totals))
    print("Top 10 parties:", party_rows[:10])
    print("Top 10 states:", state_totals.most_common(10))
    print("Top 10 ministries:", ministry_totals.most_common(10))


if __name__ == "__main__":
    main()
