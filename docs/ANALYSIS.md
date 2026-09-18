# Parliament Questions, 18th Lok Sabha term — analysis

Source data: `sansad.in` (`api_ls`) for Lok Sabha, `rsdoc.nic.in` for Rajya Sabha (sessions 265-271, the sessions covering the same period as the 18th Lok Sabha), both chambers' member rosters for party/state attribution. Full methodology in the repository README.

## What a Parliament Question actually is

Per Rules 32-54 of the Lok Sabha's Rules of Procedure (Rules 47-50 in the Rajya Sabha), an MP files a notice — max 150 words, no policy-level or sub-judice matters, no more than 5 notices a day — at least 15 days ahead (10 for a short-notice question). The Speaker/Chairman rules on admissibility. A **starred** question gets an oral answer and allows follow-up supplementaries on the floor, capped at one per MP per sitting day; an **unstarred** question gets only a written reply tabled on the record. (Source: Drishti IAS, "Questioning in Parliament", drishtiias.com — a standard UPSC-prep civics reference, used here only to confirm procedural definitions against a reliable secondary source, not as a data source.)

## Top parties by total questions

| Rank | Party | Lok Sabha | Rajya Sabha | Total |
|---:|---|---:|---:|---:|
| 1 | BJP | 11,755 | 11,126 | 22,881 |
| 2 | INC | 7,921 | 3,263 | 11,184 |
| 3 | DMK | 2,299 | 1,238 | 3,537 |
| 4 | AITC | 1,503 | 1,041 | 2,544 |
| 5 | SP | 1,959 | 372 | 2,331 |
| 6 | TDP | 1,830 | 348 | 2,178 |
| 7 | YSRCP | 494 | 777 | 1,271 |
| 8 | SS | 1,007 | 125 | 1,132 |
| 9 | CPI(M) | 455 | 647 | 1,102 |
| 10 | BJD | 0 | 1,019 | 1,019 |
| 11 | JD(U) | 851 | 167 | 1,018 |
| 12 | IND. | 448 | 523 | 971 |
| 13 | AAP | 210 | 580 | 790 |
| 14 | NCP(SP) | 525 | 179 | 704 |
| 15 | AIADMK | 0 | 697 | 697 |

## Top ministries by questions received

| Ministry | Questions |
|---|---:|
| HEALTH AND FAMILY WELFARE | 3,550 |
| RAILWAYS | 2,900 |
| EDUCATION | 2,802 |
| AGRICULTURE AND FARMERS WELFARE | 2,754 |
| FINANCE | 2,253 |
| CIVIL AVIATION | 2,129 |
| ROAD TRANSPORT AND HIGHWAYS | 2,061 |
| JAL SHAKTI | 1,997 |
| HOUSING AND URBAN AFFAIRS | 1,823 |
| ENVIRONMENT, FOREST AND CLIMATE CHANGE | 1,809 |
| LABOUR AND EMPLOYMENT | 1,570 |
| RURAL DEVELOPMENT | 1,389 |
| COMMERCE AND INDUSTRY | 1,356 |
| CONSUMER AFFAIRS, FOOD AND PUBLIC DISTRIBUTION | 1,332 |
| WOMEN AND CHILD DEVELOPMENT | 1,271 |

## Top states by their MPs' question volume

| State/UT | Questions |
|---|---:|
| Uttar Pradesh | 6,514 |
| Tamil Nadu | 6,031 |
| Maharashtra | 5,703 |
| Andhra Pradesh | 4,072 |
| Kerala | 3,722 |
| West Bengal | 3,549 |
| Bihar | 3,412 |
| Rajasthan | 3,224 |
| Odisha | 2,717 |
| Karnataka | 2,693 |
| Gujarat | 2,248 |
| Punjab | 2,000 |
| Madhya Pradesh | 1,991 |
| Telangana | 1,917 |
| Jharkhand | 1,540 |

## Knowledge-graph findings

The flat rankings above answer "who asks the most" and "about what, in aggregate". Building a heterogeneous graph (MP / Party / Ministry / Topic nodes, weighted question-count edges) and running standard graph analyses on it answers three questions the pivot tables can't:

**1. Which ministries are a party's genuine signature** — not just its biggest by raw count, but where it asks disproportionately more than its overall share of questions would predict ("lift"). See each party's brief in `docs/parties/` for its own list, or `data/processed/kg_party_ministry_lift.csv` for all of them.

**2. Which parties cluster together by what they ask about**, independent of size or stated ideology — Louvain community detection on party-ministry lift vectors (not raw counts, which are swamped by every party's shared interest in Health/Railways/Education) finds:

- **Community 1** (18 parties, a left- and minority-interest bloc): AIMIM, AITC, AJSU, ASP (KR), BAP, CPI, CPI(M), CPI(ML)(L), IUML, J&KNC, JMM, LJSP(RV), PMK, RJD, RLM, RLP, SAD, SP
- **Community 2** (4 parties, a broad mainstream bloc containing both the ruling party and the principal opposition): AGP, SKM, UPPL, Unknown
- **Community 3** (23 parties, a smaller regional-development cluster): AAP, AIADMK, BJD, BJP, DMK, INC, IND., JD(S), JD(U), JSP, KC(M), KEC, MDMK, NCP, NCP(SP), NOM., RLD, RSP, SHS(UBT), SS, TDP, VCK, YSRCP
- **Community 4** (1 parties, outlier(s) whose profile doesn't resemble any cluster closely enough): BRS

**3. Where MPs cross party lines** — Lok Sabha questions are occasionally tabled jointly by several MPs; a handful of those pairings cross party lines. Top cross-party co-asking pairs:

| MP | Party | MP | Party | Joint questions |
|---|---|---|---|---:|
| Shri Dhairyasheel Sambhajirao Mane | SS | Shri Sudheer Gupta | BJP | 207 |
| Prof. Varsha Eknath Gaikwad | INC | Smt. Supriya Sule | NCP(SP) | 206 |
| Prof. Varsha Eknath Gaikwad | INC | Shri Sanjay Dina Patil | SS | 205 |
| Shri Shrirang Appa Chandu Barne | SS | Smt. Bharti Pardhi | BJP | 204 |
| Prof. Varsha Eknath Gaikwad | INC | Shri Mohite Patil Dhairyasheel Rajsinh | NCP(SP) | 200 |
| Dr. Amol Ramsing Kolhe | NCP(SP) | Prof. Varsha Eknath Gaikwad | INC | 199 |
| Prof. Varsha Eknath Gaikwad | INC | Shri Bhaskar Murlidhar Bhagare | NCP(SP) | 193 |
| Shri Sanjay Dina Patil | SS | Smt. Supriya Sule | NCP(SP) | 181 |
| Shri Mohite Patil Dhairyasheel Rajsinh | NCP(SP) | Shri Sanjay Dina Patil | SS | 179 |
| Dr. Amol Ramsing Kolhe | NCP(SP) | Shri Sanjay Dina Patil | SS | 178 |

## Parliament questions as a text source, cross-checked against PIB

Treating the PQ corpus as real text (not just metadata rows) rather than only counting it opens a
direct comparison against what ministries proactively publish through the Press Information Bureau
over the same window (June 2024 – present, PIB index refreshed to match). Two cuts:

**Ministry level — PQ questions per PIB release.** A high ratio means a ministry draws a lot of
parliamentary scrutiny relative to how much it self-publicizes; a low ratio means the opposite —
heavy self-promotion, comparatively little PQ pressure.

| Ministry | PQ questions | PIB releases | PQ per PIB release |
|---|---:|---:|---:|
| EXTERNAL AFFAIRS | 1,026 | 2 | 513.0x |
| CIVIL AVIATION | 2,129 | 188 | 11.3x |
| HOUSING AND URBAN AFFAIRS | 1,823 | 303 | 6.0x |
| EDUCATION | 2,802 | 506 | 5.5x |
| RAILWAYS | 2,900 | 570 | 5.1x |
| PETROLEUM AND NATURAL GAS | 1,138 | 257 | 4.4x |
| HEALTH AND FAMILY WELFARE | 3,550 | 809 | 4.4x |
| ROAD TRANSPORT AND HIGHWAYS | 2,061 | 471 | 4.4x |

*(most self-publicized relative to PQ scrutiny — low end of the same ratio)*

| Ministry | PQ questions | PIB releases | PQ per PIB release |
|---|---:|---:|---:|
| DEFENCE | 186 | 2234 | 0.08x |
| SCIENCE AND TECHNOLOGY | 430 | 1418 | 0.30x |
| PERSONNEL, PUBLIC GRIEVANCES AND PENSIONS | 305 | 808 | 0.38x |
| INFORMATION AND BROADCASTING | 465 | 974 | 0.48x |
| PARLIAMENTARY AFFAIRS | 67 | 139 | 0.48x |
| STATISTICS AND PROGRAMME IMPLEMENTATION | 314 | 480 | 0.65x |
| HOME AFFAIRS | 1,051 | 1147 | 0.92x |
| STEEL | 334 | 349 | 0.96x |

*Note: External Affairs' near-zero PIB count (2 releases) is a known gap in the underlying PIB index
for that ministry specifically, not a real signal — see caveats below.*

**Named scheme/programme level.** Scheme and programme names extracted directly from PQ subject
lines and (for Rajya Sabha) full question text via pattern-matching (`Pradhan Mantri ... Yojana`,
`... Mission`, `... Abhiyan`, `PM-<X>` acronyms), then checked for whether that exact term also
appears in a PIB release *title* in the same window:

| Scheme/programme (from PQ text) | PQ mentions | PIB release-title mentions |
|---|---:|---:|
| Jal Jeevan Mission | 376 | 68 |
| PMAY-U | 315 | 14 |
| Pradhan Mantri Awas Yojana | 303 | 19 |
| PMAY-G | 249 | 32 |
| PM-KISAN | 206 | 37 |
| Pradhan Mantri Jan Arogya Yojana | 191 | 8 |
| Pradhan Mantri Kaushal Vikas Yojana | 188 | 9 |
| Pradhan Mantri Fasal Bima Yojana | 182 | 13 |
| National Mission | 175 | 56 |
| Smart Cities Mission | 164 | 8 |
| PM-KUSUM | 155 | 7 |
| Pradhan Mantri Gram Sadak Yojana | 152 | 13 |

*PQ-scrutinised terms with no matching PIB release title in the same window:*

- Samagra Shiksha Abhiyan (81 PQ mentions)
- PM-SGMBY (65 PQ mentions)
- PM-SHRI (60 PQ mentions)
- Atal Mission (27 PQ mentions)
- PM-SVANidhi (26 PQ mentions)
- Pradhan Mantri Swasthya Suraksha Yojana (24 PQ mentions)
- Pradhan Mantri Gramin Sadak Yojana (24 PQ mentions)
- Nagar Van Yojana (20 PQ mentions)

This is a **title-text match, not a content match** — a PIB release can genuinely cover a scheme
without using its exact name (or using a different abbreviation) in the headline, so the PQ-only
list above is a floor, not proof of zero coverage. Several of these (PM-SGMBY, PM-SHRI) are
abbreviations PQ text uses that PIB's own headlines likely spell out differently — check
`data/processed/pib_scheme_comparison.csv` and the full-text PDF before citing a specific scheme as
uncovered.

## PLI schemes — scrutiny vs. actual disbursal

A separate PIB-sourced research asset (`india-trade-sector-policy-recommendations`,
copied into `data/external/pli_report_card.json`, retrieved 2026-07-19, grades and figures
are that repo's own judgment, not re-verified here) grades all 13 Production Linked
Incentive sub-schemes A–F on whether the government's own incentive money is actually
flowing, not just approved. Joined against how often PQ text specifically names each
scheme (`scripts/compare_pli.py`, keyword patterns per scheme — a conservative undercount):

| Grade | Scheme | Minister-in-charge | PQ mentions | Outlay (₹cr) | Disbursed |
|---|---|---|---:|---:|---:|
| A | PLI Pharmaceuticals (formulations) | Shri Jagat Prakash Nadda | 7 | 15000 | 36.2% |
| A- | Electronics (LSEM + IT Hardware) | — | 9 | 11324 | 137.3% |
| B | PLI Bulk Drugs (KSMs/APIs) | Shri Jagat Prakash Nadda | 34 | 6940 | 0.8% |
| B | PLI Medical Devices | Shri Jagat Prakash Nadda | 5 | 3420 | 4.6% |
| B | PLI Food Processing | Shri Chirag Paswan | 29 | 10900 | 9.9% |
| B | PLI Telecom & Networking | Shri Jyotiraditya M. Scindia | 11 | 12195 | 9.6% |
| B- | PLI White Goods (ACs & LEDs) | Shri Piyush Goyal | 2 | 6238 | 4.5% |
| B- | PLI Solar PV Modules | Shri Pralhad Joshi | 20 | 24000 | 0.0% |
| C+ | PLI Drones | Shri Kinjarapu Rammohan Naidu | 9 | 120 | 25.0% |
| D+ | PLI Automobile & Auto Components | Shri H. D. Kumaraswamy | 28 | 25938 | 9.2% |
| D | PLI Specialty Steel | Shri H. D. Kumaraswamy | 14 | 6322 | 0.8% |
| D | PLI Textiles (MMF/technical) | Shri Giriraj Singh | 17 | 10683 | 0.5% |
| F | PLI ACC Battery Storage | Shri H. D. Kumaraswamy | 11 | 18100 | 0.0% |

The two worst grades (D and F) are not the two most heavily questioned — **PLI ACC Battery
Storage (F, ₹18,100cr outlay, 0% disbursed) draws only 11 PQ mentions**, and **PLI White
Goods (B-, only 4.5% disbursed) draws just 2** — both plausibly flying under the radar
relative to the scale of the shortfall. PLI Bulk Drugs (B grade but only 0.8% disbursed on
₹6,940cr) is the most-scrutinised scheme in the table (34 mentions), consistent with it
being a live China-dependency policy flashpoint independent of its own disbursal grade.

## MeitY's own scheme catalogue vs. PQ scrutiny

MeitY runs a JS-shell site with no crawlable page content, but its scheme content is
served underneath by a public WordPress REST API
(`https://www.meity.gov.in/cms/wp-json/wp/v2/schemes_and_services`, `scripts/compare_meity.py`)
— the first of the surveyed-but-unintegrated ministry-website sources actually wired in.
22 schemes, matched against PQ text by acronym or distinguishing title words (heuristic,
a lower bound — see caveats):

| Scheme | PQ mentions | Months since MeitY update | Outlay mentioned (₹cr) |
|---|---:|---:|---:|
| Production Linked Incentive Scheme – PLI 2.0 for IT Hardware | 9 | 3.9 | — |
| Production Linked Incentive Scheme (PLI) for IT Hardware | 9 | 3.9 | — |
| Electronic Manufacturing Clusters (EMC) Scheme | 8 | 3.5 | 50.0 |
| Electronics Component Manufacturing Scheme | 7 | 13.6 | — |
| Modified Electronics Manufacturing Clusters (EMC 2.0) Scheme | 4 | 7.2 | — |
| Modified Special Incentive Package Scheme (M-SIPS) | 4 | 15.3 | — |
| Digital India Internship Scheme 2026 | 4 | 5.3 | — |
| TECHNICAL INTERNSHIP PROGRAMME 2025 | 4 | 15.3 | — |
| CSC Scheme 2.0 – A Way Forward [ Part of e-Governance Division] | 3 | 15.3 | — |
| BPO promotion Schemes | 3 | 15.3 | 543.0 |
| Scheme for Financial Assistance to select States/UTs for Skill Development in Electronics System Design and Manufacturing (ESDM) sector | 3 | 15.3 | 113.77 |
| GEN-NEXT Support for Innovative Startups (GENESIS) | 2 | 15.3 | 490.0 |
| Visvesvaraya PhD Scheme | 2 | 4.0 | 481.93 |
| Technology Incubation and Development of Entrepreneurs | 0 | 15.3 | — |
| Scheme for Promotion of Manufacturing of Electronic Components and Semiconductors (SPECS) | 0 | 15.3 | — |

**9 of 22 MeitY schemes draw zero PQ mentions by name** in this window
— including SPECS (semiconductor/electronics-component manufacturing promotion) and the
Large Scale Electronics Manufacturing component of the PLI program, both genuinely verified
zero (not a matching artifact — checked directly against the raw corpus). Either PQs about
these use language this heuristic doesn't catch, or they draw essentially no
scheme-specific parliamentary attention. **15 of 22** haven't been
touched on MeitY's own site in over a year — a smaller staleness signal than the
ministry-site-access memory's prior finding of frozen, present-tense scheme pages, but the
same phenomenon.

## Known gaps

- **Lok Sabha question/answer full text is not in this dataset.** The `api_ls` listing endpoint used to fetch all 34,720 LS questions only exposes the subject line, not the question or answer body — those live only in per-question PDFs (a different URL per question, with a random filename suffix on the 18th LS). Fetching and OCR'ing ~34,700 PDFs was out of scope for this pass; `docs/parties/*.md` and the topic tab work from subject-line text only for the Lok Sabha side.
- **Rajya Sabha has full question text** (`question_text` in `rs_questions` / `all_questions`) but **not answer text** — `rsdoc.nic.in` returns `ans_text: null` for every record; answers are PDF-only there too (`answer_pdf_url`).
- 138 of 34,720 Lok Sabha questions (0.4%) could not be matched to a roster member by name (honorific variants and, in a couple of cases, MPs who left office without a public former-member record) and are excluded from party/state breakdowns.
- Party attribution for a jointly-tabled Lok Sabha question uses the first-listed (lead) member only, to avoid one question inflating multiple parties' counts.
- **The PIB comparison's Ministry of External Affairs count (2 releases since June 2024) is a data gap, not reality** — MEA is one of PIB's most active posters; the underlying index (`pib_index.sqlite`, built for a separate project) under-captures MEA specifically throughout its history, not just this window. Treat MEA's row in `pib_ministry_comparison.csv` as missing, not low.
- The scheme/topic-vs-PIB comparison matches on release **titles only** via substring search, not full release body text — a real undercount of PIB coverage, especially for acronym-heavy PQ terms (e.g. PM-SGMBY, PM-SHRI) that PIB headlines likely spell out in full.
- "Ministry of Planning" and the one "Prime Minister" ministry-label row genuinely have ~0 matching PIB releases in this window — not a matching bug, just a near-dormant PIB presence for Planning and a mislabelled single row for PM.
- **PLI scheme_pq_mentions is a keyword-pattern count, not a verified extraction** — a PQ about a scheme that doesn't use one of the matched phrases (e.g. asks about "Advanced Chemistry Cell manufacturing" without saying "ACC Battery") is missed. Treat these counts as a lower bound.
- **MeitY scheme matching is auto-derived per scheme** (parenthetical acronym if genuinely scheme-specific, else the title's distinguishing words after "for"/"of") rather than hand-curated like the PLI table — lower precision. Two "PLI for IT Hardware" entries (1.0 and 2.0) get identical counts because PQ text can't be told which version it means; this is a real ambiguity in the source data, not a bug.
- **`months_since_update` is time since MeitY's CMS last touched that scheme's page**, not evidence the scheme itself is inactive — a scheme can be fully live with a stale page, or vice versa.
