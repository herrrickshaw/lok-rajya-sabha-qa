"""scripts/render_site.py and scripts/build_xlsx.py on tiny synthetic inputs."""
import csv

import pytest

from conftest import run_script


# ------------------------------------------------------------------ render_site
def site(repo, **files):
    for name, text in files.items():
        (repo / "site" / name).write_text(text)


def test_render_site_injects_every_payload(repo, capsys):
    site(repo, **{"template.html": "<a>{{DATA_JSON}}</a><b>{{GRAPH_JSON}}</b><c>{{PIB_JSON}}</c><d>{{PLI_JSON}}</d><e>{{MEITY_JSON}}</e><f>{{PARIVESH_JSON}}</f>",
                  "data.json": "D", "graph.json": "G", "pib.json": "P", "pli.json": "L", "meity.json": "M", "parivesh.json": "V"})
    run_script("render_site")
    assert (repo / "site/index.html").read_text() == "<a>D</a><b>G</b><c>P</c><d>L</d><e>M</e><f>V</f>"
    assert capsys.readouterr().out.strip() == f"wrote {repo / 'site/index.html'} 48 bytes"


def test_render_site_uses_placeholders_for_missing_optional_payloads(repo):
    site(repo, **{"template.html": "{{PIB_JSON}}|{{PLI_JSON}}|{{MEITY_JSON}}|{{PARIVESH_JSON}}|{{DATA_JSON}}|{{GRAPH_JSON}}", "data.json": "{}", "graph.json": "{}"})
    run_script("render_site")
    pib, pli, meity, pv, d, g = (repo / "site/index.html").read_text().split("|")
    import json
    assert json.loads(pib)["note"] == "PIB comparison not run for this build." and json.loads(pib)["ministry_comparison"] == []
    assert json.loads(pli)["note"] == "PLI comparison not run for this build." and json.loads(pli)["rows"] == []
    assert json.loads(meity)["note"] == "MeitY comparison not run for this build."
    assert json.loads(pv)["note"] == "PARIVESH comparison not run for this build." and json.loads(pv)["state_rows"] == []
    assert (d, g) == ("{}", "{}")


def test_render_site_repeated_placeholder_replaced_everywhere(repo):
    site(repo, **{"template.html": "{{DATA_JSON}} {{DATA_JSON}}", "data.json": "X", "graph.json": ""})
    run_script("render_site")
    assert (repo / "site/index.html").read_text() == "X X"


def test_render_site_needs_template(repo):
    with pytest.raises(FileNotFoundError):
        run_script("render_site")


# ------------------------------------------------------------------ build_xlsx
def write_csv(repo, name, rows, cols):
    p = repo / "data/processed" / name
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def test_build_xlsx_sheets_styles_and_cover(repo, capsys):
    from openpyxl import load_workbook
    write_csv(repo, "party_summary.csv", [dict(party="BJP", total_questions=10), dict(party="X" * 80, total_questions=1)], ["party", "total_questions"])
    write_csv(repo, "ls_questions_enriched.csv", [dict(subject="s", member="m")], ["subject", "member"])
    run_script("build_xlsx")
    path = repo / "Lok_Rajya_Sabha_PQ_Analysis.xlsx"
    wb = load_workbook(path)
    names = wb.sheetnames
    assert names[0] == "Read Me" and len(names) == 22 and names[1] == "Party Ranking" and names[-1] == "RS Questions (raw)"
    assert wb["Read Me"]["A1"].value.startswith("Lok & Rajya Sabha") and wb["Read Me"]["A1"].font.bold and wb["Read Me"]["A1"].font.size == 14
    assert wb["Read Me"]["A3"].font.bold is False and wb["Read Me"].column_dimensions["A"].width == 100
    ws = wb["Party Ranking"]
    assert [c.value for c in ws[1]] == ["party", "total_questions"]
    assert ws["A1"].fill.fgColor.rgb.endswith("1D1A14") and ws["A1"].font.bold and ws["A1"].font.color.rgb.endswith("FFFFFF")
    assert ws["A2"].value == "BJP" and ws["A2"].font.name == "Arial" and ws["A2"].font.size == 10
    assert ws.freeze_panes == "A2" and ws.auto_filter.ref == "A1:B3"
    assert ws.column_dimensions["A"].width == 42 and ws.column_dimensions["B"].width == 17          # capped at 42; len('total_questions') + 2 = 17
    assert wb["Ministry Ranking"].max_row == 1 and wb["Ministry Ranking"].max_column == 1          # missing CSV -> empty sheet
    assert wb["LS Questions (raw)"]["B2"].value == "m"
    assert capsys.readouterr().out.startswith(f"Wrote {path} ")


def test_build_xlsx_column_width_floor_and_sheet_name_limit(repo):
    from openpyxl import load_workbook
    write_csv(repo, "kg_mp_coasking_bridges.csv", [dict(a="x")], ["a"])
    write_csv(repo, "pib_ministry_comparison.csv", [dict(a="y")], ["a"])
    run_script("build_xlsx")
    wb = load_workbook(repo / "Lok_Rajya_Sabha_PQ_Analysis.xlsx")
    assert wb["KG Cross-Party Bridges"].column_dimensions["A"].width == 9                           # minimum width
    assert all(len(n) <= 31 for n in wb.sheetnames)
