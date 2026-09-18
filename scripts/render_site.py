"""Inject data.json / graph.json into site/template.html -> site/index.html."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

template = (SITE / "template.html").read_text()
data_json = (SITE / "data.json").read_text()
graph_json = (SITE / "graph.json").read_text()
pib_path = SITE / "pib.json"
pib_json = pib_path.read_text() if pib_path.exists() else '{"since": null, "ministry_comparison": [], "scheme_comparison": [], "note": "PIB comparison not run for this build."}'
pli_path = SITE / "pli.json"
pli_json = pli_path.read_text() if pli_path.exists() else '{"retrieved": null, "grade_criteria": "", "rows": [], "note": "PLI comparison not run for this build."}'
meity_path = SITE / "meity.json"
meity_json = meity_path.read_text() if meity_path.exists() else '{"source_url": "", "rows": [], "note": "MeitY comparison not run for this build."}'
parivesh_path = SITE / "parivesh.json"
parivesh_json = parivesh_path.read_text() if parivesh_path.exists() else '{"since": null, "ministry": "", "ministry_pq": 0, "total_ec_proposals": 0, "granted_count": 0, "pq_per_ec_proposal": null, "state_rows": [], "mega_projects": [], "note": "PARIVESH comparison not run for this build."}'

out = (
    template.replace("{{DATA_JSON}}", data_json)
    .replace("{{GRAPH_JSON}}", graph_json)
    .replace("{{PIB_JSON}}", pib_json)
    .replace("{{PLI_JSON}}", pli_json)
    .replace("{{MEITY_JSON}}", meity_json)
    .replace("{{PARIVESH_JSON}}", parivesh_json)
)
(SITE / "index.html").write_text(out)
print("wrote", SITE / "index.html", len(out), "bytes")
