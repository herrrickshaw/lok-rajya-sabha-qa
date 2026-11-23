"""scripts/build.py: roster/name normalisation, LS/RS enrichment and the full summary build, on a tiny synthetic corpus."""
import csv
import json
import re

import pytest


@pytest.fixture
def B(load):
    return load("build")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ canonicalisers
@pytest.mark.parametrize("raw,expected", [
    ("SHSUBT", "SHS(UBT)"), ("ss-ubt", "SHS(UBT)"), (" ncpsp ", "NCP(SP)"), ("NCP-SCP", "NCP(SP)"),
    ("YSR Congress Party", "YSRCP"), ("Ind", "IND."), ("IND.", "IND."), ("UPP(L)", "UPPL"),
    ("BJP", "BJP"), ("  Some Party  ", "Some Party"), ("", "Unknown"), (None, "Unknown"),
])
def test_canonical_party(B, raw, expected):
    assert B.canonical_party(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Keralam", "Kerala"), ("KERALAM", "Kerala"), ("National Capital Territory of Delhi", "Delhi"), ("NCT of  Delhi", "Delhi"),
    ("Jammu & Kashmir", "Jammu and Kashmir"), ("  Tamil   Nadu ", "Tamil Nadu"), ("Goa", "Goa"), ("", "Unknown"), (None, "Unknown"),
])
def test_canonical_state(B, raw, expected):
    assert B.canonical_state(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Housing and Urban Affairs", "HOUSING AND URBAN AFFAIRS"),
    ("HOUSING  AND URBAN AFFAIRS", "HOUSING AND URBAN AFFAIRS"),
    ("Law & Justice", "LAW AND JUSTICE"), ("Law&Justice", "LAW AND JUSTICE"),
    ("Personnel,Public Grievances", "PERSONNEL, PUBLIC GRIEVANCES"), ("Personnel,  Public Grievances", "PERSONNEL, PUBLIC GRIEVANCES"),
    ("Road Transport and High Ways", "ROAD TRANSPORT AND HIGHWAYS"), ("Communication", "COMMUNICATIONS"), ("Communications", "COMMUNICATIONS"),
    ("", "Unknown"), (None, "Unknown"),
])
def test_canonical_ministry(B, raw, expected):
    assert B.canonical_ministry(raw) == expected


def test_strip_html(B):
    assert B.strip_html("<p>Hello&nbsp;<b>world</b> &amp; co</p>") == "Hello world & co"
    assert B.strip_html("  a \n\t b  ") == "a b"
    assert B.strip_html("<br/>") is None and B.strip_html("") is None and B.strip_html(None) is None


@pytest.mark.parametrize("raw,expected", [
    ("Dr. Shashi Tharoor", "shashi tharoor"), ("SHRI  RAHUL   GANDHI", "rahul gandhi"), ("Smt. Dr. Prof. X Y", "x y"),
    ("Mohd. Azam", "azam"), ("Adv. Er. Raj", "raj"), ("Capt. Maj. Singh", "singh"),
    ("  Plain Name ", "plain name"), ("Justice", "justice"), ("Major General", "general"), ("Thiru Selvi Devi", "devi"),
    ("Drake Smith", "drake smith"),                        # 'dr' is only stripped as a whole word
])
def test_normalize_name(B, raw, expected):
    assert B.normalize_name(raw) == expected


# ------------------------------------------------------------------ rosters
LS_MEMBERS = [
    {"mpFirstLastName": "Shashi Tharoor", "mpLastFirstName": "Tharoor Shashi", "partySname": "INC", "partyFname": "Indian National Congress",
     "stateName": "Kerala", "constName": "Thiruvananthapuram"},
    {"mpFirstLastName": "Dr. Rahul Gandhi", "mpLastFirstName": "", "partySname": "", "partyFname": "Indian National Congress", "stateName": "Keralam", "constName": "Wayanad"},
    {"mpFirstLastName": "Amit Kumar Shah", "mpLastFirstName": None, "partySname": "BJP", "partyFname": "Bharatiya Janata Party", "stateName": "", "constName": "G"},
    {"mpFirstLastName": None, "mpLastFirstName": None, "partySname": "X"},
]


def test_load_ls_member_index(B, repo):
    write_json(repo / "data/raw/ls_members.json", LS_MEMBERS)
    index, words = B.load_ls_member_index()
    assert index["shashi tharoor"]["party"] == "INC" and index["tharoor shashi"]["party"] == "INC"
    rg = index["rahul gandhi"]
    assert rg["party"] == "Indian National Congress" and rg["state"] == "Kerala" and rg["canonical_name"] == "Dr. Rahul Gandhi"   # no short name -> full name
    assert index["amit kumar shah"]["state"] == "Unknown"
    assert set(words["shashi"]) == {"shashi tharoor", "tharoor shashi"} and words["tharoor"] == ["shashi tharoor", "tharoor shashi"]
    assert "ka" not in words and "kumar" in words                    # words of <= 2 chars are not indexed
    assert len(index) == 4


def test_fuzzy_match_threshold_and_choice(B, repo):
    write_json(repo / "data/raw/ls_members.json", LS_MEMBERS + [{"mpFirstLastName": "Amit Shah", "partySname": "BJP2", "stateName": "Gujarat"}])
    index, words = B.load_ls_member_index()
    # "Shri Amit Kumar Shah Ji": words {amit,kumar,shah,ji->dropped} overlaps the 3-word record fully
    assert B.fuzzy_match("Shri Amit Kumar Shah", index, words)["party"] == "BJP"
    assert B.fuzzy_match("Amit Shah", index, words)["party"] == "BJP2"            # exact word set -> 2/2 beats 2/3
    assert B.fuzzy_match("Zzz Qqq", index, words) is None                           # no overlap
    assert B.fuzzy_match("Dr. Ab", index, words) is None                            # no word longer than 2 chars
    assert B.fuzzy_match("Amit Zzzz Yyyy Xxxx", index, words) is None              # 1 shared word / 6 in the union < 0.5
    assert B.fuzzy_match("Rahul Gandhi Vadra", index, words)["state"] == "Kerala"  # 2/3 = 0.667 >= 0.5
    assert B.fuzzy_match("Shashi", index, words)["party"] == "INC"                 # exactly 1/2 = 0.5 still counts (>=)
    assert B.fuzzy_match("Shashi Ghosh Roy Sen", index, words) is None              # 1/5 < 0.5


def test_fuzzy_match_tie_goes_to_the_first_roster_entry(B, repo):
    write_json(repo / "data/raw/ls_members.json", [
        {"mpFirstLastName": "Rahul Gandhi", "partySname": "P1", "stateName": "Goa"},
        {"mpFirstLastName": "Gandhi Rahul", "partySname": "P2", "stateName": "Goa"}])
    index, words = B.load_ls_member_index()
    assert B.fuzzy_match("Rahul Gandhi Jee", index, words)["party"] == "P1"             # equal Jaccard scores: earlier candidate wins


def test_load_rs_member_index_merges_former(B, repo):
    write_json(repo / "data/raw/rs_members.json", [
        {"mpsno": 1, "partyCode": "BJP", "party": "Bharatiya Janata Party", "state": "Assam", "name": " A B "},
        {"mpsno": 2, "partyCode": None, "party": None, "state": "Keralam", "name": None}])
    write_json(repo / "data/raw/rs_members_former.json", [{"mpsno": 3, "partyCode": "SS-UBT", "party": "Shiv Sena (UBT)", "state": "Delhi", "name": "C"}])
    idx = B.load_rs_member_index()
    assert idx[1] == {"party": "BJP", "party_full": "Bharatiya Janata Party", "state": "Assam", "canonical_name": "A B"}
    assert idx[2]["party"] == "Unknown" and idx[2]["state"] == "Kerala" and idx[2]["canonical_name"] == ""
    assert idx[3]["party"] == "SHS(UBT)" and set(idx) == {1, 2, 3}


def test_load_rs_member_index_without_former_file(B, repo):
    write_json(repo / "data/raw/rs_members.json", [{"mpsno": 1, "partyCode": "X", "state": "Goa"}])
    assert set(B.load_rs_member_index()) == {1}
    (repo / "data/raw/rs_members.json").unlink()
    assert B.load_rs_member_index() == {}


# ------------------------------------------------------------------ question tables
def test_build_ls_matches_exact_then_fuzzy_then_unmatched(B, repo):
    write_json(repo / "data/raw/ls_members.json", LS_MEMBERS)
    index, words = B.load_ls_member_index()
    write_json(repo / "data/raw/ls_questions.json", [
        {"quesNo": 1, "sessionNo": 7, "date": "2025-02-01", "type": "STARRED", "ministry": "Housing & Urban Affairs", "subjects": " Water supply ",
         "member": ["Dr. Shashi Tharoor", "Amit Kumar Shah"]},
        {"quesNo": 2, "member": ["Shri Amit Kumar Shah"], "ministry": "Communication", "subjects": None, "type": "UNSTARRED"},
        {"quesNo": 3, "member": ["Nobody Known"], "ministry": None, "subjects": "x"},
        {"quesNo": 4, "member": [], "ministry": "Law"}, {"quesNo": 5},
    ])
    rows, unmatched = B.build_ls(index, words)
    r1, r2, r3, r4, r5 = rows
    assert (r1["party"], r1["party_full"], r1["state"], r1["member"]) == ("INC", "Indian National Congress", "Kerala", "Dr. Shashi Tharoor")
    assert r1["all_members"] == "Dr. Shashi Tharoor; Amit Kumar Shah" and r1["subject"] == "Water supply"
    assert r1["ministry"] == "HOUSING AND URBAN AFFAIRS" and r1["chamber"] == "Lok Sabha" and r1["ques_no"] == 1 and r1["session_no"] == 7
    assert r1["question_text"] is None and r1["answer_pdf_url"] is None
    assert (r2["party"], r2["state"], r2["ministry"], r2["subject"]) == ("BJP", "Unknown", "COMMUNICATIONS", "")
    assert (r3["party"], r3["party_full"], r3["state"], r3["ministry"]) == ("Unknown", None, "Unknown", "Unknown")
    assert (r4["party"], r4["member"], r4["all_members"]) == ("Unknown", None, "") and r5["member"] is None
    assert dict(unmatched) == {"Nobody Known": 1}


def test_build_rs_uses_mp_code_and_strips_html(B, repo):
    write_json(repo / "data/raw/rs_members.json", [{"mpsno": 11, "partyCode": "BJP", "party": "Bharatiya Janata Party", "state": "Assam", "name": "A"}])
    rs_index = B.load_rs_member_index()
    write_json(repo / "data/raw/rs_questions_raw.json", [
        {"qno": 5, "ses_no": 265, "ans_date": "2025-03-03", "qtype": " STARRED ", "min_name": "Law & Justice", "qtitle": " Title ", "name": " Mem One ",
         "mp_code": 11, "qn_text": "<p>Q&nbsp;text</p>", "ans_text": "<b>Ans</b>", "files": "http://f.pdf"},
        {"qno": 6, "mp_code": 99, "name": "Ghost", "qtype": None},
        {"qno": 7, "mp_code": 99, "name": "Ghost"}, {"qno": 8},
    ])
    rows, unmatched = B.build_rs(rs_index)
    a = rows[0]
    assert (a["party"], a["party_full"], a["state"], a["type"], a["ministry"], a["subject"], a["member"]) == \
        ("BJP", "Bharatiya Janata Party", "Assam", "STARRED", "LAW AND JUSTICE", "Title", "Mem One")
    assert (a["question_text"], a["answer_text"], a["answer_pdf_url"], a["chamber"], a["ques_no"], a["session_no"], a["date"]) == \
        ("Q text", "Ans", "http://f.pdf", "Rajya Sabha", 5, 265, "2025-03-03")
    assert rows[1]["party"] == "Unknown" and rows[1]["state"] == "Unknown" and rows[1]["type"] == "" and rows[1]["question_text"] is None
    assert dict(unmatched) == {"Ghost": 2, None: 1}


def test_write_csv(B, tmp_path):
    p = tmp_path / "o.csv"
    B.write_csv(p, [{"a": 1, "b": "x,y"}, {"a": 2, "b": "é"}], ["a", "b"])
    assert read_csv(p) == [{"a": "1", "b": "x,y"}, {"a": "2", "b": "é"}]


# ------------------------------------------------------------------ main
@pytest.fixture
def corpus(repo):
    write_json(repo / "data/raw/ls_members.json", LS_MEMBERS)
    write_json(repo / "data/raw/rs_members.json", [
        {"mpsno": 11, "partyCode": "BJP", "party": "Bharatiya Janata Party", "state": "Assam", "name": "A"},
        {"mpsno": 12, "partyCode": "INC", "party": "Indian National Congress", "state": "Keralam", "name": "B"}])
    ls = [
        {"quesNo": i, "sessionNo": 7, "date": "d", "type": "STARRED" if i % 2 else "UNSTARRED", "ministry": "Health", "subjects": "Rural health mission funds",
         "member": ["Dr. Shashi Tharoor"]} for i in range(1, 5)]
    ls += [{"quesNo": 10, "type": "UNSTARRED", "ministry": "Railways", "subjects": "Railway safety audit", "member": ["Amit Kumar Shah", "Dr. Shashi Tharoor"]},
           {"quesNo": 11, "type": "", "ministry": "Railways", "subjects": "Rural health mission funds", "member": ["Unknown Person"]}]
    write_json(repo / "data/raw/ls_questions.json", ls)
    write_json(repo / "data/raw/rs_questions_raw.json", [
        {"qno": 1, "ses_no": 265, "ans_date": "d", "qtype": "STARRED", "min_name": "HEALTH", "qtitle": "Rural health mission funds", "name": "A", "mp_code": 11},
        {"qno": 2, "ses_no": 265, "ans_date": "d", "qtype": "UNSTARRED", "min_name": "Railways", "qtitle": "Railway safety audit", "name": "B", "mp_code": 12},
        {"qno": 3, "ses_no": 265, "ans_date": "d", "qtype": "UNSTARRED", "min_name": "Railways", "qtitle": "Railway safety audit", "name": "Z", "mp_code": 99}])
    return repo


def test_main_writes_all_outputs(B, corpus, capsys):
    B.main()
    out = corpus / "data/processed"
    ls = read_csv(out / "ls_questions_enriched.csv")
    assert len(ls) == 6 and list(ls[0]) == ["chamber", "ques_no", "session_no", "date", "type", "ministry", "subject", "member", "all_members",
                                           "party", "party_full", "state", "question_text", "answer_text", "answer_pdf_url"]
    ps = {r["party"]: r for r in read_csv(out / "party_summary.csv")}
    assert ps["INC"] == {"party": "INC", "lok_sabha_questions": "4", "rajya_sabha_questions": "1", "total_questions": "5"}
    assert ps["BJP"]["lok_sabha_questions"] == "1" and ps["BJP"]["rajya_sabha_questions"] == "1" and ps["Unknown"]["total_questions"] == "2"
    parties = [r["party"] for r in read_csv(out / "party_summary.csv")]
    assert parties[0] == "INC"                                                       # sorted by total, descending
    ms = {r["ministry"]: int(r["questions"]) for r in read_csv(out / "ministry_summary.csv")}
    assert ms == {"HEALTH": 5, "RAILWAYS": 4}
    ss = {r["state"]: int(r["questions"]) for r in read_csv(out / "state_summary.csv")}
    assert ss["Kerala"] == 5 and ss["Assam"] == 1 and ss["Unknown"] == 3
    pm = {r["party"]: r for r in read_csv(out / "party_ministry_matrix.csv")}
    assert pm["INC"]["HEALTH"] == "4" and pm["INC"]["RAILWAYS"] == "1" and list(pm["INC"]) == ["party", "HEALTH", "RAILWAYS"]
    pt = {r["party"]: r for r in read_csv(out / "party_type_matrix.csv")}
    assert pt["INC"]["STARRED"] == "2" and pt["INC"]["UNSTARRED"] == "3" and pt["Unknown"]["UNKNOWN"] == "1"      # blank type -> UNKNOWN
    sp = {r["state"]: r for r in read_csv(out / "state_party_matrix.csv")}
    assert sp["Kerala"]["INC"] == "5"
    sm = {r["state"]: r for r in read_csv(out / "state_ministry_matrix.csv")}
    assert sm["Kerala"]["HEALTH"] == "4"
    unmatched = read_csv(out / "unmatched_members.csv")
    assert {(r["chamber"], r["name"], r["count"]) for r in unmatched} == {("Lok Sabha", "Unknown Person", "1"), ("Rajya Sabha", "Z", "1")}
    topics = read_csv(out / "topic_keywords.csv")
    allt = {r["term"]: int(r["count"]) for r in topics if r["party"] == "ALL"}
    assert allt == {"rural health": 6, "health mission": 6, "mission funds": 6, "railway safety": 3, "safety audit": 3}   # bigrams seen >= 3 times; their unigrams are folded in
    data = json.loads((corpus / "site/data.json").read_text())
    assert data["totals"] == {"lok_sabha": 6, "rajya_sabha": 3, "combined": 9, "unmatched_ls": 1, "unmatched_rs": 1}
    assert data["party_ministry_matrix"]["ministries"] == ["HEALTH", "RAILWAYS"]
    assert data["party_summary"][0]["party"] == "INC"
    text = capsys.readouterr().out
    assert "LS rows: 6 unmatched: 1" in text and "RS rows: 3 unmatched: 1" in text
