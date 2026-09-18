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
import json
import re
import csv
from pathlib import Path
from collections import defaultdict, Counter

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT = Path(__file__).resolve().parent.parent / "data" / "processed"
SITE = Path(__file__).resolve().parent.parent / "site"
OUT.mkdir(parents=True, exist_ok=True)
SITE.mkdir(parents=True, exist_ok=True)

HONORIFICS = re.compile(
    r"^(dr\.?|shri|smt\.?|kumari|sushri|km\.?|prof\.?|adv\.?|er\.?|col\.?|capt\.?|major|maj\.?|"
    r"lt\.?|gen\.?|justice|mrs\.?|mr\.?|ms\.?|thiru|thirumathi|selvi|md\.?|mohd\.?|mohammad|"
    r"com\.?|sardar|pandit|maulana|rev\.?|er)\s+",
    re.IGNORECASE,
)


# The LS and RS rosters come from independently maintained sansad.in tables
# and use different abbreviation conventions for the same party. Without this
# map, e.g. Shiv Sena (UBT) splits into "SHSUBT" (LS) and "SS-UBT" (RS) and
# is undercounted in both chambers' rankings.
PARTY_ALIASES = {
    "SHSUBT": "SHS(UBT)",
    "SS-UBT": "SHS(UBT)",
    "YSR CONGRESS PARTY": "YSRCP",
    "NCPSP": "NCP(SP)",
    "NCP-SCP": "NCP(SP)",
    "IND.": "IND.",
    "IND": "IND.",
    "UPP(L)": "UPPL",
}


def canonical_party(name: str) -> str:
    if not name:
        return "Unknown"
    key = name.strip().upper()
    return PARTY_ALIASES.get(key, name.strip())


# Same cross-source naming drift as parties: RS uses the constitutional name
# "Keralam" where LS uses "Kerala", RS spells out "National Capital Territory
# of Delhi" where LS abbreviates "NCT of Delhi", etc.
STATE_ALIASES = {
    "KERALAM": "Kerala",
    "NATIONAL CAPITAL TERRITORY OF DELHI": "Delhi",
    "NCT OF DELHI": "Delhi",
    "JAMMU & KASHMIR": "Jammu and Kashmir",
}


def canonical_state(name: str) -> str:
    if not name:
        return "Unknown"
    collapsed = re.sub(r"\s+", " ", name.strip())
    return STATE_ALIASES.get(collapsed.upper(), collapsed) or "Unknown"


def canonical_ministry(name: str) -> str:
    """LS ('ministry') and RS ('min_name') fields differ in case/spacing for the
    same ministry (e.g. 'HOUSING AND URBAN AFFAIRS' vs 'Housing and Urban
    Affairs'), which would otherwise fragment ministry-level counts."""
    if not name:
        return "Unknown"
    collapsed = re.sub(r"\s+", " ", name.strip())
    return collapsed.upper() or "Unknown"


TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text):
    if not text:
        return None
    text = TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip() or None


def normalize_name(name: str) -> str:
    name = name.strip()
    prev = None
    while prev != name:
        prev = name
        name = HONORIFICS.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name.lower()


def load_ls_member_index():
    members = json.loads((RAW / "ls_members.json").read_text())
    index = {}
    word_index = defaultdict(list)  # word -> list of normalized-name keys, for fuzzy fallback
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


def fuzzy_match(name: str, index: dict, word_index: dict):
    """Fallback for honorific variants / middle-name mismatches: pick the roster
    entry whose word set has the highest Jaccard overlap with the PQ name's
    word set, requiring a strong majority overlap to avoid false positives."""
    norm = normalize_name(name)
    words = set(w for w in norm.split() if len(w) > 2)
    if not words:
        return None
    candidates = Counter()
    for w in words:
        for cand in word_index.get(w, ()):
            candidates[cand] += 1
    best, best_score = None, 0.0
    for cand, overlap in candidates.items():
        cand_words = set(cand.split())
        union = words | cand_words
        score = overlap / len(union) if union else 0
        if score > best_score:
            best, best_score = cand, score
    if best and best_score >= 0.5:
        return index[best]
    return None


def load_rs_member_index():
    index = {}
    for fname in ("rs_members.json", "rs_members_former.json"):
        p = RAW / fname
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


def build_ls(ls_index, ls_word_index):
    raw = json.loads((RAW / "ls_questions.json").read_text())
    rows = []
    unmatched = Counter()
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


def build_rs(rs_index):
    raw = json.loads((RAW / "rs_questions_raw.json").read_text())
    rows = []
    unmatched = Counter()
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


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    ls_index, ls_word_index = load_ls_member_index()
    rs_index = load_rs_member_index()

    ls_rows, ls_unmatched = build_ls(ls_index, ls_word_index)
    rs_rows, rs_unmatched = build_rs(rs_index)

    fieldnames = [
        "chamber", "ques_no", "session_no", "date", "type", "ministry",
        "subject", "member", "all_members", "party", "party_full", "state",
        "question_text", "answer_text", "answer_pdf_url",
    ]
    write_csv(OUT / "ls_questions_enriched.csv", ls_rows, fieldnames)
    write_csv(OUT / "rs_questions_enriched.csv", rs_rows, fieldnames)

    all_rows = ls_rows + rs_rows

    # Party summary (combined + per chamber)
    party_totals = defaultdict(lambda: {"Lok Sabha": 0, "Rajya Sabha": 0})
    for r in all_rows:
        party_totals[r["party"]][r["chamber"]] += 1

    party_summary_rows = []
    for party, counts in sorted(
        party_totals.items(), key=lambda kv: -(kv[1]["Lok Sabha"] + kv[1]["Rajya Sabha"])
    ):
        total = counts["Lok Sabha"] + counts["Rajya Sabha"]
        party_summary_rows.append(
            {
                "party": party,
                "lok_sabha_questions": counts["Lok Sabha"],
                "rajya_sabha_questions": counts["Rajya Sabha"],
                "total_questions": total,
            }
        )
    write_csv(
        OUT / "party_summary.csv",
        party_summary_rows,
        ["party", "lok_sabha_questions", "rajya_sabha_questions", "total_questions"],
    )

    # Party x Ministry matrix (combined)
    pm = defaultdict(Counter)
    ministries = set()
    for r in all_rows:
        pm[r["party"]][r["ministry"]] += 1
        ministries.add(r["ministry"])
    ministries = sorted(ministries)
    pm_rows = []
    for party in pm:
        row = {"party": party}
        for m in ministries:
            row[m] = pm[party].get(m, 0)
        pm_rows.append(row)
    write_csv(OUT / "party_ministry_matrix.csv", pm_rows, ["party"] + ministries)

    # Ministry summary (combined)
    ministry_totals = Counter(r["ministry"] for r in all_rows)
    write_csv(
        OUT / "ministry_summary.csv",
        [{"ministry": m, "questions": c} for m, c in ministry_totals.most_common()],
        ["ministry", "questions"],
    )

    # State summary (combined) -- which states' MPs raise the most questions
    state_totals = Counter((r["state"] or "Unknown") for r in all_rows)
    write_csv(
        OUT / "state_summary.csv",
        [{"state": s, "questions": c} for s, c in state_totals.most_common()],
        ["state", "questions"],
    )

    # State x Party matrix (combined)
    sp = defaultdict(Counter)
    parties_for_state = set()
    for r in all_rows:
        sp[r["state"] or "Unknown"][r["party"]] += 1
        parties_for_state.add(r["party"])
    parties_for_state = sorted(parties_for_state)
    sp_rows = []
    for state in sp:
        row = {"state": state}
        for p in parties_for_state:
            row[p] = sp[state].get(p, 0)
        sp_rows.append(row)
    write_csv(OUT / "state_party_matrix.csv", sp_rows, ["state"] + parties_for_state)

    # State x Ministry matrix (combined) -- which states' MPs focus on which topics
    sm = defaultdict(Counter)
    for r in all_rows:
        sm[r["state"] or "Unknown"][r["ministry"]] += 1
    sm_rows = []
    for state in sm:
        row = {"state": state}
        for m in ministries:
            row[m] = sm[state].get(m, 0)
        sm_rows.append(row)
    write_csv(OUT / "state_ministry_matrix.csv", sm_rows, ["state"] + ministries)

    # Party x type (STARRED/UNSTARRED) breakdown -- "kinds of queries"
    pt = defaultdict(Counter)
    types = set()
    for r in all_rows:
        t = (r["type"] or "UNKNOWN").strip().upper() or "UNKNOWN"
        pt[r["party"]][t] += 1
        types.add(t)
    types = sorted(types)
    pt_rows = []
    for party in pt:
        row = {"party": party}
        for t in types:
            row[t] = pt[party].get(t, 0)
        pt_rows.append(row)
    write_csv(OUT / "party_type_matrix.csv", pt_rows, ["party"] + types)

    # Topic keywords (finer-grained than ministry): word/bigram frequency in
    # question subjects, overall and per party -- a lightweight topic cut on
    # top of the ministry-level grouping.
    STOPWORDS = set(
        "the a an of in on for to and or is are was were be been being with "
        "by at as from this that these those it its their his her our your "
        "under regarding about state government india national scheme "
        "schemes details status number year years since current"
        .split()
    )

    def tokenize(text):
        words = re.findall(r"[a-zA-Z]{3,}", (text or "").lower())
        return [w for w in words if w not in STOPWORDS]

    def top_terms(rows_subset, n=20):
        uni = Counter()
        bi = Counter()
        for r in rows_subset:
            toks = tokenize(r["subject"])
            uni.update(toks)
            bi.update(" ".join(pair) for pair in zip(toks, toks[1:]))
        combined = Counter()
        combined.update({k: v for k, v in bi.items() if v >= 3})
        for k, v in uni.items():
            if k not in " ".join(combined.keys()):
                combined[k] = v
        return combined.most_common(n)

    overall_topics = top_terms(all_rows, 30)
    topic_rows = [{"party": "ALL", "term": t, "count": c} for t, c in overall_topics]
    by_party_topics = {}
    for party in party_totals:
        subset = [r for r in all_rows if r["party"] == party]
        terms = top_terms(subset, 12)
        by_party_topics[party] = terms
        topic_rows += [{"party": party, "term": t, "count": c} for t, c in terms]
    write_csv(OUT / "topic_keywords.csv", topic_rows, ["party", "term", "count"])

    # Unmatched name caveats
    unmatched_rows = [{"chamber": "Lok Sabha", "name": n, "count": c} for n, c in ls_unmatched.most_common()]
    unmatched_rows += [{"chamber": "Rajya Sabha", "name": n, "count": c} for n, c in rs_unmatched.most_common()]
    write_csv(OUT / "unmatched_members.csv", unmatched_rows, ["chamber", "name", "count"])

    # JSON for the artifact
    top_ministries = [m for m, _ in ministry_totals.most_common(25)]
    top_states = [s for s, _ in state_totals.most_common(40)]
    site_data = {
        "generated_note": "18th Lok Sabha PQs since formation (Jun 2024); Rajya Sabha sessions 265-271 (same period). Source: sansad.in / rsdoc.nic.in public APIs, member rosters cross-referenced for party and state.",
        "party_summary": party_summary_rows,
        "ministry_summary": [{"ministry": m, "questions": c} for m, c in ministry_totals.most_common()],
        "state_summary": [{"state": s, "questions": c} for s, c in state_totals.most_common()],
        "party_ministry_matrix": {
            "ministries": top_ministries,
            "rows": [
                {"party": row["party"], "values": [row.get(m, 0) for m in top_ministries]}
                for row in sorted(pm_rows, key=lambda r: -sum(v for k, v in r.items() if k != "party"))
            ],
        },
        "state_party_matrix": {
            "parties": parties_for_state,
            "rows": [
                {"state": row["state"], "values": [row.get(p, 0) for p in parties_for_state]}
                for row in sorted(sp_rows, key=lambda r: -sum(v for k, v in r.items() if k != "state"))
                if row["state"] in top_states
            ],
        },
        "state_ministry_matrix": {
            "ministries": top_ministries,
            "rows": [
                {"state": row["state"], "values": [row.get(m, 0) for m in top_ministries]}
                for row in sorted(sm_rows, key=lambda r: -sum(v for k, v in r.items() if k != "state"))
                if row["state"] in top_states
            ],
        },
        "party_type_matrix": {
            "types": types,
            "rows": sorted(pt_rows, key=lambda r: -sum(v for k, v in r.items() if k != "party")),
        },
        "overall_topics": [{"term": t, "count": c} for t, c in overall_topics],
        "party_topics": {
            party: [{"term": t, "count": c} for t, c in terms]
            for party, terms in by_party_topics.items()
        },
        "totals": {
            "lok_sabha": len(ls_rows),
            "rajya_sabha": len(rs_rows),
            "combined": len(all_rows),
            "unmatched_ls": sum(ls_unmatched.values()),
            "unmatched_rs": sum(rs_unmatched.values()),
        },
    }
    (SITE / "data.json").write_text(json.dumps(site_data, indent=2))

    print("LS rows:", len(ls_rows), "unmatched:", sum(ls_unmatched.values()))
    print("RS rows:", len(rs_rows), "unmatched:", sum(rs_unmatched.values()))
    print("Parties:", len(party_summary_rows))
    print("Ministries:", len(ministries))
    print("States:", len(state_totals))
    print("Top 10 parties:", party_summary_rows[:10])
    print("Top 10 states:", state_totals.most_common(10))
    print("Top 10 ministries:", ministry_totals.most_common(10))


if __name__ == "__main__":
    main()
