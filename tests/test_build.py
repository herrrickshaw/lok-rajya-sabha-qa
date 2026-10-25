"""Unit tests for the name/party/ministry normalisation and MP matching in
scripts/build.py. Synthetic roster fixtures only; no network, no data/raw."""
import json

import pytest

import build as b


@pytest.mark.parametrize("raw,expected", [
    ("SHSUBT", "SHS(UBT)"), ("SS-UBT", "SHS(UBT)"), (" ncp-scp ", "NCP(SP)"),
    ("IND", "IND."), ("BJP", "BJP"), ("", "Unknown"), (None, "Unknown"),
])
def test_canonical_party(raw, expected):
    assert b.canonical_party(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Keralam", "Kerala"), ("NCT of Delhi", "Delhi"),
    ("National  Capital Territory of Delhi", "Delhi"), ("Jammu & Kashmir", "Jammu and Kashmir"),
    ("Tamil Nadu", "Tamil Nadu"), ("", "Unknown"),
])
def test_canonical_state(raw, expected):
    assert b.canonical_state(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Housing and Urban Affairs", "HOUSING AND URBAN AFFAIRS"),
    ("Law & Justice", "LAW AND JUSTICE"),
    ("Personnel,Public Grievances and Pensions", "PERSONNEL, PUBLIC GRIEVANCES AND PENSIONS"),
    ("Road Transport and High Ways", "ROAD TRANSPORT AND HIGHWAYS"),
    ("Communication", "COMMUNICATIONS"),
    (None, "Unknown"),
])
def test_canonical_ministry_merges_ls_and_rs_spellings(raw, expected):
    assert b.canonical_ministry(raw) == expected


def test_strip_html():
    assert b.strip_html("<p>Rail&nbsp;safety &amp; <b>signals</b></p>") == "Rail safety & signals"
    assert b.strip_html("<br/>") is None
    assert b.strip_html(None) is None


def test_normalize_name_strips_stacked_honorifics():
    assert b.normalize_name("Dr.  Shri Ram   Kumar") == "ram kumar"
    assert b.normalize_name("Smt. Priya Devi") == "priya devi"
    assert b.normalize_name("Adv. Col. Anil Rao") == "anil rao"


def _write_roster(tmp_path, monkeypatch, members):
    (tmp_path / "ls_members.json").write_text(json.dumps(members))
    monkeypatch.setattr(b, "RAW", tmp_path)
    return b.load_ls_member_index()


ROSTER = [
    {"mpFirstLastName": "Ravi Shankar Prasad", "mpLastFirstName": "Prasad, Ravi Shankar",
     "partySname": "BJP", "stateName": "Bihar", "constName": "Patna Sahib"},
    {"mpFirstLastName": "Supriya Sule", "mpLastFirstName": "Sule, Supriya",
     "partySname": "NCPSP", "stateName": "Maharashtra", "constName": "Baramati"},
]


def test_roster_index_exact_lookup(tmp_path, monkeypatch):
    index, _ = _write_roster(tmp_path, monkeypatch, ROSTER)
    hit = index[b.normalize_name("Shri Ravi Shankar Prasad")]
    assert hit["party"] == "BJP" and hit["state"] == "Bihar"
    assert index["supriya sule"]["party"] == "NCP(SP)"


def test_fuzzy_match_middle_name_variant(tmp_path, monkeypatch):
    index, words = _write_roster(tmp_path, monkeypatch, ROSTER)
    # 2 of 3 words shared with "ravi shankar prasad": Jaccard 2/3 >= 0.5
    assert b.fuzzy_match("Dr. Ravi Prasad", index, words)["party"] == "BJP"


def test_fuzzy_match_rejects_weak_overlap(tmp_path, monkeypatch):
    index, words = _write_roster(tmp_path, monkeypatch, ROSTER)
    # 1 shared word of union 5 (ravi, kumar, yadav, shankar, prasad) -> 0.2
    assert b.fuzzy_match("Ravi Kumar Yadav", index, words) is None
    assert b.fuzzy_match("", index, words) is None


def test_fuzzy_match_is_true_jaccard_when_both_name_orders_normalize_alike(tmp_path, monkeypatch):
    # A single-name MP: FirstLast and LastFirst are the same string, so the
    # roster key is indexed twice. The overlap must still count each shared
    # word once; otherwise "Kanimozhi Abc Xyz" scores 2/3 instead of 1/3 and
    # is wrongly attributed to this MP's party.
    index, words = _write_roster(tmp_path, monkeypatch, [
        {"mpFirstLastName": "Kanimozhi", "mpLastFirstName": "Kanimozhi",
         "partySname": "DMK", "stateName": "Tamil Nadu"}])
    assert b.fuzzy_match("Kanimozhi Abc Xyz", index, words) is None
