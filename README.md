# Lok & Rajya Sabha — Parliament Questions Ledger

Who asks Parliament what. Every Lok Sabha question since the 18th Lok Sabha convened
(June 2024) and every Rajya Sabha question over the matching sessions (265–271),
matched to the asking MP's party and state, ranked and cross-tabbed by party,
ministry, state and topic — plus a knowledge-graph layer on top that surfaces
each party's *signature* ministries, which parties cluster together by what they
ask about, and the rare MPs who co-sign questions across party lines.

**Dashboard:** https://claude.ai/artifact/P81z1Qnfur4XS2uvgMakEr
**Workbook:** `Lok_Rajya_Sabha_PQ_Analysis.xlsx`
**Database:** `data/pq_ledger.duckdb`
**Write-up:** `docs/ANALYSIS.md`, `docs/parties/<party>.md`

## What a Parliament Question is

Per Rules 32–54 of the Lok Sabha's Rules of Procedure (Rules 47–50 in the Rajya
Sabha), an MP files a notice — max 150 words, no policy-level or sub-judice
matters, at most 5 notices a day — at least 15 days ahead (10 for a short-notice
question). A **starred** question gets an oral answer and floor follow-ups,
capped at one per MP per sitting day; an **unstarred** question gets only a
written reply on the record. (Definitions cross-checked against Drishti IAS,
["Questioning in Parliament"](https://www.drishtiias.com/daily-news-analysis/questioning-in-parliament),
a standard UPSC-prep civics reference — used here only to confirm procedural
facts against a reliable secondary source, not as data.)

## Data sources

| Source | What it gives | Access |
|---|---|---|
| `sansad.in` `api_ls` | All 18th Lok Sabha questions (34,720): subject, ministry, asking member(s), type, date, session — no full question/answer text, only the per-question PDF | Undocumented JSON API, found in the Next.js client bundle |
| `sansad.in` `api_ls`/`api_rs` member endpoints | Both houses' current *and* former member rosters: party, state, constituency | Undocumented JSON API |
| `rsdoc.nic.in` `Question/Search_Questions` | All Rajya Sabha questions for sessions 265–271 (24,661): full question text, ministry, MP code, type, date — answer text is `null` for every record; answers are PDF-only | Raw parametrised-SQL `whereclause` query param |

None of these are documented public APIs — see the inline comments in
`scripts/build.py` for the exact endpoints and how they were found (mining the
Next.js chunks for the real backend host, same technique for both chambers).
Party names and ministry/state labels are reconciled across the two chambers'
independently-maintained naming conventions where they diverged — e.g. Lok
Sabha's `SHSUBT` vs Rajya Sabha's `SS-UBT` both become `SHS(UBT)`; `Kerala` vs
`Keralam`; `HOUSING AND URBAN AFFAIRS` vs `Housing and Urban Affairs` (see
`PARTY_ALIASES` / `STATE_ALIASES` / `canonical_ministry` in `build.py`).

## Reproducing it

```bash
# 1. Fetch raw data (writes into data/raw/) — see scripts/build.py's docstring
#    for the exact endpoints; there's no single fetch script since each pull
#    was a one-off paginated/bulk curl, documented there.

# 2. Enrich + aggregate
python3 scripts/build.py          # -> data/processed/*.csv, site/data.json

# 3. Knowledge-graph analysis
python3 scripts/build_graph.py    # -> data/processed/kg_*.csv, graph.graphml, site/graph.json

# 4. Render the dashboard
python3 scripts/render_site.py    # -> site/index.html

# 5. Load everything into DuckDB + write markdown summaries
python3 scripts/build_db.py       # -> data/pq_ledger.duckdb, docs/ANALYSIS.md, docs/parties/*.md

# 6. Build the Excel workbook
python3 scripts/build_xlsx.py     # -> Lok_Rajya_Sabha_PQ_Analysis.xlsx
```

Requires `networkx` and `duckdb` (both pure-Python-installable; no `scipy` —
PageRank is implemented as plain power iteration in `build_graph.py` to avoid
that dependency) plus `pandas`/`openpyxl` for the workbook.

## Querying the database

```bash
python3 -c "
import duckdb
con = duckdb.connect('data/pq_ledger.duckdb', read_only=True)
print(con.execute('SELECT * FROM party_ranking LIMIT 10').fetchdf())
"
```

Key tables/views: `all_questions` (both chambers, tidy, includes `question_text`
where available), `party_ranking`, `party_summary`, `ministry_summary`,
`state_summary`, the `kg_*` knowledge-graph tables, and the wide `*_matrix_wide`
cross-tabs.

## Knowledge-graph approach

Everything (MP, Party, Ministry, Topic, Question) is treated as a node in a
heterogeneous graph and every question an edge. Three analyses ride on top of
the raw counts:

1. **Signature ministries (lift)** — a party's ministry focus divided by what
   its overall share of all questions would predict, not just its biggest
   ministries by raw volume. BJP and INC, e.g., have low lift almost
   everywhere because their sheer size means they ask about *everything*
   close to proportionally; smaller and regional parties show sharp,
   interpretable spikes (e.g. IUML → Minority Affairs, BJD → Law & Justice).
2. **Party communities** — Louvain community detection on party-ministry
   *lift* vectors (not raw counts, which are dominated by every party's
   shared interest in Health/Railways/Education and collapse into one giant
   blob). Clustering on relative emphasis instead surfaces a left- and
   minority-interest bloc, a broad mainstream bloc spanning both the ruling
   party and the principal opposition, a smaller regional-development
   cluster, and outliers — see `docs/ANALYSIS.md` for the full breakdown.
3. **Ministry co-occurrence and cross-party MP bridges** — which ministries
   one MP tends to probe together (thematic linkage independent of party),
   and the rare Lok Sabha questions jointly tabled by MPs from different
   parties.

The dashboard's "Knowledge Graph" tab renders the signature-ministry network
as an interactive force-directed graph (D3); `data/processed/graph.graphml`
has the full graph for Gephi/Cytoscape.

## Known gaps

- **Lok Sabha question/answer full text isn't in this dataset.** The listing
  API used to pull all 34,720 questions only exposes the subject line — full
  text lives in a per-question PDF at a randomly-suffixed URL. OCR'ing ~34,700
  PDFs was out of scope for this pass.
- **Rajya Sabha has full question text but not answer text** — `rsdoc.nic.in`
  returns `ans_text: null` for every record; answers are PDF-only there too
  (`answer_pdf_url` in the data).
- 138 of 34,720 Lok Sabha questions (0.4%) couldn't be matched to a roster
  member by name and are excluded from party/state breakdowns —
  `data/processed/unmatched_members.csv`.
- A jointly-tabled Lok Sabha question is credited to its first-listed (lead)
  member only, to avoid one question inflating several parties' counts.
- Ministry-level is the topic granularity for the headline rankings; the
  "Topics" tab / `topic_keywords.csv` layer a lighter subject-line keyword
  extraction on top for a finer (if noisier) cut.
