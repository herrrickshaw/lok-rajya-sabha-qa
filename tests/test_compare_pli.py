"""scripts/compare_pli.py: PLI scheme mention counting and the report-card join."""
import csv
import json

import pytest


@pytest.fixture
def L(load):
    return load("compare_pli")


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def test_count_mentions_counts_texts_not_matches(L):
    corpus = ["PLI for Drone makers", "drone and PLI again", "unrelated", "", None, "pli  drone"]
    assert L.count_mentions([r"PLI.{0,20}Drone", r"Drone.{0,20}PLI"], corpus) == 3        # case-insensitive; one hit per text
    assert L.count_mentions([r"zzz"], corpus) == 0 and L.count_mentions([], corpus) == 0 and L.count_mentions([r"PLI"], []) == 0
    assert L.count_mentions([r"PLI.{0,20}Drone", r"Drone.{0,20}PLI"], ["PLI Drone and Drone PLI"]) == 1


def test_scheme_map_patterns_are_specific(L):
    m = {name: pats for name, _, pats in L.SCHEME_MAP}
    assert L.count_mentions(m["Electronics (LSEM + IT Hardware)"], ["LSEM units", "mobile phone manufacturing", "ELSEMB"]) == 2
    assert L.count_mentions(m["PLI White Goods (ACs & LEDs)"], ["PLI for LED lights", "PLI AC units", "PLI ACCELERATE"]) == 2
    assert L.count_mentions(m["PLI Bulk Drugs (KSMs/APIs)"], ["Bulk Drug parks", "KSM and API plans"]) == 2
    assert len(L.SCHEME_MAP) == 13 and len({n for n, _, _ in L.SCHEME_MAP}) == 13


CARD = {"retrieved": "2026-07-19", "method": "m", "grade_criteria": {"A": "x"}, "disbursal_report_card": [
    {"scheme": "PLI Drones", "outlay_rs_cr": 120, "disbursed_rs_cr": 30, "grade": "B", "evidence": "ev1"},
    {"scheme": "PLI Specialty Steel", "outlay_rs_cr": 0, "disbursed_rs_cr": 5, "grade": "A", "evidence": "ev2"},
    {"scheme": "PLI Textiles (MMF/technical)", "outlay_rs_cr": 10, "disbursed_rs_cr": 10, "grade": "F"},
    {"scheme": "PLI Solar PV Modules", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "A-"},
    {"scheme": "PLI Food Processing", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "D+"},
    {"scheme": "PLI Telecom & Networking", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "D"},
    {"scheme": "PLI Automobile & Auto Components", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "C+"},
    {"scheme": "PLI ACC Battery Storage", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "C"},
    {"scheme": "PLI Medical Devices", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "B-"},
    {"scheme": "Electronics (LSEM + IT Hardware)", "outlay_rs_cr": 100, "disbursed_rs_cr": 50, "grade": "A"},
    {"scheme": "PLI Pharmaceuticals (formulations)", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "B"},
    {"scheme": "PLI Bulk Drugs (KSMs/APIs)", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "C"},
    {"scheme": "PLI White Goods (ACs & LEDs)", "outlay_rs_cr": 3, "disbursed_rs_cr": 1, "grade": "C"},
]}


def test_main_requires_report_card(L):
    with pytest.raises(SystemExit) as e:
        L.main()
    assert "PLI report card not found at" in str(e.value)


def test_main_joins_card_registry_and_pq_counts(L, repo, monkeypatch, capsys):
    import ministry_registry as R
    (repo / "data/external").mkdir(parents=True)
    (repo / "data/external/pli_report_card.json").write_text(json.dumps(CARD))
    cols = ["subject", "question_text"]
    write_csv(repo / "data/processed/ls_questions_enriched.csv", [dict(subject="PLI for Drone makers"), dict(subject="Specialty Steel")], cols)
    write_csv(repo / "data/processed/rs_questions_enriched.csv", [dict(subject="x", question_text="PLI scheme for textiles and Specialty Steel")], cols)
    monkeypatch.setattr(L, "load_registry", lambda: {"CIVIL AVIATION": R.MinistryRecord(pq_ministry="CIVIL AVIATION", pq_total_questions=77, minister_name="Shri Naidu")})
    L.main()
    with open(repo / "data/processed/pli_scheme_scrutiny.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 13
    grades = [r["grade"] for r in rows]
    order = {"A": 0, "A-": 1, "B": 2, "B-": 3, "C": 4, "C+": 4, "D+": 5, "D": 6, "F": 7}
    assert [order[g] for g in grades] == sorted(order[g] for g in grades)               # best grade first
    assert grades[0] == "A" and grades[-1] == "F"
    by = {r["scheme"]: r for r in rows}
    d = by["PLI Drones"]
    assert (d["pq_ministry"], d["minister_in_charge"], d["ministry_total_pq"], d["scheme_pq_mentions"]) == ("CIVIL AVIATION", "Shri Naidu", "77", "1")
    assert (d["outlay_rs_cr"], d["disbursed_rs_cr"], d["disbursed_pct"], d["grade"], d["grade_evidence"]) == ("120", "30", "25.0", "B", "ev1")
    steel = by["PLI Specialty Steel"]
    assert steel["disbursed_pct"] == "" and steel["scheme_pq_mentions"] == "2"            # zero outlay -> no percentage
    assert by["PLI Textiles (MMF/technical)"]["disbursed_pct"] == "100.0" and by["PLI Textiles (MMF/technical)"]["scheme_pq_mentions"] == "1"
    el = by["Electronics (LSEM + IT Hardware)"]
    assert (el["disbursed_pct"], el["minister_in_charge"], el["ministry_total_pq"]) == ("50.0", "", "0")      # ministry missing from the registry
    data = json.loads((repo / "site/pli.json").read_text())
    assert data["retrieved"] == "2026-07-19" and data["method"] == "m" and data["grade_criteria"] == {"A": "x"} and len(data["rows"]) == 13
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "13 PLI schemes joined" and out[1].startswith("    A  Electronics")


@pytest.mark.xfail(strict=True, raises=TypeError,
                   reason="compare_pli.py:149 formats `{r['grade']:>3}`; a scheme missing from the report card has grade None and the final print crashes")
def test_main_survives_scheme_missing_from_report_card(L, repo, monkeypatch):
    import ministry_registry as R
    card = dict(CARD, disbursal_report_card=CARD["disbursal_report_card"][:-1])      # drop White Goods
    (repo / "data/external").mkdir(parents=True)
    (repo / "data/external/pli_report_card.json").write_text(json.dumps(card))
    cols = ["subject", "question_text"]
    write_csv(repo / "data/processed/ls_questions_enriched.csv", [], cols)
    write_csv(repo / "data/processed/rs_questions_enriched.csv", [], cols)
    monkeypatch.setattr(L, "load_registry", lambda: {})
    L.main()
