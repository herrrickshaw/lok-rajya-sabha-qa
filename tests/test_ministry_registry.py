"""scripts/ministry_registry.py: label normalisation, PIB/minister resolution and the generated registry snapshot."""
import csv
import json
import sqlite3

import pytest


@pytest.fixture
def R(load, repo):
    m = load("ministry_registry")
    # the real paths point into the owner's home directory: always redirect them
    m.PIB_DB = repo / "ext/pib_index.sqlite"
    m.MINISTER_CONTACTS_CSV = repo / "ext/pib_ministry_contacts.csv"
    return m


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


@pytest.mark.parametrize("raw,expected", [
    ("Ministry of Jal Shakti", "JAL SHAKTI"), ("department of Atomic Energy", "ATOMIC ENERGY"), ("Ministry of Home Affairs", "HOME AFFAIRS"),
    ("Ministry of Chemicals and Fertilizers - Department of Fertilizers", "CHEMICALS AND FERTILIZERS"),
    ("Electronics & IT", "ELECTRONICS AND IT"), ("Micro,Small and Medium", "MICRO SMALL AND MEDIUM"), ("Micro.Small", "MICRO SMALL"),
    ("  Coal  ", "COAL"), ("Ministry ofJal", "MINISTRY OFJAL"), ("", ""), (None, ""),
])
def test_normalize(R, raw, expected):
    assert R.normalize(raw) == expected


def test_resolve_pib_label_alias_sums_listed_labels(R):
    raw = {"Ministry of Chemicals and Fertilizers": 5, "Ministry of Chemicals and Fertilizers - Department of Fertilizers": 3, "Other": 9}
    label, count = R._resolve_pib_label("CHEMICALS AND FERTILIZERS", raw, {})
    assert count == 8 and label.startswith("Ministry of Chemicals and Fertilizers; ") and label.count("; ") == 3
    label, count = R._resolve_pib_label("ATOMIC ENERGY", {"Department of Atomic Energy": 4}, {})
    assert (label, count) == ("Department of Atomic Energy", 4)
    assert R._resolve_pib_label("SPACE", {}, {}) == ("Department of Space", 0)


def test_resolve_pib_label_generic_path(R):
    raw = {"Ministry of Jal Shakti": 6, "Department of Jal Shakti": 1}
    norm = {"JAL SHAKTI": 7}
    assert R._resolve_pib_label("JAL SHAKTI", raw, norm) == ("Ministry of Jal Shakti", 7)      # first raw label wins
    assert R._resolve_pib_label("COAL", raw, norm) == ("", 0)


def test_minister_lookup_prefers_cabinet_rank(R):
    cols = ["ministry", "contact_name", "designation"]
    write_csv(R.MINISTER_CONTACTS_CSV, [
        dict(ministry="Ministry of Coal", contact_name="MoS Person", designation="Minister of State"),
        dict(ministry="Ministry of Coal", contact_name="Cab Person", designation="Minister"),
        dict(ministry="Ministry of Coal", contact_name="Late Person", designation="Minister"),          # same rank: first one stays
        dict(ministry="Ministry of Mines", contact_name="IC Person", designation="Minister of State (Independent Charge)"),
        dict(ministry="Ministry of Mines", contact_name="Other", designation="Advisor"),
        dict(ministry="Ministry of Space", contact_name="  ", designation="Minister"),
        dict(ministry="Ministry of Rail", contact_name="Only Adv", designation="Advisor"),
    ], cols)
    got = R._load_minister_lookup()
    assert got == {"COAL": ("Cab Person", "Minister"), "MINES": ("IC Person", "Minister of State (Independent Charge)"), "RAIL": ("Only Adv", "Advisor")}


def test_minister_lookup_missing_file(R):
    assert R._load_minister_lookup() == {}


def make_pib(R, rows):
    R.PIB_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(R.PIB_DB)
    con.execute("CREATE TABLE pib_items(id INTEGER, kind TEXT, date TEXT, ministry TEXT)")
    con.executemany("INSERT INTO pib_items VALUES (?,?,?,?)", rows)
    con.commit()
    con.close()


def test_build_registry_end_to_end(R, repo, capsys):
    write_csv(repo / "data/processed/ministry_summary.csv", [
        dict(ministry="JAL SHAKTI", questions="40"), dict(ministry="ATOMIC ENERGY", questions="7"), dict(ministry="COAL", questions="3"),
        dict(ministry="ELECTRONICS AND INFORMATION TECHNOLOGY", questions="12")], ["ministry", "questions"])
    make_pib(R, [(1, "release", "2024-06-01", "Ministry of Jal Shakti"), (2, "release", "2024-05-31", "Ministry of Jal Shakti"),
                 (3, "factsheet", "2025-01-01", "Ministry of Jal Shakti"), (4, "release", "2025-01-01", "Ministry of Jal Shakti"),
                 (5, "release", "2025-01-01", "Department of Atomic Energy"), (6, "release", "2025-02-01", "Ministry of Electronics & IT")])
    write_csv(R.MINISTER_CONTACTS_CSV, [dict(ministry="Ministry of Jal Shakti", contact_name="Shri Patil", designation="Minister")],
              ["ministry", "contact_name", "designation"])
    recs = R.build_registry()
    assert set(recs) == {"JAL SHAKTI", "ATOMIC ENERGY", "COAL", "ELECTRONICS AND INFORMATION TECHNOLOGY"}
    js = recs["JAL SHAKTI"]
    assert (js.pq_total_questions, js.pib_label, js.pib_releases_since_2024_06) == (40, "Ministry of Jal Shakti", 2)     # >= since date, releases only
    assert (js.minister_name, js.minister_designation) == ("Shri Patil", "Minister")
    assert recs["ATOMIC ENERGY"].pib_releases_since_2024_06 == 1 and recs["ELECTRONICS AND INFORMATION TECHNOLOGY"].pib_releases_since_2024_06 == 1
    assert recs["COAL"].pib_releases_since_2024_06 == 0 and recs["COAL"].minister_name == ""
    saved = json.loads(R.REGISTRY_PATH.read_text())
    assert saved["JAL SHAKTI"]["pq_ministry"] == "JAL SHAKTI" and saved["COAL"]["parivesh"] in (True, False)
    assert capsys.readouterr().out.startswith("Ministry registry: 4 ministries, 3 PIB-matched, 1 minister-matched, ")
    # round trip through load_registry (file now exists)
    again = R.load_registry()
    assert again["JAL SHAKTI"] == recs["JAL SHAKTI"] and isinstance(again["JAL SHAKTI"], R.MinistryRecord)


def test_build_registry_hooks_from_source_tables(R, repo, capsys):
    pq = next(iter(R.WP_JSON_MINISTRIES))
    pv = next(iter(R.PARIVESH_MINISTRIES))
    write_csv(repo / "data/processed/ministry_summary.csv", [dict(ministry=pq, questions="1"), dict(ministry=pv, questions="2"), dict(ministry="NOT A MINISTRY", questions="3")],
              ["ministry", "questions"])
    recs = R.build_registry()
    assert recs[pq].wp_json == dict(R.WP_JSON_MINISTRIES[pq]) and recs[pq].wp_json is not R.WP_JSON_MINISTRIES[pq]
    assert recs[pv].parivesh is True and recs["NOT A MINISTRY"].parivesh is False and recs["NOT A MINISTRY"].wp_json == {}
    assert recs["NOT A MINISTRY"].niti_iced_path == R.NITI_ICED_MINISTRIES.get("NOT A MINISTRY", "")
    out = capsys.readouterr().out
    assert "0 PIB-matched, 0 minister-matched" in out


def test_load_registry_builds_when_missing(R, repo, capsys):
    write_csv(repo / "data/processed/ministry_summary.csv", [dict(ministry="COAL", questions="3")], ["ministry", "questions"])
    assert not R.REGISTRY_PATH.exists()
    recs = R.load_registry()
    assert R.REGISTRY_PATH.exists() and recs["COAL"].pq_total_questions == 3
