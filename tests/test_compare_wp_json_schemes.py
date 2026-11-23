"""scripts/compare_wp_json_schemes.py: scheme catalogue fetchers (urllib faked), pattern derivation and the PQ-scrutiny join."""
import csv
import io
import json
import re
import urllib.request
from datetime import datetime, timezone

import pytest


@pytest.fixture
def W(load):
    return load("compare_wp_json_schemes")


def write_csv(repo, name, rows, cols):
    p = repo / "data/processed" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ text helpers
def test_strip_html(W):
    assert W.strip_html("<p>Rs.  <b>100</b>\n crore</p>") == "Rs. 100 crore"
    assert W.strip_html(None) == "" and W.strip_html("") == ""


def test_significant_words(W):
    assert W._significant_words("Scheme for the 5G Test Beds 2026 and Labs") == ["5G", "Test", "Beds", "Labs"]       # stopwords and bare numbers dropped, limit 4
    assert W._significant_words("Alpha Beta Gamma Delta Eps", limit=2) == ["Alpha", "Beta"]
    assert W._significant_words("") == [] and W._significant_words("of the and") == []
    assert W._significant_words("Foo-Bar Baz") == ["Foo-Bar", "Baz"]


def test_derive_pattern_acronym_rules(W):
    assert W.derive_pattern("Semiconductor Components (SPECS) Scheme") == r"\bSPECS\b"
    assert W.derive_pattern("Production Linked Incentive (PLI) for Large Scale Electronics").startswith("Large")     # generic acronym rejected -> tail words
    assert W.derive_pattern("Something (AB)") != r"\bAB\b"                                                           # < 3 chars rejected
    assert W.derive_pattern("Something (ABC)") == r"\bABC\b"                                                         # exactly 3 accepted
    assert W.derive_pattern("Something (Summer) Scheme Alpha Beta").startswith("Something")                          # not an acronym
    assert W.derive_pattern("Thing (A.B-C9)") == re.escape(r"A.B-C9").join([r"\b", r"\b"])
    assert W.derive_pattern("X (ABCDEFGHIJKLMNO)") == r"\bABCDEFGHIJKLMNO\b"                                        # 15 chars accepted
    assert W.derive_pattern("X (ABCDEFGHIJKLMNOP)") != r"\bABCDEFGHIJKLMNOP\b"                                      # 16 chars rejected


def test_derive_pattern_phrase_and_fallback(W):
    assert W.derive_pattern("Support for Electronic Component Manufacturing Ecosystem Extra") == r"Electronic\s+Component\s+Manufacturing\s+Ecosystem"
    assert W.derive_pattern("Alpha Beta Gamma") == r"Alpha\s+Beta\s+Gamma"                                          # no tail: leading significant words
    assert W.derive_pattern("Boost for Labs") == r"Boost\s+Labs"                                                    # tail has 1 word -> fall back to the whole title
    assert W.derive_pattern("Portal") == "Portal"                                                                   # single word: verbatim title
    assert W.derive_pattern("Scheme for 1.5 (v2)") == re.escape("Scheme for 1.5 (v2)")


def test_extract_outlay(W):
    assert W.extract_outlay("An outlay of Rs. 1,234.5 Crore over 5 years") == 1234.5
    assert W.extract_outlay("rs 20 crore") == 20.0 and W.extract_outlay("Rs.7,00 CRORE") == 700.0
    assert W.extract_outlay("Rs. ,,, Crore") is None                                    # digits-and-commas group that is not a number
    assert W.extract_outlay("Rs 5 lakh") is None and W.extract_outlay("") is None and W.extract_outlay(None) is None


def test_months_since(W, monkeypatch):
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr(W, "datetime", FakeDT)
    assert W.months_since("2026-06-01 00:00:00") == round(30 / 30.44, 1)
    assert W.months_since("2025-07-01T00:00:00") == round(365 / 30.44, 1)
    assert W.months_since("2026-07-01") == 0.0
    assert W.months_since("garbage") is None


# ------------------------------------------------------------------ fetchers
class Resp(io.StringIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def patch_urlopen(monkeypatch, router):
    seen = []

    def urlopen(req, timeout=None):
        seen.append((req.full_url, timeout, req.get_header("User-agent")))
        r = router(req.full_url)
        if isinstance(r, Exception):
            raise r
        return Resp(json.dumps(r))
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return seen


CORE = [{"title": {"rendered": "SPECS Scheme"}, "modified": "2025-01-02T03:04:05", "acf": {"l3_introduction": "<p>Rs. 100 Crore</p>"}, "link": "https://m/specs"},
        {"title": {"rendered": "Other"}, "modified": "2024-01-01T00:00:00", "link": "https://m/o"},
        {"title": {"rendered": "Intro2"}, "modified": "2024-01-01T00:00:00", "acf": {"introduction": "<b>text</b>"}}]


def test_fetch_wp_core(W, monkeypatch):
    seen = patch_urlopen(monkeypatch, lambda u: CORE)
    items, raw = W.fetch_wp_core("MEITY", {"site": "meity.gov.in", "path": "cms/x"})
    assert seen == [("https://www.meity.gov.in/cms/x?per_page=100", 30, "Mozilla/5.0")]
    assert raw == CORE and [i.title for i in items] == ["SPECS Scheme", "Other", "Intro2"]
    assert items[0] == W.SchemeItem("MEITY", "SPECS Scheme", "2025-01-02T03:04:05", "Rs. 100 Crore", "https://m/specs")
    assert items[1].intro == "" and items[1].page == "https://m/o" and items[2].intro == "text" and items[2].page == ""


def test_fetch_post_page_paginates(W, monkeypatch):
    pages = {1: {"posts": [{"post_title": "A", "post_modified": "m1", "acf_data": {"introduction": "i"}, "post_slug": "a"}], "total_pages": 2},
             2: {"posts": [{"post_title": "B", "post_modified": "m2", "post_slug": "b"}], "total_pages": 2}}
    seen = patch_urlopen(monkeypatch, lambda u: pages[int(re.search(r"page=(\d+)", u).group(1))])
    items, raw = W.fetch_post_page("DOT", {"site": "dot.gov.in", "path": "cms/p"})
    assert [s[0] for s in seen] == ["https://www.dot.gov.in/cms/p?limit=10&page=1&orderby=menu_order", "https://www.dot.gov.in/cms/p?limit=10&page=2&orderby=menu_order"]
    assert [i.title for i in items] == ["A", "B"] and len(raw) == 2
    assert items[0].page == "https://www.dot.gov.in/offerings/schemes-and-services/details/a" and items[0].intro == "i" and items[1].intro == ""


def test_fetch_post_page_single_page_default(W, monkeypatch):
    seen = patch_urlopen(monkeypatch, lambda u: {"posts": [{"post_title": "A", "post_modified": "m"}]})
    items, _ = W.fetch_post_page("X", {"site": "s", "path": "p"})
    assert len(seen) == 1 and items[0].page.endswith("/details/")


def test_fetch_all_schemes_collects_and_survives_failures(W, repo, monkeypatch, capsys):
    def router(u):
        if "meity" in u:
            return CORE
        if "dot.gov.in" in u:
            return OSError("down")
        return {"posts": [{"post_title": "DPIIT One", "post_modified": "2025-05-05", "post_slug": "d"}], "total_pages": 1}
    patch_urlopen(monkeypatch, router)
    items = W.fetch_all_schemes()
    assert [i.ministry for i in items].count("ELECTRONICS AND INFORMATION TECHNOLOGY") == 3 and [i.title for i in items][-1] == "DPIIT One"
    out = capsys.readouterr().out
    assert "ELECTRONICS AND INFORMATION TECHNOLOGY (meity.gov.in, wp_core): 3 schemes" in out and "Live fetch failed for COMMUNICATION (dot.gov.in): down" in out
    dump = json.loads((repo / "data/raw/wp_json_schemes.json").read_text())
    assert set(dump) == {"ELECTRONICS AND INFORMATION TECHNOLOGY", "COMMERCE AND INDUSTRY"}


def test_fetch_all_schemes_unknown_schema_is_skipped(W, repo, monkeypatch, capsys):
    monkeypatch.setattr(W, "WP_JSON_MINISTRIES", {"ODD": {"site": "x", "schema": "mystery", "path": "p"}})
    patch_urlopen(monkeypatch, lambda u: pytest.fail("no request expected"))
    assert W.fetch_all_schemes() == []
    assert "Skipping ODD: unknown schema 'mystery'" in capsys.readouterr().out


def test_load_all_schemes_uses_live_items_when_available(W, monkeypatch):
    monkeypatch.setattr(W, "fetch_all_schemes", lambda: ["live"])
    assert W.load_all_schemes() == ["live"]


def test_load_all_schemes_cache_fallback(W, repo, monkeypatch, capsys):
    monkeypatch.setattr(W, "fetch_all_schemes", lambda: [])
    assert W.load_all_schemes() == []                                                    # no cache either
    (repo / "data/raw").mkdir(parents=True, exist_ok=True)
    (repo / "data/raw/wp_json_schemes.json").write_text(json.dumps({
        "ELECTRONICS AND INFORMATION TECHNOLOGY": CORE[:1],
        "COMMUNICATION": [{"post_title": "BharatNet", "post_modified": "2025-01-01", "acf_data": {"introduction": "<i>fast</i>"}}]}))
    items = W.load_all_schemes()
    assert [(i.ministry, i.title, i.intro, i.page) for i in items] == [
        ("ELECTRONICS AND INFORMATION TECHNOLOGY", "SPECS Scheme", "Rs. 100 Crore", "https://m/specs"), ("COMMUNICATION", "BharatNet", "fast", "")]
    assert "All live fetches failed, using cached" in capsys.readouterr().out


# ------------------------------------------------------------------ main
def test_main_without_data_exits(W, monkeypatch):
    monkeypatch.setattr(W, "load_all_schemes", lambda: [])
    with pytest.raises(SystemExit) as e:
        W.main()
    assert "No scheme data available" in str(e.value)


def test_main_scores_pq_mentions_and_writes_outputs(W, repo, monkeypatch, capsys):
    import ministry_registry as R
    SI = W.SchemeItem
    eit, dot = "ELECTRONICS AND INFORMATION TECHNOLOGY", "COMMUNICATION"
    schemes = [SI(eit, "Semiconductor Components (SPECS) Scheme", "2024-01-05T00:00:00", "Outlay Rs. 3,000 Crore", "p1"),
               SI(eit, "Quantum Computing Mission", "2026-01-01T00:00:00", "", "p2"),
               SI(dot, "BharatNet Rural Broadband", "bad-date", "", "p3")]
    monkeypatch.setattr(W, "load_all_schemes", lambda: schemes)
    monkeypatch.setattr(W, "load_registry", lambda: {eit: R.MinistryRecord(pq_ministry=eit, pq_total_questions=50, minister_name="Shri V")})
    write_csv(repo, "ls_questions_enriched.csv", [dict(subject="Status of SPECS funding"), dict(subject="specs again"), dict(subject="quantum computing mission news"), dict(subject="x")], ["subject"])
    write_csv(repo, "rs_questions_enriched.csv", [dict(subject="y", question_text="SPECS in text"), dict(subject="z", question_text="")], ["subject", "question_text"])
    W.main()
    with open(repo / "data/processed/ministry_scheme_scrutiny.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [(r["ministry"], r["scheme"]) for r in rows] == [(dot, "BharatNet Rural Broadband"), (eit, "Semiconductor Components (SPECS) Scheme"), (eit, "Quantum Computing Mission")]
    specs = rows[1]
    assert (specs["pq_mentions"], specs["last_modified"], specs["outlay_rs_cr_mentioned"], specs["scheme_page"]) == ("3", "2024-01-05", "3000.0", "p1")   # sorted by ministry, then mentions desc
    assert float(specs["months_since_update"]) > 12 and rows[2]["pq_mentions"] == "1" and rows[0]["months_since_update"] == "" and rows[0]["pq_mentions"] == "0"
    payload = json.loads((repo / "site/meity.json").read_text())
    assert payload["by_ministry"][eit] == {"ministry_total_pq": 50, "minister_in_charge": "Shri V", "source": "https://www.meity.gov.in/cms/wp-json/wp/v2/schemes_and_services",
                                           "scheme_count": 2, "zero_pq_count": 0, "stale_count": 1}
    assert payload["by_ministry"][dot]["ministry_total_pq"] == 0 and payload["by_ministry"][dot]["minister_in_charge"] == "" and payload["by_ministry"][dot]["zero_pq_count"] == 1
    assert "COMMERCE AND INDUSTRY" not in payload["by_ministry"]                              # ministries with no schemes are omitted
    out = capsys.readouterr().out
    assert "3 schemes across 2 ministries" in out and f"  {eit}: 2 schemes, 0 zero-PQ, 1 stale 12mo+" in out
