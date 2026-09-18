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
| JAL SHAKTI | 1,997 |
| HOUSING AND URBAN AFFAIRS | 1,823 |
| ENVIRONMENT, FOREST AND CLIMATE CHANGE | 1,809 |
| LABOUR AND EMPLOYMENT | 1,570 |
| RURAL DEVELOPMENT | 1,389 |
| COMMERCE AND INDUSTRY | 1,356 |
| CONSUMER AFFAIRS, FOOD AND PUBLIC DISTRIBUTION | 1,332 |
| ROAD TRANSPORT AND HIGHWAYS | 1,286 |
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

- **Community 1** (13 parties, a left- and minority-interest bloc): AIMIM, AITC, ASP (KR), BAP, CPI, CPI(M), CPI(ML)(L), IUML, RLM, RSP, SAD, SP, VCK
- **Community 2** (24 parties, a broad mainstream bloc containing both the ruling party and the principal opposition): AAP, AIADMK, BJD, BJP, DMK, INC, IND., J&KNC, JD(S), JD(U), JSP, KC(M), KEC, LJSP(RV), MDMK, NCP, NCP(SP), NOM., RJD, RLD, SHS(UBT), SS, TDP, YSRCP
- **Community 3** (8 parties, a smaller regional-development cluster): AGP, AJSU, JMM, PMK, RLP, SKM, UPPL, Unknown
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

## Known gaps

- **Lok Sabha question/answer full text is not in this dataset.** The `api_ls` listing endpoint used to fetch all 34,720 LS questions only exposes the subject line, not the question or answer body — those live only in per-question PDFs (a different URL per question, with a random filename suffix on the 18th LS). Fetching and OCR'ing ~34,700 PDFs was out of scope for this pass; `docs/parties/*.md` and the topic tab work from subject-line text only for the Lok Sabha side.
- **Rajya Sabha has full question text** (`question_text` in `rs_questions` / `all_questions`) but **not answer text** — `rsdoc.nic.in` returns `ans_text: null` for every record; answers are PDF-only there too (`answer_pdf_url`).
- 138 of 34,720 Lok Sabha questions (0.4%) could not be matched to a roster member by name (honorific variants and, in a couple of cases, MPs who left office without a public former-member record) and are excluded from party/state breakdowns.
- Party attribution for a jointly-tabled Lok Sabha question uses the first-listed (lead) member only, to avoid one question inflating multiple parties' counts.
