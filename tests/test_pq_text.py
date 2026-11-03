from __future__ import annotations

from pq_text import (
    canonical_ministry, canonical_party, canonical_state, fuzzy_match, normalize_name, strip_html,
)
from build import index_ls_members


def test_canonical_party_merges_chamber_spellings():
    assert canonical_party("SHSUBT") == canonical_party("ss-ubt") == "SHS(UBT)"
    assert canonical_party("  BJP ") == "BJP"
    assert canonical_party(None) == "Unknown"


def test_canonical_state_unifies_variants():
    assert canonical_state("Keralam") == "Kerala"
    assert canonical_state("national capital territory of delhi") == "Delhi"
    assert canonical_state("  Tamil   Nadu ") == "Tamil Nadu"
    assert canonical_state("") == "Unknown"


def test_canonical_ministry_case_ampersand_and_aliases():
    assert canonical_ministry("Health & Family Welfare") == "HEALTH AND FAMILY WELFARE"
    assert canonical_ministry("Personnel,Public Grievances") == canonical_ministry("Personnel, Public Grievances")
    assert canonical_ministry("Road Transport and High Ways") == "ROAD TRANSPORT AND HIGHWAYS"
    assert canonical_ministry("COMMUNICATION") == "COMMUNICATIONS"
    assert canonical_ministry(None) == "Unknown"


def test_strip_html_and_normalize_name():
    assert strip_html("<p>a&nbsp;b &amp; c</p>") == "a b & c"
    assert strip_html("<br>") is None and strip_html(None) is None
    assert normalize_name("Dr. Shri  Anil   Kumar") == "anil kumar"


def test_fuzzy_match_requires_majority_overlap():
    index, words = index_ls_members(
        [{"mpFirstLastName": "Sanjay Rao Patil", "partySname": "INC", "stateName": "Goa"}]
    )
    assert fuzzy_match("Sanjay Patil", index, words)["party"] == "INC"
    assert fuzzy_match("Rao Totally Different Person", index, words) is None
    assert fuzzy_match("", index, words) is None
