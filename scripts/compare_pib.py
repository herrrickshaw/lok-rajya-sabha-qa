"""
Treat the PQ corpus as a real text source and cross-reference it against PIB
(Press Information Bureau) press releases over the same window: does what
Parliament grills a ministry about via questions match what that ministry
proactively self-publicizes via press releases?

Two comparisons:
  1. Ministry level -- PQ volume vs PIB release volume, same date range.
     A high PQ:PIB ratio means a ministry gets a lot of parliamentary
     scrutiny relative to how much it publicizes itself; a low ratio means
     the opposite (heavy self-promotion, comparatively little PQ pressure).
  2. Scheme/topic level -- named government schemes and programmes extracted
     from actual PQ text (Lok Sabha subject lines + Rajya Sabha full question
     text, which we do have inline) are checked against PIB release titles
     in the same window: is this scheme showing up in both, PQ-only
     (scrutinised but not much self-publicized), or PIB-only (the reverse)?

Source: PIB index built for a separate project
(india-trade-sector-policy-recommendations/scripts/pib_index.py ->
data/pib_index.sqlite), 124,857 releases 2017-01-01 to present, refreshed as
of this run. Not re-fetched here -- see that repo for the indexer itself.
"""
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
SITE = ROOT / "site"
PIB_DB = Path("/Users/umashankar/india-trade-sector-policy-recommendations/data/pib_index.sqlite")
# Ministry -> current Minister-in-charge, built for a sibling project on top
# of the same PIB index + igod.gov.in who's-who scrape. Completes the
# accountability chain this repo already draws (Party -> MP -> Question ->
# Ministry) one link further: -> the minister actually answering it.
MINISTER_CONTACTS_CSV = Path("/Users/umashankar/india-govt-yellow-pages/data/pib_ministry_contacts.csv")
SINCE = "2024-06-01"

# PQ ministry name (as used throughout this repo) -> PIB ministry label(s) to
# sum. Most are a direct normalized match (handled generically below); this
# covers the cases where Parliament's ministry taxonomy and PIB's diverge --
# a combined ministry (Jal Shakti) split across PIB's two constituent
# departments, and a ministry PIB lists by its sub-departments only.
MANUAL_ALIASES = {
    # Ministry of Jal Shakti (2019-) is a single PIB label post-2024; the old
    # pre-merger department labels only appear in historical (pre-2019) rows
    # and are deliberately NOT included here.
    "CHEMICALS AND FERTILIZERS": [
        "Ministry of Chemicals and Fertilizers",
        "Ministry of Chemicals and Fertilizers - Department of Chemicals and Petrochemicals",
        "Ministry of Chemicals and Fertilizers - Department of Fertilizers",
        "Ministry of Chemicals and Fertilizers - Department of Pharmaceuticals",
    ],
    "ATOMIC ENERGY": ["Department of Atomic Energy"],
    "SPACE": ["Department of Space"],
    "ELECTRONICS AND INFORMATION TECHNOLOGY": ["Ministry of Electronics & IT"],
    "COMMUNICATION": ["Ministry of Communications"],
    "DEVELOPMENT OF NORTH EASTERN REGION": ["Ministry of Development of North-East Region"],
}


def normalize(label):
    if not label:
        return ""
    s = label.strip()
    s = re.sub(r"^(Ministry of|Department of)\s+", "", s, flags=re.I)
    s = s.split(" - ")[0]  # drop sub-department suffix for the generic path
    s = s.replace("&", "AND")
    s = re.sub(r"[,.]", " ", s)  # comma/period become a space, not deleted -- "Micro,Small" must not fuse into "MicroSmall"
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def read_csv(name):
    with open(PROC / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_minister_lookup():
    """ministry (our normalized form) -> (name, designation) of the senior-most minister, from a sibling repo's igod/PIB-sourced who's-who."""
    if not MINISTER_CONTACTS_CSV.exists():
        return {}
    rank = {"Minister": 0, "Minister of State (Independent Charge)": 1, "Minister of State": 2}
    best = {}
    with open(MINISTER_CONTACTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name, designation = row.get("contact_name", "").strip(), row.get("designation", "").strip()
            if not name:
                continue
            key = normalize(row["ministry"])
            score = rank.get(designation, 3)
            if key not in best or score < best[key][2]:
                best[key] = (name, designation, score)
    return {k: (v[0], v[1]) for k, v in best.items()}


def ministry_comparison(con):
    ministry_summary = read_csv("ministry_summary.csv")
    minister_lookup = load_minister_lookup()
    cur = con.cursor()
    cur.execute("SELECT ministry, COUNT(*) FROM pib_items WHERE date >= ? AND kind='release' GROUP BY ministry", (SINCE,))
    pib_counts_raw = dict(cur.fetchall())

    pib_norm_counts = Counter()
    for label, cnt in pib_counts_raw.items():
        pib_norm_counts[normalize(label)] += cnt

    rows = []
    matched_minister = 0
    for m in ministry_summary:
        ministry = m["ministry"]
        pq_count = int(m["questions"])
        if ministry in MANUAL_ALIASES:
            pib_count = sum(pib_counts_raw.get(lbl, 0) for lbl in MANUAL_ALIASES[ministry])
        else:
            pib_count = pib_norm_counts.get(normalize(ministry), 0)
        ratio = round(pq_count / pib_count, 3) if pib_count else None
        minister_name, minister_designation = minister_lookup.get(normalize(ministry), ("", ""))
        if minister_name:
            matched_minister += 1
        rows.append(
            {
                "ministry": ministry,
                "minister_in_charge": minister_name,
                "minister_designation": minister_designation,
                "pq_questions": pq_count,
                "pib_releases_since_2024_06": pib_count,
                "pq_per_pib_release": ratio,
            }
        )
    rows.sort(key=lambda r: -(r["pq_per_pib_release"] or 0))
    fieldnames = ["ministry", "minister_in_charge", "minister_designation", "pq_questions", "pib_releases_since_2024_06", "pq_per_pib_release"]
    with open(PROC / "pib_ministry_comparison.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    matched = sum(1 for r in rows if r["pib_releases_since_2024_06"] > 0)
    print(f"Ministry comparison: {matched}/{len(rows)} PQ ministries matched to a PIB label, {matched_minister}/{len(rows)} matched to a minister-in-charge")
    return rows


# ---- Scheme/programme name extraction from actual PQ text ----
SCHEME_PATTERNS = [
    re.compile(r"\bPradhan Mantri [A-Z][A-Za-z\-]*(?: [A-Z][A-Za-z\-]*){0,5}(?: Yojana| Scheme| Mission| Abhiyan)?\b"),
    re.compile(r"\b[A-Z][A-Za-z\-]*(?: [A-Z][A-Za-z\-]*){0,3} Yojana\b"),
    re.compile(r"\b[A-Z][A-Za-z\-]*(?: [A-Z][A-Za-z\-]*){0,3} Mission\b"),
    re.compile(r"\b[A-Z][A-Za-z\-]*(?: [A-Z][A-Za-z\-]*){0,3} Abhiyan\b"),
    re.compile(r"\bPLI Scheme(?: for [A-Z][A-Za-z\-]*(?: [A-Z][A-Za-z\-]*){0,3})?\b"),
    re.compile(r"\b(?:PM|PM-)[A-Z][A-Za-z\-]+\b"),
]
STOP_TERMS = {"the government", "central government", "state government"}


def extract_schemes(text, counter):
    if not text:
        return
    for pat in SCHEME_PATTERNS:
        for m in pat.finditer(text):
            term = re.sub(r"\s+", " ", m.group(0)).strip()
            if len(term) < 6 or term.lower() in STOP_TERMS:
                continue
            counter[term] += 1


def scheme_comparison(con):
    counter = Counter()
    for row in read_csv("ls_questions_enriched.csv"):
        extract_schemes(row.get("subject"), counter)
    for row in read_csv("rs_questions_enriched.csv"):
        extract_schemes(row.get("subject"), counter)
        extract_schemes(row.get("question_text"), counter)

    # Collapse near-duplicates that differ only by trailing Yojana/Scheme/Mission
    collapsed = Counter()
    canonical_for = {}
    for term, cnt in counter.items():
        base = re.sub(r"\s+(Yojana|Scheme|Mission|Abhiyan)$", "", term, flags=re.I)
        canonical_for.setdefault(base.lower(), term)
        collapsed[canonical_for[base.lower()]] += cnt

    top_terms = [t for t, c in collapsed.most_common(80) if c >= 8]

    cur = con.cursor()
    rows = []
    for term in top_terms:
        pq_mentions = collapsed[term]
        like = f"%{term}%"
        cur.execute(
            "SELECT COUNT(*) FROM pib_items WHERE date >= ? AND kind='release' AND title LIKE ?",
            (SINCE, like),
        )
        pib_mentions = cur.fetchone()[0]
        rows.append({"term": term, "pq_mentions": pq_mentions, "pib_release_mentions": pib_mentions})

    rows.sort(key=lambda r: -r["pq_mentions"])
    with open(PROC / "pib_scheme_comparison.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["term", "pq_mentions", "pib_release_mentions"])
        w.writeheader()
        w.writerows(rows)

    pq_only = [r for r in rows if r["pib_release_mentions"] == 0][:15]
    both = [r for r in rows if r["pib_release_mentions"] > 0][:15]
    print(f"Scheme/topic terms extracted: {len(rows)}")
    print("Top PQ-only (scrutinised, ~zero PIB self-coverage in title text):")
    for r in pq_only[:10]:
        print(" ", r["term"], r["pq_mentions"])
    print("Top overlapping (both PQ'd and PIB-covered):")
    for r in both[:10]:
        print(" ", r["term"], "pq=", r["pq_mentions"], "pib=", r["pib_release_mentions"])
    return rows


def main():
    if not PIB_DB.exists():
        raise SystemExit(f"PIB index not found at {PIB_DB}")
    con = sqlite3.connect(str(PIB_DB))
    ministry_rows = ministry_comparison(con)
    scheme_rows = scheme_comparison(con)
    con.close()

    payload = {
        "since": SINCE,
        "ministry_comparison": ministry_rows,
        "scheme_comparison": scheme_rows,
        "note": (
            "PIB (Press Information Bureau) press-release index built for a separate project, "
            "124,857 releases 2017-present, refreshed to match this dataset's window. External "
            "Affairs' near-zero release count is a known gap in that index for MEA specifically, "
            "not a real signal. Scheme matching is release-title text only (a floor on PIB "
            "coverage, not a ceiling)."
        ),
    }
    (SITE / "pib.json").write_text(json.dumps(payload, indent=2))
    print("Wrote", SITE / "pib.json")


if __name__ == "__main__":
    main()
