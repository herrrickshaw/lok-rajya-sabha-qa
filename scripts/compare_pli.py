"""
Integrate the PLI (Production Linked Incentive) beneficiary/disbursal report
card -- a separate, PIB-sourced research asset from
india-trade-sector-policy-recommendations -- against this repo's PQ corpus.

The report card grades each of the 13 PLI sub-schemes A-F on whether the
government's own incentive money is actually flowing (not just approved),
with every claim traced to a PIB release ID. Joining it against PQ volume
answers a question neither dataset answers alone: are the worst-performing
schemes (D/F grades -- negligible disbursal, stalled implementation) getting
proportionate parliamentary scrutiny, or flying under the radar relative to
better-performing ones?

Source: data/external/pli_report_card.json in *this* repo -- a copied
snapshot (retrieved 2026-07-19) of
india-trade-sector-policy-recommendations/data/pli_report_card_2026-07-19.json,
included directly (it's 21KB) rather than referenced by external path, unlike
the much larger PIB press-release index in compare_pib.py.

The minister-in-charge for each scheme's administering ministry comes from
the same ministry_registry.py used by compare_pib.py -- this integration
didn't need to write its own igod-matching code, which is the whole point of
having one registry instead of one bespoke join per script.
"""
import csv
import json
import re
from pathlib import Path

from ministry_registry import load_registry

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
SITE = ROOT / "site"
REPORT_CARD = ROOT / "data" / "external" / "pli_report_card.json"

# report-card scheme -> (our PQ ministry bucket, PQ-text regex patterns to
# count mentions of *that specific* sub-scheme, not "PLI" in general).
# Ministry mapping follows the administering department: DoP schemes sit
# inside our combined CHEMICALS AND FERTILIZERS bucket (see MANUAL_ALIASES in
# compare_pib.py -- DoP is a department of that ministry, not a standalone
# PQ ministry); DoT sits inside COMMUNICATIONS; DPIIT inside COMMERCE AND
# INDUSTRY.
SCHEME_MAP = [
    ("Electronics (LSEM + IT Hardware)", "ELECTRONICS AND INFORMATION TECHNOLOGY",
     [r"\bLSEM\b", r"Large[- ]Scale Electronics", r"IT Hardware", r"Mobile Phone Manufactur"]),
    ("PLI Pharmaceuticals (formulations)", "CHEMICALS AND FERTILIZERS",
     [r"PLI.{0,20}Pharmaceutical", r"Pharmaceutical.{0,20}PLI"]),
    ("PLI Bulk Drugs (KSMs/APIs)", "CHEMICALS AND FERTILIZERS",
     [r"Bulk Drug", r"\bKSM\b.{0,10}API", r"Critical.{0,5}KSM"]),
    ("PLI Medical Devices", "CHEMICALS AND FERTILIZERS",
     [r"Medical Device.{0,20}PLI", r"PLI.{0,20}Medical Device"]),
    ("PLI Food Processing", "FOOD PROCESSING INDUSTRIES",
     [r"PLI.{0,20}Food Processing", r"Food Processing.{0,20}PLI"]),
    ("PLI Telecom & Networking", "COMMUNICATIONS",
     [r"PLI.{0,20}Telecom", r"Telecom.{0,20}PLI"]),
    ("PLI White Goods (ACs & LEDs)", "COMMERCE AND INDUSTRY",
     [r"White Goods", r"PLI.{0,15}\bLED\b", r"PLI.{0,15}\bAC\b"]),
    ("PLI Solar PV Modules", "NEW AND RENEWABLE ENERGY",
     [r"PLI.{0,20}Solar", r"Solar.{0,20}PLI", r"High Efficiency Solar"]),
    ("PLI Drones", "CIVIL AVIATION",
     [r"PLI.{0,20}Drone", r"Drone.{0,20}PLI"]),
    ("PLI Automobile & Auto Components", "HEAVY INDUSTRIES",
     [r"PLI.{0,20}Auto", r"Auto.{0,20}PLI", r"Advanced Chemistry Cell.{0,10}Auto"]),
    ("PLI Specialty Steel", "STEEL",
     [r"Specialty Steel", r"Special(?:i|is)ed Steel"]),
    ("PLI Textiles (MMF/technical)", "TEXTILES",
     [r"PLI.{0,20}Textile", r"Textile.{0,20}PLI", r"\bMMF\b.{0,10}Technical Textile"]),
    ("PLI ACC Battery Storage", "HEAVY INDUSTRIES",
     [r"ACC Battery", r"Advanced Chemistry Cell"]),
]


def read_csv(name):
    with open(PROC / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def count_mentions(patterns, corpus):
    compiled = [re.compile(p, re.I) for p in patterns]
    count = 0
    for text in corpus:
        if not text:
            continue
        if any(p.search(text) for p in compiled):
            count += 1
    return count


def main():
    if not REPORT_CARD.exists():
        raise SystemExit(f"PLI report card not found at {REPORT_CARD} -- copy it in first")
    card = json.loads(REPORT_CARD.read_text())
    grade_by_scheme = {r["scheme"]: r for r in card["disbursal_report_card"]}

    ls_rows = read_csv("ls_questions_enriched.csv")
    rs_rows = read_csv("rs_questions_enriched.csv")
    corpus = [r["subject"] for r in ls_rows] + [r["subject"] for r in rs_rows] + [r.get("question_text") for r in rs_rows]

    registry = load_registry()

    rows = []
    for scheme, ministry, patterns in SCHEME_MAP:
        gc = grade_by_scheme.get(scheme, {})
        pq_mentions = count_mentions(patterns, corpus)
        rec = registry.get(ministry)
        rows.append(
            {
                "scheme": scheme,
                "pq_ministry": ministry,
                "minister_in_charge": rec.minister_name if rec else "",
                "ministry_total_pq": rec.pq_total_questions if rec else 0,
                "scheme_pq_mentions": pq_mentions,
                "outlay_rs_cr": gc.get("outlay_rs_cr"),
                "disbursed_rs_cr": gc.get("disbursed_rs_cr"),
                "disbursed_pct": round(100 * gc.get("disbursed_rs_cr", 0) / gc["outlay_rs_cr"], 2) if gc.get("outlay_rs_cr") else None,
                "grade": gc.get("grade"),
                "grade_evidence": gc.get("evidence"),
            }
        )

    grade_order = {"A": 0, "A-": 1, "B": 2, "B-": 3, "C": 4, "C+": 4, "D": 6, "D+": 5, "F": 7}
    rows.sort(key=lambda r: grade_order.get(r["grade"], 99))

    fieldnames = ["scheme", "pq_ministry", "minister_in_charge", "ministry_total_pq", "scheme_pq_mentions", "outlay_rs_cr", "disbursed_rs_cr", "disbursed_pct", "grade", "grade_evidence"]
    with open(PROC / "pli_scheme_scrutiny.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    payload = {
        "retrieved": card.get("retrieved"),
        "method": card.get("method"),
        "grade_criteria": card.get("grade_criteria"),
        "rows": rows,
        "note": (
            "PLI disbursal report card copied from a separate project "
            "(india-trade-sector-policy-recommendations), grades and figures are that "
            "repo's own PIB-sourced judgment, not re-verified here. scheme_pq_mentions counts "
            "Lok Sabha subject lines + Rajya Sabha subject lines/full question text matching "
            "scheme-specific keyword patterns (see SCHEME_MAP in compare_pli.py) -- a "
            "conservative undercount, since PQs about a scheme don't always name it explicitly."
        ),
    }
    (SITE / "pli.json").write_text(json.dumps(payload, indent=2))

    print(f"{len(rows)} PLI schemes joined")
    for r in rows:
        print(f"  {r['grade']:>3}  {r['scheme']:<38} pq_mentions={r['scheme_pq_mentions']:>4}  disbursed={r['disbursed_pct']}%")


if __name__ == "__main__":
    main()
