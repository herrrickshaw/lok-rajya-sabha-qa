"""
Wire in MeitY's own scheme catalogue -- the first of the "surveyed but not
integrated" ministry-website sources in ministry_registry.py's
WP_JSON_MINISTRIES hook -- and compare it against PQ scrutiny.

MeitY (and DoT/DPIIT, not yet wired) run a Next.js shell site with no
crawlable content, but the actual scheme content is served by a public
WordPress REST API underneath (`<site>/cms/wp-json/wp/v2/schemes_and_services`
-- see reference_india_ministry_site_access memory). This fetches that
endpoint directly: 22 schemes, each with a description, an approval/launch
narrative, and a `modified` timestamp -- the ministry's own record of what it
runs and when it last touched the page.

Two things this adds that compare_pli.py's 13-scheme report card doesn't
cover: (1) it's MeitY's *complete* scheme catalogue, not just the PLI subset
-- 9 of these 22 schemes are entirely outside the PLI program (GENESIS,
CSC 2.0, internships, PhD fellowships, academies); (2) `modified` dates
surface stale scheme pages directly -- the ministry-site-access memory
already flagged that these pages are routinely stale (frozen "last updated"
stamps, present-tense language for schemes long closed), so this measures
that staleness instead of just asserting it.
"""
import csv
import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ministry_registry import WP_JSON_MINISTRIES, read_csv

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
SITE = ROOT / "site"

MEITY_MINISTRY = "ELECTRONICS AND INFORMATION TECHNOLOGY"
STOPWORDS = {
    "scheme", "schemes", "for", "of", "the", "and", "in", "to", "a", "way",
    "forward", "select", "states", "uts", "sector", "guidelines",
    "implementation", "promotion",
}


def fetch_schemes():
    site, namespace = WP_JSON_MINISTRIES[MEITY_MINISTRY]
    url = f"https://www.{site}/{namespace}?per_page=100"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "meity_schemes.json").write_text(json.dumps(data, indent=2))
    return data


def load_schemes():
    cached = RAW / "meity_schemes.json"
    if cached.exists():
        return json.loads(cached.read_text())
    return fetch_schemes()


# Acronyms that name a whole cross-ministry government program rather than
# this one specific scheme -- matching on these alone massively over-counts
# (e.g. "PLI" alone matches every PLI sub-scheme across every ministry, not
# just MeitY's Electronics/IT Hardware one). For these, require the acronym
# AND a scheme-specific title word, never the acronym on its own.
GENERIC_ACRONYMS = {"PLI", "IT", "CSC", "M"}


def _significant_words(text, limit=4):
    return [w for w in re.findall(r"[A-Za-z][A-Za-z\-]+", text) if w.lower() not in STOPWORDS][:limit]


def derive_pattern(title):
    """A scheme's parenthetical acronym if it has one and it's specific
    enough to identify this scheme alone (most reliable match, since that's
    how PQs usually refer to a scheme); otherwise its most *distinguishing*
    title words as an ordered near-phrase -- preferring whatever follows the
    last " for "/" of " (the scheme's actual subject), since many MeitY
    scheme titles share the same boilerplate prefix ("Production Linked
    Incentive Scheme (PLI) for ...") and differ only in what comes after."""
    # Require the WHOLE parenthetical to be uppercase letters/digits/./- --
    # rejects e.g. "(Summer)" or "(GENESIS)"-style mixed captures that aren't
    # actually acronyms, without rejecting real ones like "M-SIPS" or "EMC".
    m = re.search(r"\(([A-Z][A-Z0-9.\-]{1,14})\)", title)
    if m and m.group(1) not in GENERIC_ACRONYMS and len(m.group(1)) >= 3:
        return rf"\b{re.escape(m.group(1))}\b"

    tail_match = re.search(r"\s+(?:for|of)\s+(.+)$", title, re.I)
    tail_words = _significant_words(tail_match.group(1)) if tail_match else []
    words = tail_words if len(tail_words) >= 2 else _significant_words(title)
    if not words:
        return re.escape(title)
    return r"\s+".join(re.escape(w) for w in words)


def extract_outlay(text):
    m = re.search(r"Rs\.?\s*([\d,]+(?:\.\d+)?)\s*Crore", text or "", re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def months_since(date_str):
    try:
        dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    return round((now - dt).days / 30.44, 1)


def build_corpus():
    ls_rows = read_csv("ls_questions_enriched.csv")
    rs_rows = read_csv("rs_questions_enriched.csv")
    return [r["subject"] for r in ls_rows] + [r["subject"] for r in rs_rows] + [r.get("question_text") for r in rs_rows]


def main():
    if MEITY_MINISTRY not in WP_JSON_MINISTRIES:
        raise SystemExit(f"{MEITY_MINISTRY} has no wp_json hook in ministry_registry.py")

    try:
        schemes = fetch_schemes()
    except Exception as e:
        cached = RAW / "meity_schemes.json"
        if not cached.exists():
            raise SystemExit(f"Could not fetch MeitY schemes and no cache at {cached}: {e}")
        print(f"Live fetch failed ({e}), using cached {cached}")
        schemes = json.loads(cached.read_text())

    corpus = build_corpus()
    compiled_corpus_len = len(corpus)

    rows = []
    for s in schemes:
        title = s["title"]["rendered"]
        acf = s.get("acf", {})
        intro = acf.get("l3_introduction") or acf.get("introduction") or ""
        pattern = re.compile(derive_pattern(title), re.I)
        pq_mentions = sum(1 for text in corpus if text and pattern.search(text))
        rows.append(
            {
                "scheme": title,
                "category": acf.get("category", ""),
                "meity_last_modified": s["modified"][:10],
                "months_since_update": months_since(s["modified"]),
                "outlay_rs_cr_mentioned": extract_outlay(intro),
                "pq_mentions": pq_mentions,
                "meity_page": s.get("link", ""),
            }
        )

    rows.sort(key=lambda r: -r["pq_mentions"])
    fieldnames = ["scheme", "category", "meity_last_modified", "months_since_update", "outlay_rs_cr_mentioned", "pq_mentions", "meity_page"]
    with open(PROC / "meity_scheme_scrutiny.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    ministry_total_pq = int(next((r["questions"] for r in read_csv("ministry_summary.csv") if r["ministry"] == MEITY_MINISTRY), 0))
    zero_pq = [r for r in rows if r["pq_mentions"] == 0]
    stale = sorted([r for r in rows if (r["months_since_update"] or 0) > 12], key=lambda r: -(r["months_since_update"] or 0))

    payload = {
        "ministry": MEITY_MINISTRY,
        "ministry_total_pq": ministry_total_pq,
        "source_url": f"https://www.{WP_JSON_MINISTRIES[MEITY_MINISTRY][0]}/{WP_JSON_MINISTRIES[MEITY_MINISTRY][1]}",
        "rows": rows,
        "note": (
            "MeitY's own scheme catalogue (public WordPress REST API behind its JS-shell site, "
            "22 schemes as of this run), matched against PQ text by each scheme's parenthetical "
            "acronym (if it has one) or its first significant title words -- a heuristic match, "
            "not a verified extraction; treat pq_mentions as a lower bound. months_since_update "
            "is time since MeitY's own CMS last touched that scheme's page, not evidence the "
            "scheme itself is inactive."
        ),
    }
    (SITE / "meity.json").write_text(json.dumps(payload, indent=2))

    print(f"MeitY schemes: {len(rows)} fetched, corpus {compiled_corpus_len} PQ texts")
    print(f"Ministry total PQ ({MEITY_MINISTRY}): {ministry_total_pq}")
    print(f"Schemes with zero PQ mentions: {len(zero_pq)}/{len(rows)}")
    print(f"Schemes not updated on MeitY's own site in 12+ months: {len(stale)}/{len(rows)}")
    for r in rows[:8]:
        print(f"  pq={r['pq_mentions']:>3}  {r['scheme'][:55]:<55}  updated {r['meity_last_modified']}")


if __name__ == "__main__":
    main()
