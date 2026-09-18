"""
Wire in every ministry's headless-WordPress scheme catalogue that
ministry_registry.py's WP_JSON_MINISTRIES hook knows about -- MeitY, DoT,
DPIIT as of this run -- and compare each against PQ scrutiny.

These ministries run a Next.js shell site with no crawlable page content,
but their actual scheme content is served underneath by a public WordPress
API (see reference_india_ministry_site_access memory). Started as a
MeitY-only script (compare_meity.py); generalized here because DoT and
DPIIT turned out to use a genuinely different API shape from MeitY's --
verifying each site live rather than assuming they share one shape is what
caught that:

  "wp_core"   -- MeitY: the standard WP REST route (wp/v2/<post_type>),
                 ?per_page=N, a bare JSON array, fields at the top level
                 (title.rendered, modified, acf.introduction).
  "post_page" -- DoT, DPIIT: a custom "post-page" route (not core WP
                 REST), ?limit=N&page=N&orderby=menu_order,
                 {"posts":[...], "total_items", "total_pages"}, snake_case
                 fields (post_title, post_modified, acf_data.introduction).

Both schemas are read through the same SchemeItem shape below, so the rest
of the pipeline (matching, staleness, output) doesn't care which ministry
or API shape a scheme came from.
"""
import csv
import json
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ministry_registry import WP_JSON_MINISTRIES, load_registry, read_csv

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
SITE = ROOT / "site"

STOPWORDS = {
    "scheme", "schemes", "for", "of", "the", "and", "in", "to", "a", "way",
    "forward", "select", "states", "uts", "sector", "guidelines",
    "implementation", "promotion",
}
# Acronyms that name a whole cross-ministry program rather than one scheme --
# matching on these alone massively over-counts (e.g. "PLI" alone matches
# every PLI sub-scheme across every ministry, not just this one).
GENERIC_ACRONYMS = {"PLI", "IT", "CSC", "M", "IL"}

TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class SchemeItem:
    ministry: str
    title: str
    modified: str  # ISO-ish date string
    intro: str
    page: str


def strip_html(text):
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", text or "")).strip()


def fetch_wp_core(ministry, hook):
    url = f"https://www.{hook['site']}/{hook['path']}?per_page=100"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    items = []
    for s in data:
        acf = s.get("acf", {})
        items.append(
            SchemeItem(
                ministry=ministry,
                title=s["title"]["rendered"],
                modified=s["modified"],
                intro=strip_html(acf.get("l3_introduction") or acf.get("introduction") or ""),
                page=s.get("link", ""),
            )
        )
    return items, data


def fetch_post_page(ministry, hook):
    base = f"https://www.{hook['site']}/{hook['path']}"
    all_posts = []
    page = 1
    while True:
        url = f"{base}?limit=10&page={page}&orderby=menu_order"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        all_posts.extend(data.get("posts", []))
        if page >= data.get("total_pages", 1):
            break
        page += 1
    items = []
    for s in all_posts:
        acf = s.get("acf_data", {})
        items.append(
            SchemeItem(
                ministry=ministry,
                title=s["post_title"],
                modified=s["post_modified"],
                intro=strip_html(acf.get("l3_introduction") or acf.get("introduction") or ""),
                page=f"https://www.{hook['site']}/offerings/schemes-and-services/details/{s.get('post_slug', '')}",
            )
        )
    return items, all_posts


FETCHERS = {"wp_core": fetch_wp_core, "post_page": fetch_post_page}


def fetch_all_schemes():
    all_items = []
    raw_dump = {}
    for ministry, hook in WP_JSON_MINISTRIES.items():
        fetcher = FETCHERS.get(hook["schema"])
        if not fetcher:
            print(f"Skipping {ministry}: unknown schema {hook['schema']!r}")
            continue
        try:
            items, raw = fetcher(ministry, hook)
        except Exception as e:
            print(f"Live fetch failed for {ministry} ({hook['site']}): {e}")
            continue
        all_items.extend(items)
        raw_dump[ministry] = raw
        print(f"  {ministry} ({hook['site']}, {hook['schema']}): {len(items)} schemes")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "wp_json_schemes.json").write_text(json.dumps(raw_dump, indent=2))
    return all_items


def load_all_schemes():
    """Prefer a live fetch; fall back to the cached raw dump per ministry if
    any single ministry's fetch fails, so one dead endpoint doesn't blank
    the others."""
    items = fetch_all_schemes()
    cached_path = RAW / "wp_json_schemes.json"
    if not items and cached_path.exists():
        print("All live fetches failed, using cached", cached_path)
        raw_dump = json.loads(cached_path.read_text())
        for ministry, raw in raw_dump.items():
            hook = WP_JSON_MINISTRIES[ministry]
            if hook["schema"] == "wp_core":
                for s in raw:
                    acf = s.get("acf", {})
                    items.append(SchemeItem(ministry, s["title"]["rendered"], s["modified"], strip_html(acf.get("l3_introduction") or acf.get("introduction") or ""), s.get("link", "")))
            else:
                for s in raw:
                    acf = s.get("acf_data", {})
                    items.append(SchemeItem(ministry, s["post_title"], s["post_modified"], strip_html(acf.get("l3_introduction") or acf.get("introduction") or ""), ""))
    return items


# Word regex allows a leading digit (so "5G", "4G", "2.0"-style tokens count
# towards a phrase) but excludes purely-numeric tokens ("100", "2026") on
# their own -- those are dates/counts, not scheme-identifying words.
_WORD_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9\-]*\b")


def _significant_words(text, limit=4):
    words = []
    for w in _WORD_RE.findall(text):
        if w.lower() in STOPWORDS or w.isdigit():
            continue
        words.append(w)
        if len(words) == limit:
            break
    return words


def derive_pattern(title):
    """A scheme's parenthetical acronym if it's genuinely scheme-specific
    (the WHOLE parenthetical must be uppercase letters/digits/./- -- this
    rejects e.g. "(Summer)", a plain word that happens to be in parens, not
    an acronym), else the title's most *distinguishing* words -- preferring
    whatever follows the last " for "/" of ", since many scheme titles share
    boilerplate prefixes ("Production Linked Incentive Scheme (PLI) for
    ...") and differ only in what comes after.

    Requires at least 2 significant words for a phrase match -- a single
    leftover word is usually a generic noun ("Labs", "Portal") that would
    match unrelated PQs everywhere. Titles that don't clear that bar (or
    have no usable acronym) fall back to matching the full title verbatim,
    which will almost never appear in PQ text -- an honest near-zero rather
    than a false-positive-prone single-word match."""
    m = re.search(r"\(([A-Z][A-Z0-9.\-]{1,14})\)", title)
    if m and m.group(1) not in GENERIC_ACRONYMS and len(m.group(1)) >= 3:
        return rf"\b{re.escape(m.group(1))}\b"

    tail_match = re.search(r"\s+(?:for|of)\s+(.+)$", title, re.I)
    tail_words = _significant_words(tail_match.group(1)) if tail_match else []
    words = tail_words if len(tail_words) >= 2 else _significant_words(title)
    if len(words) < 2:
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
        dt = datetime.fromisoformat(date_str.replace(" ", "T")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return round((datetime.now(timezone.utc) - dt).days / 30.44, 1)


def build_corpus():
    ls_rows = read_csv("ls_questions_enriched.csv")
    rs_rows = read_csv("rs_questions_enriched.csv")
    return [r["subject"] for r in ls_rows] + [r["subject"] for r in rs_rows] + [r.get("question_text") for r in rs_rows]


def main():
    print("Fetching ministry scheme catalogues...")
    schemes = load_all_schemes()
    if not schemes:
        raise SystemExit("No scheme data available from any ministry (live fetch and cache both failed)")

    corpus = build_corpus()
    registry = load_registry()

    rows = []
    for s in schemes:
        pattern = re.compile(derive_pattern(s.title), re.I)
        pq_mentions = sum(1 for text in corpus if text and pattern.search(text))
        rows.append(
            {
                "ministry": s.ministry,
                "scheme": s.title,
                "last_modified": s.modified[:10],
                "months_since_update": months_since(s.modified),
                "outlay_rs_cr_mentioned": extract_outlay(s.intro),
                "pq_mentions": pq_mentions,
                "scheme_page": s.page,
            }
        )
    rows.sort(key=lambda r: (r["ministry"], -r["pq_mentions"]))

    fieldnames = ["ministry", "scheme", "last_modified", "months_since_update", "outlay_rs_cr_mentioned", "pq_mentions", "scheme_page"]
    with open(PROC / "ministry_scheme_scrutiny.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_ministry = {}
    for ministry in WP_JSON_MINISTRIES:
        m_rows = [r for r in rows if r["ministry"] == ministry]
        if not m_rows:
            continue
        zero = sum(1 for r in m_rows if r["pq_mentions"] == 0)
        stale = sum(1 for r in m_rows if (r["months_since_update"] or 0) > 12)
        rec = registry.get(ministry)
        by_ministry[ministry] = {
            "ministry_total_pq": rec.pq_total_questions if rec else 0,
            "minister_in_charge": rec.minister_name if rec else "",
            "source": f"https://www.{WP_JSON_MINISTRIES[ministry]['site']}/{WP_JSON_MINISTRIES[ministry]['path']}",
            "scheme_count": len(m_rows),
            "zero_pq_count": zero,
            "stale_count": stale,
        }

    payload = {
        "by_ministry": by_ministry,
        "rows": rows,
        "note": (
            "Each ministry's own scheme catalogue (public WordPress-backed API behind its "
            "otherwise-uncrawlable JS-shell site; MeitY, DoT and DPIIT use two different API "
            "shapes, verified independently rather than assumed identical), matched against PQ "
            "text by each scheme's parenthetical acronym (only when genuinely scheme-specific) or "
            "distinguishing title words -- a heuristic match, a lower bound, not a verified "
            "extraction. months_since_update is time since that ministry's own CMS last touched "
            "the scheme's page, not evidence the scheme itself is inactive."
        ),
    }
    (SITE / "meity.json").write_text(json.dumps(payload, indent=2))

    print(f"\n{len(rows)} schemes across {len(by_ministry)} ministries")
    for ministry, stats in by_ministry.items():
        print(f"  {ministry}: {stats['scheme_count']} schemes, {stats['zero_pq_count']} zero-PQ, {stats['stale_count']} stale 12mo+")


if __name__ == "__main__":
    main()
