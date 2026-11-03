"""Characterisation test for compare_parivesh.main on synthetic proposals (no network).

Golden files in tests/fixtures/parivesh_golden were produced by the pre-refactor main()."""
from __future__ import annotations

import json
import os
from pathlib import Path

import compare_parivesh

GOLDEN = Path(__file__).parent / "fixtures" / "parivesh_golden"
MIN = compare_parivesh.PARIVESH_MINISTRY

PROPOSALS = [
    {"proposal_no": "P1", "project_name": "Expansion of plant by M/s Alpha Steel Ltd at Surat", "state_name": "GUJARAT",
     "investment_cost": 5.0e9, "status": "EC Granted", "start_date": "2024-07-01T00:00:00",
     "other_property": json.dumps([{"label": "Activity", "value": "Metallurgical"}])},
    {"proposal_no": "P1", "project_name": "dup should be replaced", "state_name": "GUJARAT",
     "investment_cost": 6.0e9, "status": "EC Granted", "start_date": "2024-07-02T00:00:00",
     "other_property": json.dumps([{"label": "Activity", "value": "Metallurgical"}])},
    {"proposal_no": "P2", "project_name": "Port work by Beta Ports Pvt Ltd", "state_name": "the dadra and nagar haveli and daman and diu",
     "investment_cost": 2.0e9, "status": "Under Examination", "start_date": "2024-08-01",
     "other_property": "not json"},
    {"proposal_no": "P3", "project_name": "No company named", "state_name": "Goa", "investment_cost": None,
     "status": "Pulled back", "start_date": None, "other_property": None},
    {"proposal_no": "P4", "project_name": "Mine by Gamma Mining", "state_name": None, "investment_cost": 1.0e9,
     "status": "Granted", "start_date": "2024-09-09", "other_property": json.dumps([{"label": "Other", "value": "x"}])},
]
TABLES = {
    "ministry_summary.csv": [{"ministry": MIN, "questions": "50"}, {"ministry": "OTHER", "questions": "9"}],
    "state_ministry_matrix.csv": [
        {"state": "Gujarat", MIN: "10"}, {"state": "Goa", MIN: "3"}, {"state": "Kerala", MIN: ""},
    ],
    "ls_questions_enriched.csv": [{"subject": "Alpha Steel emissions"}, {"subject": "roads"}],
    "rs_questions_enriched.csv": [{"subject": "ports", "question_text": "about beta ports pvt ltd"}],
}


def _run(tmp_path, monkeypatch):
    out, site = tmp_path / "processed", tmp_path / "site"
    out.mkdir(), site.mkdir()
    monkeypatch.setattr(compare_parivesh, "PROC", out)
    monkeypatch.setattr(compare_parivesh, "SITE", site)
    monkeypatch.setattr(compare_parivesh, "load_proposals", lambda: [dict(p) for p in PROPOSALS])
    monkeypatch.setattr(compare_parivesh, "read_csv", lambda name: TABLES[name])
    compare_parivesh.main()
    return out, site


def test_main_matches_golden(tmp_path, monkeypatch, capsys):
    out, site = _run(tmp_path, monkeypatch)
    printed = capsys.readouterr().out
    if os.environ.get("REGEN_GOLDEN"):
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for p in out.iterdir():
            (GOLDEN / p.name).write_bytes(p.read_bytes())
        (GOLDEN / "parivesh.json").write_bytes((site / "parivesh.json").read_bytes())
        (GOLDEN / "stdout.txt").write_text(printed)
    for p in out.iterdir():
        assert p.read_bytes() == (GOLDEN / p.name).read_bytes(), p.name
    assert (site / "parivesh.json").read_bytes() == (GOLDEN / "parivesh.json").read_bytes()
    assert printed == (GOLDEN / "stdout.txt").read_text()
    assert sorted(p.name for p in out.iterdir()) == [
        "parivesh_activity_summary.csv", "parivesh_mega_projects.csv", "parivesh_state_comparison.csv",
    ]
