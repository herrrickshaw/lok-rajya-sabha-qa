"""scripts/compare_parivesh.py: PARIVESH EC proposals vs Environment-ministry PQs (HTTP faked, cache fallback)."""
import csv
import io
import json
import urllib.request

import pytest

ENV = "ENVIRONMENT, FOREST AND CLIMATE CHANGE"


@pytest.fixture
def V(load):
    return load("compare_parivesh")


def write_csv(repo, name, rows, cols):
    p = repo / "data/processed" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def read(repo, name):
    with open(repo / "data/processed" / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fake_urlopen(monkeypatch, payload=None, error=None):
    seen = []

    def urlopen(req, timeout=None):
        seen.append((req.full_url, timeout, req.get_header("User-agent")))
        if error:
            raise error
        return io.StringIO(json.dumps(payload))
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return seen


# ------------------------------------------------------------------ pure helpers
@pytest.mark.parametrize("raw,expected", [
    ("gujarat", "Gujarat"), ("  TAMIL NADU ", "Tamil Nadu"), ("THE DADRA AND NAGAR HAVELI AND DAMAN AND DIU", "Dadra and Nagar Haveli and Daman and Diu"),
    ("the dadra and nagar haveli and daman and diu", "Dadra and Nagar Haveli and Daman and Diu"), ("", "Unknown"), (None, "Unknown"),
])
def test_normalize_state(V, raw, expected):
    assert V.normalize_state(raw) == expected


@pytest.mark.parametrize("name,expected", [
    ("Expansion of plant by M/s Adani Power Ltd at Mundra", "Adani Power Ltd"),
    ("Expansion by Vedanta Limited for new unit", "Vedanta Limited"),
    ("Expansion by enhancing capacity by M/s Tata Steel Ltd, Jamshedpur", "Tata Steel Ltd"),            # last 'by' clause wins
    ("Capacity expansion by M/s. JSW Steel Ltd.", "JSW Steel Ltd"),
    ("Newzone India Pvt Limited proposed expansion", None),
    ("Plant by abc", None), ("Plant by M/s Xy", None), ("", None), (None, None),
    ("Plant by Abcd at site", "Abcd"),
])
def test_extract_company(V, name, expected):
    assert V.extract_company(name) == expected


def test_extract_activity(V):
    props = json.dumps([{"label": "Other", "value": "x"}, {"label": "Activity", "value": "1(a) Mining"}])
    assert V.extract_activity(props) == "1(a) Mining"
    assert V.extract_activity(json.dumps([{"label": "Other", "value": "x"}])) is None
    assert V.extract_activity("not json") is None and V.extract_activity(None) is None and V.extract_activity("") is None
    assert V.extract_activity(12) is None


# ------------------------------------------------------------------ fetching
def test_fetch_proposals_builds_url_and_caches(V, repo, monkeypatch):
    seen = fake_urlopen(monkeypatch, {"status": 200, "data": [{"proposal_no": "1"}]})
    assert V.fetch_proposals() == [{"proposal_no": "1"}]
    url, timeout, ua = seen[0]
    assert url.startswith(V.BASE_URL + "?fromDate=2024-06-01&toDate=") and url.endswith("&status=Received&is_state=false")
    assert timeout == 90 and ua == "Mozilla/5.0"
    assert json.loads((repo / "data/raw/parivesh_proposals.json").read_text()) == [{"proposal_no": "1"}]


def test_fetch_proposals_non_200_exits(V, monkeypatch):
    fake_urlopen(monkeypatch, {"status": 500, "message": "boom"})
    with pytest.raises(SystemExit) as e:
        V.fetch_proposals()
    assert "status 500: boom" in str(e.value)


def test_load_proposals_falls_back_to_cache_or_exits(V, repo, monkeypatch, capsys):
    fake_urlopen(monkeypatch, error=OSError("offline"))
    with pytest.raises(SystemExit) as e:
        V.load_proposals()
    assert "no cache at" in str(e.value) and "offline" in str(e.value)
    (repo / "data/raw").mkdir(parents=True, exist_ok=True)
    (repo / "data/raw/parivesh_proposals.json").write_text(json.dumps([{"proposal_no": "9"}]))
    assert V.load_proposals() == [{"proposal_no": "9"}]
    assert "Live fetch failed (offline), using cached" in capsys.readouterr().out


# ------------------------------------------------------------------ main
def props(n, **kw):
    base = {"proposal_no": f"P{n}", "state_name": "GUJARAT", "status": "Received", "investment_cost": None, "project_name": "", "other_property": "[]", "start_date": "2025-01-02T10:00"}
    base.update(kw)
    return base


@pytest.fixture
def world(repo, monkeypatch):
    activity = json.dumps([{"label": "Activity", "value": "1(a) Mining"}])
    proposals = [
        props(1, investment_cost=900, project_name="Expansion by M/s Adani Power Ltd at Mundra", other_property=activity, status="EC Granted"),
        props(2, investment_cost=500, project_name="Plant by M/s Zed Corp Ltd", other_property=activity, state_name="goa"),
        props(3, investment_cost=700, project_name="Untitled plant", state_name="Kerala", status="Rejected"),
        props(3, investment_cost=1, project_name="duplicate payload for P3", state_name="Kerala"),            # same proposal_no: last one wins
        props(4, state_name="Lakshadweep", status="Granted ", other_property=json.dumps([{"label": "Activity", "value": "2(b) Ports"}])),
        props(5, state_name=None, status=None),
    ]
    fake_urlopen(monkeypatch, {"status": 200, "data": proposals})
    ms_cols = ["ministry", "questions"]
    write_csv(repo, "ministry_summary.csv", [dict(ministry="HEALTH", questions="4"), dict(ministry=ENV, questions="30")], ms_cols)
    write_csv(repo, "state_ministry_matrix.csv", [
        {"state": "Gujarat", ENV: "12"}, {"state": "Goa", ENV: "3"}, {"state": "Sikkim", ENV: "7"}, {"state": "Kerala", ENV: ""}, {"state": "Unknown", ENV: "1"}], ["state", ENV])
    write_csv(repo, "ls_questions_enriched.csv", [dict(subject="Query about Adani Power Ltd projects"), dict(subject="x")], ["subject"])
    write_csv(repo, "rs_questions_enriched.csv", [dict(subject="y", question_text="about ZED CORP LTD sites")], ["subject", "question_text"])
    return repo


def test_main_outputs(V, world, capsys):
    V.main()
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "PARIVESH: 5 distinct EC proposals since 2024-06-01 (2 in a 'granted' status)"
    assert out[1] == f"{ENV}: 30 PQs, 6.0x PQ per EC proposal"
    states = {r["state"]: r for r in read(world, "parivesh_state_comparison.csv")}
    assert states["Gujarat"] == {"state": "Gujarat", "environment_pqs": "12", "ec_proposals": "1", "pq_per_ec_proposal": "12.0"}
    assert states["Goa"]["ec_proposals"] == "1" and states["Goa"]["pq_per_ec_proposal"] == "3.0"
    assert states["Sikkim"] == {"state": "Sikkim", "environment_pqs": "7", "ec_proposals": "0", "pq_per_ec_proposal": ""}      # no proposals -> no ratio
    assert states["Kerala"]["environment_pqs"] == "0" and states["Kerala"]["ec_proposals"] == "1"                             # blank PQ cell counts as 0
    assert states["Lakshadweep"] == {"state": "Lakshadweep", "environment_pqs": "0", "ec_proposals": "1", "pq_per_ec_proposal": "0.0"}   # state unknown to PQ data is kept
    assert states["Unknown"]["ec_proposals"] == "1"
    order = [r["state"] for r in read(world, "parivesh_state_comparison.csv")]
    counts = [int(r["ec_proposals"]) for r in read(world, "parivesh_state_comparison.csv")]
    assert counts == sorted(counts, reverse=True) and order.index("Sikkim") == len(order) - 1
    act = read(world, "parivesh_activity_summary.csv")
    assert act == [{"activity": "1(a) Mining", "ec_proposals": "2"}, {"activity": "2(b) Ports", "ec_proposals": "1"}]
    mega = read(world, "parivesh_mega_projects.csv")
    assert [r["investment_cost_rs"] for r in mega] == ["900", "500", "1"]                          # the duplicate P3 payload replaced the first one
    by = {r["company"]: r for r in mega}
    assert by["Adani Power Ltd"]["company_mentioned_in_pq"] == "True" and by["Adani Power Ltd"]["state"] == "Gujarat" and by["Adani Power Ltd"]["start_date"] == "2025-01-02"
    assert by["Zed Corp Ltd"]["company_mentioned_in_pq"] == "True"                                  # case-insensitive substring over RS question_text
    assert by[""]["company_mentioned_in_pq"] == "" and by[""]["investment_cost_rs"] == "1"      # no company -> not counted as 'not mentioned'
    payload = json.loads((world / "site/parivesh.json").read_text())
    assert payload["total_ec_proposals"] == 5 and payload["granted_count"] == 2 and payload["pq_per_ec_proposal"] == 6.0 and payload["ministry_pq"] == 30
    assert payload["mega_projects_with_company"] == 2 and payload["mega_projects_mentioned"] == 2
    assert payload["top_activities"][0] == {"activity": "1(a) Mining", "ec_proposals": 2}
    assert out[2].startswith("Mega-project spot-check: 2/3 largest EC proposals name a company; 2 of those are mentioned")


def test_main_not_mentioned_company_and_no_proposals(V, repo, monkeypatch, capsys):
    fake_urlopen(monkeypatch, {"status": 200, "data": [props(1, investment_cost=10, project_name="Plant by M/s Ghost Industries Ltd")]})
    write_csv(repo, "ministry_summary.csv", [dict(ministry="HEALTH", questions="1")], ["ministry", "questions"])
    write_csv(repo, "state_ministry_matrix.csv", [], ["state"])
    write_csv(repo, "ls_questions_enriched.csv", [dict(subject="nothing")], ["subject"])
    write_csv(repo, "rs_questions_enriched.csv", [dict(subject="nothing", question_text="")], ["subject", "question_text"])
    V.main()
    mega = read(repo, "parivesh_mega_projects.csv")
    assert mega[0]["company_mentioned_in_pq"] == "False"
    assert json.loads((repo / "site/parivesh.json").read_text())["ministry_pq"] == 0           # ministry absent from the summary
    fake_urlopen(monkeypatch, {"status": 200, "data": []})
    V.main()
    assert json.loads((repo / "site/parivesh.json").read_text())["pq_per_ec_proposal"] is None
    assert "None" in capsys.readouterr().out
