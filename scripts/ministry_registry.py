"""
Single ministry-identity registry, shared by every script in this repo that
joins PQ data against an external ministry-level source.

Why this exists: compare_pib.py and compare_pli.py each started out doing
their own ad hoc ministry-name matching against a different external source
(PIB's release labels, igod's who's-who, the PLI report card) -- the same
"every caller hand-rolls its own join against every backend" problem that
pushed Netflix's API layer from direct client-to-microservice calls to a
single aggregation gateway (see ByteByteGo, "Evolution of the Netflix API
Architecture": monolith -> direct access -> gateway aggregation layer ->
federated gateway). The fix here is the same shape at data-pipeline scale:
one registry resolves a PQ ministry's identity across every source once, and
every consumer (compare_pib, compare_pli, and any future integration --
MeitY/DoT/DPIIT's wp-json scheme APIs, PARIVESH, NITI ICED) looks it up
instead of re-deriving its own normalize()/alias table.

This is NOT a runtime service (there's no live gateway to stand up for a
static data-build pipeline) -- it's the data-pipeline equivalent: a single
source of truth, checked in as code + a generated JSON snapshot, that new
integrations extend by adding a column, not by writing new matching logic.

Usage:
    from ministry_registry import load_registry
    registry = load_registry()              # {pq_ministry: MinistryRecord}
    registry["JAL SHAKTI"].pib_label         # -> "Ministry of Jal Shakti"
    registry["JAL SHAKTI"].minister_name     # -> "Shri C R Patil"
    registry["ELECTRONICS AND INFORMATION TECHNOLOGY"].wp_json     # -> {"site": "meity.gov.in", ...}
"""
import csv
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, asdict, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
EXTERNAL = ROOT / "data" / "external"
REGISTRY_PATH = EXTERNAL / "ministry_registry.json"

PIB_DB = Path("/Users/umashankar/india-trade-sector-policy-recommendations/data/pib_index.sqlite")
MINISTER_CONTACTS_CSV = Path("/Users/umashankar/india-govt-yellow-pages/data/pib_ministry_contacts.csv")
SINCE = "2024-06-01"

# PQ ministry -> PIB label(s) to sum, for the cases where Parliament's own
# ministry taxonomy and PIB's diverge (a combined ministry split across PIB's
# constituent departments, or a ministry PIB only lists by sub-department).
PIB_LABEL_ALIASES = {
    "CHEMICALS AND FERTILIZERS": [
        "Ministry of Chemicals and Fertilizers",
        "Ministry of Chemicals and Fertilizers - Department of Chemicals and Petrochemicals",
        "Ministry of Chemicals and Fertilizers - Department of Fertilizers",
        "Ministry of Chemicals and Fertilizers - Department of Pharmaceuticals",
    ],
    "ATOMIC ENERGY": ["Department of Atomic Energy"],
    "SPACE": ["Department of Space"],
    "ELECTRONICS AND INFORMATION TECHNOLOGY": ["Ministry of Electronics & IT"],
    "COMMUNICATION": ["Ministry of Communications"],
    "DEVELOPMENT OF NORTH EASTERN REGION": ["Ministry of Development of North-East Region"],
}

# Integration hooks for ministry-level sources this repo pulls from beyond
# the PQ/PIB/PLI data itself. Filling these in is what "organising data
# ministry-wise" buys a future pass: compare_wp_json_schemes.py reads every
# entry here instead of rediscovering which PQ ministry maps to which site.
#
# Two response shapes exist behind the same "wp-json" label, verified live
# 2026-09-18 (the reference_india_ministry_site_access memory's assumption
# that DoT/DPIIT match MeitY's shape was WRONG -- always verify per site,
# don't extrapolate one ministry's API shape to another's):
#   "wp_core"   -- MeitY: standard WP REST route (wp/v2/<post_type>),
#                  ?per_page=N, bare JSON array response, fields at the
#                  top level (title.rendered, modified, acf.*).
#   "post_page" -- DoT, DPIIT: a custom "post-page" route (not core WP
#                  REST), ?limit=N&page=N&orderby=menu_order,
#                  {"posts":[...], "total_items", "total_pages"} response,
#                  snake_case fields (post_title, post_modified, acf_data.*).
WP_JSON_MINISTRIES = {
    "ELECTRONICS AND INFORMATION TECHNOLOGY": {
        "site": "meity.gov.in", "schema": "wp_core",
        "path": "cms/wp-json/wp/v2/schemes_and_services",
    },
    "COMMUNICATION": {
        "site": "dot.gov.in", "schema": "post_page",
        "path": "cms/wp-json/post-page/schemes_and_services",
    },
    "COMMERCE AND INDUSTRY": {
        "site": "dpiit.gov.in", "schema": "post_page",
        "path": "cms/wp-json/post-page/schemes_and_services",
    },
}
PARIVESH_MINISTRIES = {"ENVIRONMENT, FOREST AND CLIMATE CHANGE"}
NITI_ICED_MINISTRIES = {
    # PQ ministry -> ICED dashboard section (energy/climate/water dataset families)
    "COAL": "energy/fuel-sources/coal",
    "NEW AND RENEWABLE ENERGY": "energy/fuel-sources",
    "PETROLEUM AND NATURAL GAS": "energy/fuel-sources",
    "POWER": "energy/electricity",
    "ENVIRONMENT, FOREST AND CLIMATE CHANGE": "climate-environment/ghg-emissions",
}


@dataclass
class MinistryRecord:
    pq_ministry: str
    pq_total_questions: int = 0
    pib_label: str = ""
    pib_releases_since_2024_06: int = 0
    minister_name: str = ""
    minister_designation: str = ""
    wp_json: dict = field(default_factory=dict)   # {"site", "schema", "path"} or {}
    parivesh: bool = False
    niti_iced_path: str = ""


def normalize(label):
    """Shared normalization for matching a ministry label from any external
    source (PIB, igod) against our own canonical PQ ministry names."""
    if not label:
        return ""
    s = label.strip()
    s = re.sub(r"^(Ministry of|Department of)\s+", "", s, flags=re.I)
    s = s.split(" - ")[0]  # drop sub-department suffix for the generic path
    s = s.replace("&", "AND")
    s = re.sub(r"[,.]", " ", s)  # comma/period become a space -- "Micro,Small" must not fuse into "MicroSmall"
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def read_csv(name):
    with open(PROC / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _resolve_pib_label(pq_ministry, pib_counts_raw, pib_norm_counts):
    """Return (chosen PIB label(s) as a display string, summed release count)."""
    if pq_ministry in PIB_LABEL_ALIASES:
        labels = PIB_LABEL_ALIASES[pq_ministry]
        count = sum(pib_counts_raw.get(lbl, 0) for lbl in labels)
        return "; ".join(labels), count
    norm = normalize(pq_ministry)
    count = pib_norm_counts.get(norm, 0)
    # recover a display label for provenance -- first raw label whose normalized form matches
    label = next((raw for raw in pib_counts_raw if normalize(raw) == norm), "")
    return label, count


def _load_minister_lookup():
    if not MINISTER_CONTACTS_CSV.exists():
        return {}
    rank = {"Minister": 0, "Minister of State (Independent Charge)": 1, "Minister of State": 2}
    best = {}
    with open(MINISTER_CONTACTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name, designation = row.get("contact_name", "").strip(), row.get("designation", "").strip()
            if not name:
                continue
            key = normalize(row["ministry"])
            score = rank.get(designation, 3)
            if key not in best or score < best[key][2]:
                best[key] = (name, designation, score)
    return {k: (v[0], v[1]) for k, v in best.items()}


def build_registry():
    """Resolve every PQ ministry's identity across all wired sources and
    write the result to data/external/ministry_registry.json. Run this once
    (or whenever a new source is wired in); everything else reads the
    generated file via load_registry()."""
    ministry_summary = read_csv("ministry_summary.csv")
    minister_lookup = _load_minister_lookup()

    pib_counts_raw, pib_norm_counts = {}, Counter()
    if PIB_DB.exists():
        con = sqlite3.connect(str(PIB_DB))
        cur = con.cursor()
        cur.execute("SELECT ministry, COUNT(*) FROM pib_items WHERE date >= ? AND kind='release' GROUP BY ministry", (SINCE,))
        pib_counts_raw = dict(cur.fetchall())
        con.close()
        for label, cnt in pib_counts_raw.items():
            pib_norm_counts[normalize(label)] += cnt

    records = {}
    for m in ministry_summary:
        pq_ministry = m["ministry"]
        pib_label, pib_count = _resolve_pib_label(pq_ministry, pib_counts_raw, pib_norm_counts)
        minister_name, minister_designation = minister_lookup.get(normalize(pq_ministry), ("", ""))
        records[pq_ministry] = MinistryRecord(
            pq_ministry=pq_ministry,
            pq_total_questions=int(m["questions"]),
            pib_label=pib_label,
            pib_releases_since_2024_06=pib_count,
            minister_name=minister_name,
            minister_designation=minister_designation,
            wp_json=dict(WP_JSON_MINISTRIES.get(pq_ministry, {})),
            parivesh=pq_ministry in PARIVESH_MINISTRIES,
            niti_iced_path=NITI_ICED_MINISTRIES.get(pq_ministry, ""),
        )

    EXTERNAL.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps({k: asdict(v) for k, v in records.items()}, indent=2))

    matched_pib = sum(1 for r in records.values() if r.pib_releases_since_2024_06 > 0)
    matched_minister = sum(1 for r in records.values() if r.minister_name)
    hooked = sum(1 for r in records.values() if r.wp_json or r.parivesh or r.niti_iced_path)
    print(
        f"Ministry registry: {len(records)} ministries, {matched_pib} PIB-matched, "
        f"{matched_minister} minister-matched, {hooked} with a not-yet-integrated source hook"
    )
    return records


def load_registry():
    """Load the generated registry, building it first if it doesn't exist yet."""
    if not REGISTRY_PATH.exists():
        return build_registry()
    raw = json.loads(REGISTRY_PATH.read_text())
    return {k: MinistryRecord(**v) for k, v in raw.items()}


if __name__ == "__main__":
    build_registry()
