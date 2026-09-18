# Lok & Rajya Sabha — Parliament Questions Ledger

Who asks Parliament what. Every Lok Sabha question since the 18th Lok Sabha convened
(June 2024) and every Rajya Sabha question over the matching sessions (265–271),
matched to the asking MP's party and state, ranked and cross-tabbed by party,
ministry, state and topic — plus a knowledge-graph layer on top that surfaces
each party's *signature* ministries, which parties cluster together by what they
ask about, and the rare MPs who co-sign questions across party lines.

A further layer treats the question text itself as a data source rather than
just something to count, and checks it against what ministries proactively
publish through the Press Information Bureau over the same window — which
ministries and named schemes draw heavy parliamentary scrutiny relative to how
much they self-publicize, and where the two barely overlap.

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
| PIB (Press Information Bureau) press-release index | 124,857 releases, 2017–present, by ministry, refreshed to match this dataset's window (June 2024–present) | **External** — built for a separate project (`india-trade-sector-policy-recommendations/scripts/pib_index.py`), not part of this repo's own fetch scripts. `scripts/ministry_registry.py` reads that project's `data/pib_index.sqlite` by local path; anyone reproducing this outside that environment needs an equivalent PIB index (see that script's docstring for the release-listing endpoint it scrapes) |
| PLI disbursal report card | 13 PLI sub-schemes graded A–F on incentive disbursal, PIB-sourced | **Included** — `data/external/pli_report_card.json`, a copied 21KB snapshot from the same sibling project (small enough to ship directly, unlike the PIB index) |
| MeitY/DoT/DPIIT scheme catalogues | 44 schemes across 3 ministries: description, launch/approval narrative, last-modified date | **Live-fetched** — public WordPress-backed APIs behind each ministry's JS-shell site (undocumented; two different API shapes, verified independently per site — see the architecture note below), fetched fresh by `scripts/compare_wp_json_schemes.py` on every run, cached to `data/raw/wp_json_schemes.json` as a fallback if a live fetch fails |
| PARIVESH environmental clearances | 4,762 Environmental Clearance proposals in this window: project/company name, state, investment cost, approval-stage status | **Live-fetched** — an open, no-auth bulk endpoint on PARIVESH's public MIS dashboard (undocumented), fetched fresh by `scripts/compare_parivesh.py` on every run, cached to `data/raw/parivesh_proposals.json` as a fallback |
| Ministry-official directory (minister-in-charge) | Current minister/designation per ministry | **External** — `india-govt-yellow-pages/data/pib_ministry_contacts.csv`, read by local path in `scripts/ministry_registry.py`; not copied in (it's a live-updated scrape, a snapshot would go stale) |

### Architecture: one ministry registry, not one join per script

`compare_pib.py` and `compare_pli.py` each started out independently
matching ministry names against PIB and igod — the same shape of problem
that pushed Netflix's client-facing API from direct per-service calls
towards a single aggregation layer (see ByteByteGo, ["Evolution of the
Netflix API Architecture"](https://bytebytego.com/guides/evolution-of-the-netflix-api-architecture/):
monolith → direct access → gateway aggregation layer → federated gateway —
each stage exists because *N* callers independently re-deriving the same
join stops scaling). `scripts/ministry_registry.py` is the data-pipeline
equivalent: it resolves every PQ ministry's identity against every wired
external source exactly once (`build_registry()`), writes the result to
`data/external/ministry_registry.json`, and every consumer — `compare_pib.py`
for the PIB/minister join, `compare_pli.py` for the PLI-scheme minister
lookup, and `compare_wp_json_schemes.py`, which reads MeitY/DoT/DPIIT's
wp-json endpoint URLs and API shapes straight from `WP_JSON_MINISTRIES`
instead of hardcoding them — all read the registry instead of re-deriving
their own `normalize()`/alias tables.

**Verify, don't extrapolate, across ministries on the same platform.**
`WP_JSON_MINISTRIES` originally assumed DoT and DPIIT would expose the same
API shape as MeitY (same CMS vendor, same "wp-json" label) — wrong. Live
verification found MeitY uses the standard WP REST route
(`wp/v2/schemes_and_services`, `?per_page=N`, a bare JSON array) while DoT
and DPIIT use a different, non-standard "post-page" route
(`post-page/schemes_and_services`, `?limit=N&page=N&orderby=menu_order`,
a `{"posts": [...]}` wrapper, snake_case fields). The registry now records a
`schema` per ministry (`"wp_core"` vs `"post_page"`) and
`compare_wp_json_schemes.py` dispatches on it, so the two shapes are handled
by two small adapter functions instead of either crashing on the assumption
or silently returning wrong data.

`compare_parivesh.py` also reads its target ministry from
`PARIVESH_MINISTRIES` rather than hardcoding it. `NITI_ICED_MINISTRIES`
remains an integration *hook*, not yet wired up, for the same reason the
others existed before their scripts did — so a future pass reads it here
rather than rediscovering the mapping.

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

# 4. Build the ministry registry (needs the external PIB index + minister
#    directory, see the Data sources table — skip if you don't have them;
#    compare_pib.py/compare_pli.py call this automatically if it's missing,
#    but running it explicitly first is clearer)
python3 scripts/ministry_registry.py   # -> data/external/ministry_registry.json

# 5. Compare against PIB press releases, the PLI disbursal report card,
#    MeitY/DoT/DPIIT's own scheme catalogues, and PARIVESH environmental
#    clearances (needs network access -- fetches live)
#    (site/pib.json / site/pli.json / site/meity.json / site/parivesh.json
#    just need to exist, even as {}, for the next step to render if you
#    skip any of these)
python3 scripts/compare_pib.py    # -> data/processed/pib_*.csv, site/pib.json
python3 scripts/compare_pli.py    # -> data/processed/pli_scheme_scrutiny.csv, site/pli.json
python3 scripts/compare_wp_json_schemes.py  # -> data/processed/ministry_scheme_scrutiny.csv, site/meity.json
python3 scripts/compare_parivesh.py  # -> data/processed/parivesh_*.csv, site/parivesh.json

# 6. Render the dashboard
python3 scripts/render_site.py    # -> site/index.html

# 7. Load everything into DuckDB + write markdown summaries
python3 scripts/build_db.py       # -> data/pq_ledger.duckdb, docs/ANALYSIS.md, docs/parties/*.md

# 8. Build the Excel workbook
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

## Questions vs. press releases (vs. PIB)

The dashboard's "vs. PIB" tab and `data/processed/pib_*.csv` compare the PQ
corpus — treated as real text, not just metadata rows — against PIB (Press
Information Bureau) press releases from the same window:

- **Ministry level**: PQ questions per PIB release, plus the current
  minister-in-charge (joined from `india-govt-yellow-pages`'s igod.gov.in
  who's-who scrape) — completing the accountability chain this repo already
  draws (Party → MP → Question → Ministry) one link further, to the minister
  actually on the hook for an answer. External Affairs draws by far the most
  PQ scrutiny relative to its PIB output (513x) — though see the caveat
  below; Defence is the opposite extreme (0.08x — heavily self-publicized,
  comparatively little formal questioning).
- **Named scheme/programme level**: scheme names extracted from PQ subject
  lines / full question text, checked against PIB release *titles* in the
  same window — which schemes get parliamentary scrutiny with essentially no
  matching PIB headline (Samagra Shiksha Abhiyan, PM-SGMBY, PM-SHRI…) versus
  which show up heavily in both (Jal Jeevan Mission, PM-KISAN, PMAY).

Full tables: `docs/ANALYSIS.md`, `pib_ministry_comparison.csv` /
`pib_scheme_comparison.csv`, or the `pib_ministry_comparison` /
`pib_scheme_comparison` DuckDB tables.

### PLI scheme scrutiny vs. actual disbursal

Integrated a separate, already-built research asset — a PIB-sourced report
card (`data/external/pli_report_card.json`, from
`india-trade-sector-policy-recommendations`, copied in 21KB and small enough
to ship directly rather than reference externally) grading all 13 Production
Linked Incentive sub-schemes A–F on whether the government's own incentive
money is *actually flowing*, not just approved, every claim traced to a PIB
release ID — joined against how often each scheme is specifically named in
PQ text (`scripts/compare_pli.py`, keyword patterns per scheme).

The two worst grades aren't the two most-scrutinised: **PLI ACC Battery
Storage (F, ₹18,100cr outlay, 0% disbursed) draws only 11 PQ mentions**, and
**PLI White Goods (B-, 4.5% disbursed) draws just 2** — both plausibly flying
under the radar relative to the scale of their shortfall. PLI Bulk Drugs (B
grade, but only 0.8% disbursed on ₹6,940cr) is the most-scrutinised scheme in
the table (34 mentions) — a live China-dependency flashpoint independent of
its own grade. Full table: `data/processed/pli_scheme_scrutiny.csv`,
`docs/ANALYSIS.md`, or the dashboard's "vs. PIB" tab.

### Ministry scheme catalogues vs. PQ scrutiny and staleness

MeitY, DoT and DPIIT all run Next.js shell sites with no crawlable page
content, but each serves its scheme catalogue underneath through a public
WordPress-backed API (`scripts/compare_wp_json_schemes.py`, endpoints and
API shapes declared in `ministry_registry.py`'s `WP_JSON_MINISTRIES`,
cached to `data/raw/wp_json_schemes.json`) — 44 schemes total (22 MeitY, 9
DoT, 13 DPIIT), each with a description and a last-modified timestamp,
matched against PQ text by each scheme's parenthetical acronym (only when
it's scheme-specific — "PLI" alone is rejected as too generic, it names a
whole cross-ministry program) or its distinguishing title words.

**19 of 44 schemes across the three ministries draw zero PQ mentions by
name** in this window — including MeitY's SPECS (electronics-component/
semiconductor manufacturing promotion) and the Large Scale Electronics
Manufacturing component of the PLI program, both verified genuinely zero
against the raw corpus, not a matching artifact. **15 of 44 (all MeitY's)
haven't been touched on their ministry's own CMS in over a year**,
operationalizing what the ministry-site-access research had only asserted
qualitatively (frozen, present-tense scheme pages) — DoT's and DPIIT's
catalogues were bulk-refreshed recently, MeitY's largely wasn't. Full
table: `data/processed/ministry_scheme_scrutiny.csv`, `docs/ANALYSIS.md`,
or the dashboard's "vs. PIB" tab (with a ministry filter).

### PARIVESH environmental clearances vs. PQ scrutiny, by state

PARIVESH's public MIS dashboard has an open, no-auth bulk endpoint
(`admin_api/dashboard/getProposals`, `scripts/compare_parivesh.py`) that
returns every Environmental Clearance (EC) proposal in a date window —
project/company name, state, investment cost, and a granular approval-stage
`status`. Two things the source research got wrong or hadn't checked,
verified live rather than trusted: the documented `status=Received|Granted`
query parameter is a **no-op** — both values return byte-identical
responses (confirmed by MD5) — so granted-vs-not is classified from each
proposal's own `status` field instead (19 distinct values: "EC Granted",
"Under Examination", "Proposal pulled back (withdrawn)", etc.); an empty
`fromDate`/`toDate` now **500s**, where the documented example omitted them.

**By state**, reusing `state_ministry_matrix.csv` (already built, no new
matching needed): Gujarat (897 EC proposals) and Maharashtra (699) dominate
clearance volume but sit at the *low* end of PQ-per-proposal (0.08x, 0.26x)
— high regulatory activity, proportionally less parliamentary follow-up per
proposal than smaller states draw. Full table:
`data/processed/parivesh_state_comparison.csv`.

**The 25 largest EC proposals by investment**, checked for whether the
applicant company (extracted from a "by [M/s] Company" clause in the
proposal title, where one exists) is named anywhere in PQ text: **none of
them are** — Adani Power, APSEZ, the Dholera investment region authority,
Vedanta Aluminium, DVC-CIL, Evonith Metallics. Individual mega-project
scrutiny by company name appears essentially absent, unlike how PLI scheme
beneficiaries surface in PQ text. Full table:
`data/processed/parivesh_mega_projects.csv`.

**Comparable data sources surveyed but not (yet) integrated**: NITI Aayog's
India Climate & Energy Dashboard (`iced.niti.gov.in`, AES-encrypted API) has
official coal/energy/GHG series for Coal- and Environment-ministry PQ
fact-checking; and a prior PLI *company-name* harvest (as opposed to the
scheme-grade report card integrated above) has verified per-beneficiary
rosters (Tata Electronics, Foxconn, individual PLI-Auto/Pharma/Textiles
applicants, etc.) that could name the actual companies behind each scheme's
PQ mentions — not pulled in here since it exists only as prose in a past
session's now-gone scratchpad, not a structured file. Neither is wired in —
a menu for a follow-up pass, not a claim that this repo uses them.

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
- **The PIB comparison's External Affairs count (2 releases since June 2024)
  is a data gap in the sibling index, not reality** — MEA is one of PIB's
  most active posters; that index under-captures MEA specifically across its
  whole 2017–present history, not just this window.
- **Scheme-vs-PIB matching is release-title text only**, a floor on PIB
  coverage not a ceiling — acronym-heavy PQ terms (PM-SGMBY, PM-SHRI) likely
  appear in PIB headlines spelled out differently.
- **Minister-in-charge is a point-in-time snapshot from a sibling repo's
  scrape** (`india-govt-yellow-pages`), not refreshed by anything in this
  repo — a reshuffle after that scrape won't be reflected here. 4 of 56
  ministries have no matched minister row.
- **PLI `scheme_pq_mentions` is a keyword-pattern count, not a verified
  extraction** — a PQ about a scheme that doesn't use one of the matched
  phrases is missed; treat these as a lower bound. Grades/outlay/disbursal
  figures are `india-trade-sector-policy-recommendations`'s own PIB-sourced
  judgment (methodology stated in the report card), not independently
  re-verified in this repo.
- **MeitY/DoT/DPIIT scheme matching is auto-derived per scheme** (acronym if
  genuinely scheme-specific — a bare "PLI" is rejected as naming a whole
  cross-ministry program, not one scheme — else the title's distinguishing
  words), not hand-curated like the PLI table; lower precision. The two
  "PLI for IT Hardware" entries (1.0 and 2.0) get identical counts because
  PQ text can't be told which version it means — a real ambiguity in the
  source data, not a bug. `months_since_update` measures each ministry's CMS
  activity, not whether the scheme itself is still active.
- **DoT and DPIIT use a different, undocumented "post-page" API route from
  MeitY's standard WP REST route** — verified live per site rather than
  assumed to match (an earlier version of this hook wrongly assumed they
  would). If either site's API changes shape again,
  `compare_wp_json_schemes.py` needs re-verifying against the live site, not
  just a retry.
- **These three ministries fetch live over the network on every run** — no
  offline reproducibility guarantee if an endpoint changes shape or goes
  down; `data/raw/wp_json_schemes.json` is the cached fallback from this
  run.
- **PARIVESH covers Environmental Clearance (EC) only** — every record
  returned by `getProposals` had `workgroup_name: "Environmental
  Clearance"`; Forest Clearance (FC) proposals, if they exist on a
  different route, aren't included here.
- **PARIVESH mega-project company extraction is a "by [M/s] Company"
  pattern match, not NER** — titles that name no company, or lead with the
  company instead of trailing it, come back with no company and are
  excluded from the mention check rather than falsely counted as
  unmentioned.
- **PARIVESH also fetches live** — cached fallback is
  `data/raw/parivesh_proposals.json`.
