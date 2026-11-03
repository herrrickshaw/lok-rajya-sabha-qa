# Lok Sabha and Rajya Sabha Parliament Questions Ledger

Who asks Parliament what. Every Lok Sabha question since the 18th Lok Sabha convened (June 2024) and every Rajya Sabha question over the matching sessions (265-271), matched to the asking MP's party and state, ranked and cross-tabbed by party, ministry, state and topic, plus a knowledge-graph layer (signature ministries, party clusters, cross-party co-signers). The question text is also checked against what ministries publish through the Press Information Bureau (PIB), PLI scheme disbursal, ministry scheme catalogues and PARIVESH environmental-clearance proposals. Outputs: processed CSVs, a DuckDB database, an Excel workbook, markdown briefs and a static HTML dashboard.

> Status: maintained research dataset. Data comes from undocumented public parliamentary JSON APIs; no licence file yet, all rights reserved. Not investment or legal advice.

**Dashboard:** https://claude.ai/artifact/P81z1Qnfur4XS2uvgMakEr · **Workbook:** `Lok_Rajya_Sabha_PQ_Analysis.xlsx` · **Database:** `data/pq_ledger.duckdb` · **Write-up:** `docs/ANALYSIS.md`, `docs/parties/<party>.md`. New to the repo? See [HOW_TO_USE_WITH_AI.md](HOW_TO_USE_WITH_AI.md).

## What it does
- Enriches 34,720 Lok Sabha and 24,661 Rajya Sabha questions with party, state and canonical ministry (`scripts/build.py`).
- Builds party x ministry, state x party, state x ministry and party x question-type matrices plus subject-line topic keywords.
- Runs five graph analyses (lift, PageRank, Louvain communities, ministry co-occurrence, cross-party MP bridges) in `scripts/build_graph.py`.
- Compares PQ scrutiny with PIB press releases, the PLI report card, MeitY/DoT/DPIIT scheme catalogues and PARIVESH proposals (`scripts/compare_*.py`).
- Loads everything into DuckDB and writes per-party briefs and `docs/ANALYSIS.md` (`scripts/build_db.py`); builds the Excel workbook and HTML dashboard.

## Quick start
```bash
git clone https://github.com/herrrickshaw/lok-rajya-sabha-qa.git
cd lok-rajya-sabha-qa
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/build.py && python scripts/build_graph.py && python scripts/build_db.py
```
The raw JSON is committed in `data/raw/`, so this offline sequence regenerates `data/processed/*.csv`, `site/data.json`, `site/graph.json`, `data/pq_ledger.duckdb` and `docs/`. The remaining steps below need extra inputs or network access.

Query the database:
```bash
python -c "
import duckdb
con = duckdb.connect('data/pq_ledger.duckdb', read_only=True)
print(con.execute('SELECT * FROM party_ranking LIMIT 10').fetchdf())
"
```
Key tables/views: `all_questions` (both chambers, tidy), `party_ranking`, `party_summary`, `ministry_summary`, `state_summary`, the `kg_*` tables and the `*_matrix_wide` cross-tabs.

## How it works
| Step | Script | Output |
|---|---|---|
| 1. Fetch raw data (one-off paginated curls, documented in the `scripts/build.py` docstring; there is no fetch script) | n/a | `data/raw/*.json` |
| 2. Enrich and aggregate | `scripts/build.py` (helpers: `pq_text.py`, `csv_io.py`) | `data/processed/*.csv`, `site/data.json` |
| 3. Knowledge graph | `scripts/build_graph.py` | `data/processed/kg_*.csv`, `graph.graphml`, `site/graph.json` |
| 4. Ministry registry (needs the external PIB index and minister directory) | `scripts/ministry_registry.py` | `data/external/ministry_registry.json` |
| 5. External comparisons (network) | `compare_pib.py`, `compare_pli.py`, `compare_wp_json_schemes.py`, `compare_parivesh.py` | `data/processed/pib_*.csv`, `pli_scheme_scrutiny.csv`, `ministry_scheme_scrutiny.csv`, `parivesh_*.csv`, `site/{pib,pli,meity,parivesh}.json` |
| 6. Dashboard | `scripts/render_site.py` | `site/index.html` (the `site/*.json` files must exist, even as `{}`) |
| 7. DuckDB and markdown | `scripts/build_db.py` | `data/pq_ledger.duckdb`, `docs/ANALYSIS.md`, `docs/parties/*.md` |
| 8. Workbook | `scripts/build_xlsx.py` | `Lok_Rajya_Sabha_PQ_Analysis.xlsx` |

Design decisions:
- **Reconciling two chambers.** LS and RS maintain their rosters independently, so party, state and ministry labels are mapped to one spelling (`SHSUBT` / `SS-UBT` become `SHS(UBT)`; `Kerala` / `Keralam`; `HOUSING AND URBAN AFFAIRS` / `Housing and Urban Affairs`). See `PARTY_ALIASES`, `STATE_ALIASES` and `canonical_ministry` in `scripts/pq_text.py`. Unmatched names go to `data/processed/unmatched_members.csv`.
- **Lift, not counts.** A party's signature ministries are its ministry share divided by what its overall share of questions predicts. BJP and INC have low lift almost everywhere because they ask about everything; smaller parties show sharp spikes (IUML to Minority Affairs, BJD to Law and Justice). Communities are clustered on lift vectors because raw counts collapse into one blob around Health, Railways and Education.
- **No scipy.** PageRank is plain power iteration in `build_graph.py`.
- **One ministry registry.** `ministry_registry.py` resolves every PQ ministry against PIB, the minister directory, the wp-json scheme sites and PARIVESH once (`build_registry()`); the `compare_*` scripts read it instead of keeping their own alias tables. It records an API `schema` per ministry because MeitY (`wp_core`) and DoT/DPIIT (`post_page`) expose different WordPress route shapes; an earlier assumption that they matched was wrong.
- **Pure core, I/O at the edge.** The aggregation and graph functions take rows and return rows; `main()` in each script takes input and output directories, which the tests use.

## Headline findings
Full tables are in `docs/ANALYSIS.md` and the matching CSVs.
- **PQs per PIB release.** External Affairs shows the highest ratio (513x) but this is a gap in the sibling PIB index (2 releases), not a real signal; Defence is the lowest (0.08x).
- **Schemes.** Samagra Shiksha Abhiyan, PM-SGMBY and PM-SHRI draw PQ scrutiny with no matching PIB headline; Jal Jeevan Mission, PM-KISAN and PMAY show up in both.
- **PLI.** ACC Battery Storage (grade F, Rs 18,100 cr outlay, 0% disbursed) has only 11 PQ mentions; White Goods (B-, 4.5% disbursed) has 2; Bulk Drugs (B, 0.8% disbursed on Rs 6,940 cr) has 34, the most in the table.
- **Scheme catalogues.** 19 of 44 MeitY/DoT/DPIIT schemes (22 / 9 / 13) are never named in a PQ; 15 of 44, all MeitY, have not been touched on the ministry's own CMS for over a year.
- **PARIVESH.** Gujarat (897 EC proposals) and Maharashtra (699) have the lowest PQ-per-proposal ratios (0.08x, 0.26x); none of the 25 largest proposals with a named applicant is named in any PQ.

## Repository layout
| Path | Purpose |
|---|---|
| `scripts/build.py`, `build_graph.py`, `build_db.py` | Core pipeline (refactored: pure functions plus a thin `main()`) |
| `scripts/pq_text.py`, `scripts/csv_io.py` | Shared name normalisers and CSV helpers |
| `scripts/ministry_registry.py`, `compare_*.py` | External-source joins (still monolithic) |
| `scripts/build_xlsx.py`, `render_site.py` | Workbook and dashboard |
| `data/raw/` | Committed raw API pulls (and cached live fetches) |
| `data/processed/` | Generated CSVs and `graph.graphml` |
| `data/external/` | `pli_report_card.json` (21 KB snapshot) and the generated ministry registry |
| `docs/`, `site/` | Generated markdown briefs and the dashboard |
| `tests/` | pytest suite with offline fixtures (`tests/fixtures/raw`, `tests/fixtures/golden`) |

## Data sources
| Source | What is taken | Access | Caveat |
|---|---|---|---|
| `sansad.in` `api_ls` | 34,720 18th-LS questions: subject, ministry, members, type, date, session | Undocumented JSON API found in the Next.js bundle | No question or answer text, only a per-question PDF |
| `sansad.in` `api_ls` / `api_rs` member endpoints | Current and former rosters: party, state, constituency | Undocumented JSON API | |
| `rsdoc.nic.in` `Question/Search_Questions` | 24,661 RS questions, sessions 265-271, with full question text | Parametrised-SQL `whereclause` query parameter | `ans_text` is null everywhere; answers are PDF-only |
| PIB press-release index | 124,857 releases 2017-present | External: built in `india-trade-sector-policy-recommendations` (`scripts/pib_index.py`), read by local path | Not reproducible without that index |
| PLI report card | 13 PLI sub-schemes graded A-F | `data/external/pli_report_card.json`, copied from the same sibling repo | Grades are that repo's own judgment |
| MeitY/DoT/DPIIT scheme catalogues | 44 schemes | Live public WordPress-backed APIs, cached in `data/raw/wp_json_schemes.json` | Undocumented; two API shapes |
| PARIVESH `getProposals` | 4,762 Environmental Clearance proposals | Live no-auth endpoint, cached in `data/raw/parivesh_proposals.json` | EC only; `status=Received\|Granted` is a no-op, empty dates return HTTP 500 |
| Minister directory | Minister per ministry | External: `india-govt-yellow-pages/data/pib_ministry_contacts.csv`, read by local path | Point-in-time snapshot |

Rules for a Parliament Question (notice rules, starred vs unstarred) were cross-checked against [Drishti IAS](https://www.drishtiias.com/daily-news-analysis/questioning-in-parliament), used only as a secondary reference, not as data.

## Configuration
No environment variables or secrets. `scripts/ministry_registry.py` holds two machine-specific absolute paths (`PIB_DB`, `MINISTER_CONTACTS_CSV`) to sibling repos; adjust them to reproduce step 4 elsewhere. Scripts can be run from any directory; they write relative to the repo root.

## Testing
```bash
pytest -q
ruff check scripts tests
```
The golden tests run `build.py` and `build_graph.py` on a tiny offline fixture and compare byte-for-byte with output produced by the pre-refactor scripts. No test touches the network.

## Limitations and known issues
- Lok Sabha question and answer full text is not in the dataset (PDF-only, about 34,700 files not fetched). Rajya Sabha has question text but no answer text.
- 138 of 34,720 LS questions (0.4%) could not be matched to a roster member and are excluded from party and state breakdowns.
- A joint LS question is credited to its first-listed member only.
- PIB matching uses release titles only, a floor on coverage; External Affairs' PIB count is a data gap.
- Minister-in-charge is a snapshot; 4 of 56 ministries have no matched minister.
- PLI mention counts are keyword patterns (lower bounds). Scheme matching for MeitY/DoT/DPIIT is auto-derived and the two "PLI for IT Hardware" entries get identical counts.
- `months_since_update` measures CMS activity, not whether a scheme is live.
- The wp-json and PARIVESH steps fetch live on every run and need re-verification if an endpoint changes shape.
- PARIVESH company extraction is a "by [M/s] Company" pattern, not NER.
- Surveyed but not wired in: NITI Aayog ICED (`NITI_ICED_MINISTRIES` hook) and per-company PLI beneficiary rosters.
- `data/pq_ledger.duckdb` is tracked although `.gitignore` lists it.

## Related repositories
- `india-trade-sector-policy-recommendations`: source of the PIB index and PLI report card.
- `india-govt-yellow-pages`: source of the minister directory.

## Licence
No licence file yet; all rights reserved.
