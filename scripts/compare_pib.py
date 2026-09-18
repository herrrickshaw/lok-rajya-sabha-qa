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

Ministry identity (which PIB label / minister a PQ ministry resolves to) is
resolved once, for every source, in ministry_registry.py -- see that file's
docstring for why (the Netflix-API-evolution lesson: one aggregation layer
per identity, not one bespoke join per caller). This script is a thin
consumer of that registry.

Source: PIB index built for a separate project
(india-trade-sector-policy-recommendations/scripts/pib_index.py ->
data/pib_index.sqlite), 124,857 releases 2017-01-01 to present, refreshed as
of this run. Not re-fetched here -- see that repo for the indexer itself.
"""
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from ministry_registry import PIB_DB, SINCE, load_registry, read_csv

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
SITE = ROOT / "site"


def ministry_comparison(registry):
    rows = []
    matched_minister = 0
    for rec in registry.values():
        ratio = round(rec.pq_total_questions / rec.pib_releases_since_2024_06, 3) if rec.pib_releases_since_2024_06 else None
        if rec.minister_name:
            matched_minister += 1
        rows.append(
            {
                "ministry": rec.pq_ministry,
                "minister_in_charge": rec.minister_name,
                "minister_designation": rec.minister_designation,
                "pq_questions": rec.pq_total_questions,
                "pib_releases_since_2024_06": rec.pib_releases_since_2024_06,
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
    registry = load_registry()
    ministry_rows = ministry_comparison(registry)
    con = sqlite3.connect(str(PIB_DB))
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
