"""
Wire in PARIVESH (the central Environmental Clearance proposal register)
against PQ scrutiny of the Environment ministry.

PARIVESH's public MIS dashboard has an open, no-auth bulk endpoint
(`admin_api/dashboard/getProposals`) that returns every EC proposal in a
date window -- project/company name, state, investment cost, and a granular
approval-stage `status` (see reference_india_ministry_site_access memory).
Two things verified live here that the source memory got wrong or didn't
check, in the same "always verify, never extrapolate" spirit as the
MeitY/DoT/DPIIT integration:

  - The documented `status=Received|Granted` query param is a no-op --
    both values return the byte-identical full dataset (confirmed via MD5).
    The real per-record `status` field (not the query param) has ~19
    distinct fine-grained values ("EC Granted", "Under Examination",
    "Proposal pulled back (withdrawn)", etc.); this script classifies
    granted-vs-not from that field instead.
  - An empty `fromDate`/`toDate` now 500s (the memory's example omitted
    them) -- an explicit date range is required.

Two comparisons, using data this repo already has (no new PQ-side matching
needed for the state one):
  1. Ministry level -- EC proposal volume vs Environment-ministry PQ volume,
     same window, same ratio framing as compare_pib.py.
  2. State level -- EC proposals per state vs that state's Environment-
     ministry PQ volume (already computed in state_ministry_matrix.csv) --
     does regulatory clearance activity in a state track parliamentary
     scrutiny of the ministry that grants it, or not?
  3. A spot-check list of the largest proposals by investment cost, flagged
     for whether the project/company name appears anywhere in PQ text.

Scope: Environmental Clearance (EC) only -- this endpoint's workgroup_name
was uniformly "Environmental Clearance" for every record returned; Forest
Clearance (FC) proposals, if they exist on a different route, are not
covered here.
"""
import csv
import json
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from ministry_registry import PARIVESH_MINISTRIES, read_csv

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
SITE = ROOT / "site"

PARIVESH_MINISTRY = "ENVIRONMENT, FOREST AND CLIMATE CHANGE"
SINCE = "2024-06-01"
BASE_URL = "https://parivesh.nic.in/admin_api/dashboard/getProposals"

STATE_ALIASES = {
    "THE DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "Dadra and Nagar Haveli and Daman and Diu",
}


def fetch_proposals():
    today = date.today().isoformat()
    url = f"{BASE_URL}?fromDate={SINCE}&toDate={today}&status=Received&is_state=false"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        payload = json.load(r)
    if payload.get("status") != 200:
        raise SystemExit(f"PARIVESH returned status {payload.get('status')}: {payload.get('message')}")
    data = payload["data"]
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "parivesh_proposals.json").write_text(json.dumps(data))
    return data


def load_proposals():
    try:
        return fetch_proposals()
    except Exception as e:
        cached = RAW / "parivesh_proposals.json"
        if not cached.exists():
            raise SystemExit(f"Could not fetch PARIVESH proposals and no cache at {cached}: {e}")
        print(f"Live fetch failed ({e}), using cached {cached}")
        return json.loads(cached.read_text())


def normalize_state(name):
    if not name:
        return "Unknown"
    upper = name.strip().upper()
    if upper in STATE_ALIASES:
        return STATE_ALIASES[upper]
    return name.strip().title()


_COMPANY_RE = re.compile(
    r"\bby\s+(?:M/s\.?\s*)?([A-Z][A-Za-z0-9&.,'()\-\s]{3,90}?)"
    r"(?:\s+at\b|\s+for\b|\s+village|\s+in\s+the\b|,|\.(?:\s|$)|$)",
)


def extract_company(project_name):
    """Most PARIVESH project names follow "<description> by [M/s] <Company>
    [at/for/, ...]" -- this pulls the company from that pattern. Titles with
    no "by ..." clause (a real, common case -- some name no company at all;
    some lead WITH the company name instead, e.g. "Newzone India Pvt
    Limited proposed expansion...", which this doesn't catch) return None
    rather than a garbage guess.

    Takes the LAST "by ..." clause, not the first -- titles routinely have
    an earlier, unrelated "by" ("... by enhancing the capacity of ...")
    describing HOW the expansion happens, with the real "by M/s <Company>"
    attribution as the final clause."""
    matches = list(_COMPANY_RE.finditer(project_name or ""))
    if not matches:
        return None
    company = re.sub(r"\s+", " ", matches[-1].group(1)).strip(" .,")
    return company if len(company) >= 4 else None


def extract_activity(other_property_raw):
    try:
        props = json.loads(other_property_raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return None
    for p in props:
        if p.get("label") == "Activity":
            return p.get("value")
    return None


def build_corpus():
    ls_rows = read_csv("ls_questions_enriched.csv")
    rs_rows = read_csv("rs_questions_enriched.csv")
    return [r["subject"] for r in ls_rows] + [r["subject"] for r in rs_rows] + [r.get("question_text") for r in rs_rows]


def main():
    raw = load_proposals()
    by_no = {}
    for r in raw:
        by_no[r.get("proposal_no")] = r  # dedupe, matching the memory's warning about repeat payloads
    proposals = list(by_no.values())

    granted = [p for p in proposals if "grant" in (p.get("status") or "").lower()]
    print(f"PARIVESH: {len(proposals)} distinct EC proposals since {SINCE} ({len(granted)} in a 'granted' status)")

    ministry_pq = int(next((r["questions"] for r in read_csv("ministry_summary.csv") if r["ministry"] == PARIVESH_MINISTRY), 0))
    ratio = round(ministry_pq / len(proposals), 3) if proposals else None
    print(f"{PARIVESH_MINISTRY}: {ministry_pq} PQs, {ratio}x PQ per EC proposal")

    # ---- State-level comparison, reusing state_ministry_matrix.csv (already built) ----
    state_pq = {}
    for r in read_csv("state_ministry_matrix.csv"):
        state_pq[r["state"]] = int(r.get(PARIVESH_MINISTRY, 0) or 0)

    proposals_by_state = Counter(normalize_state(p.get("state_name")) for p in proposals)
    state_rows = []
    for state, pq_count in state_pq.items():
        ec_count = proposals_by_state.get(state, 0)
        state_ratio = round(pq_count / ec_count, 3) if ec_count else None
        state_rows.append({"state": state, "environment_pqs": pq_count, "ec_proposals": ec_count, "pq_per_ec_proposal": state_ratio})
    # states PARIVESH has that our own state list doesn't (rare, but don't silently drop)
    for state, ec_count in proposals_by_state.items():
        if state not in state_pq:
            state_rows.append({"state": state, "environment_pqs": 0, "ec_proposals": ec_count, "pq_per_ec_proposal": 0.0})
    state_rows.sort(key=lambda r: -r["ec_proposals"])
    with open(PROC / "parivesh_state_comparison.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["state", "environment_pqs", "ec_proposals", "pq_per_ec_proposal"])
        w.writeheader()
        w.writerows(state_rows)

    # ---- Activity mix (EIA-2006 schedule categories), volume only ----
    activity_counts = Counter(extract_activity(p.get("other_property")) for p in proposals)
    activity_counts.pop(None, None)
    with open(PROC / "parivesh_activity_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["activity", "ec_proposals"])
        for activity, cnt in activity_counts.most_common():
            w.writerow([activity, cnt])

    # ---- Spot-check: largest proposals by investment cost, PQ-mention flag ----
    corpus = build_corpus()
    big_proposals = sorted((p for p in proposals if p.get("investment_cost")), key=lambda p: -p["investment_cost"])[:25]
    spotcheck_rows = []
    for p in big_proposals:
        name = p.get("project_name") or ""
        company = extract_company(name)
        mentioned = (
            any(company.lower() in (text or "").lower() for text in corpus)
            if company else None
        )
        spotcheck_rows.append(
            {
                "project_name": name,
                "company": company or "",
                "state": normalize_state(p.get("state_name")),
                "investment_cost_rs": p.get("investment_cost"),
                "status": p.get("status"),
                "start_date": (p.get("start_date") or "")[:10],
                "company_mentioned_in_pq": mentioned,
            }
        )
    with open(PROC / "parivesh_mega_projects.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["project_name", "company", "state", "investment_cost_rs", "status", "start_date", "company_mentioned_in_pq"])
        w.writeheader()
        w.writerows(spotcheck_rows)

    with_company = [r for r in spotcheck_rows if r["company"]]
    mentioned_count = sum(1 for r in with_company if r["company_mentioned_in_pq"])

    payload = {
        "since": SINCE,
        "ministry": PARIVESH_MINISTRY,
        "ministry_pq": ministry_pq,
        "total_ec_proposals": len(proposals),
        "granted_count": len(granted),
        "pq_per_ec_proposal": ratio,
        "state_rows": state_rows,
        "top_activities": [{"activity": a, "ec_proposals": c} for a, c in activity_counts.most_common(20)],
        "mega_projects": spotcheck_rows,
        "mega_projects_mentioned": mentioned_count,
        "mega_projects_with_company": len(with_company),
        "note": (
            "PARIVESH's admin_api/dashboard/getProposals, Environmental Clearance (EC) proposals only "
            "-- Forest Clearance isn't covered by this endpoint as verified. The status=Received/Granted "
            "query parameter is a no-op (confirmed byte-identical responses); granted-vs-not is classified "
            "from each proposal's own status field instead. Company names for the largest proposals are "
            "extracted from a \"by [M/s] <Company>\" clause in the project title where one exists (many "
            "titles name no company at all, or lead with the company instead of trailing it -- those show "
            "blank, not a false negative); the mention check itself is a plain substring match, a heuristic "
            "not a verified extraction."
        ),
    }
    (SITE / "parivesh.json").write_text(json.dumps(payload, indent=2))

    print(f"Mega-project spot-check: {len(with_company)}/{len(spotcheck_rows)} largest EC proposals name a company; {mentioned_count} of those are mentioned somewhere in PQ text")
    for r in state_rows[:8]:
        print(f"  {r['state']:<20} ec={r['ec_proposals']:>4}  env_pq={r['environment_pqs']:>4}")


if __name__ == "__main__":
    main()
