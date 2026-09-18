"""Inject data.json / graph.json into site/template.html -> site/index.html."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

template = (SITE / "template.html").read_text()
data_json = (SITE / "data.json").read_text()
graph_json = (SITE / "graph.json").read_text()

out = template.replace("{{DATA_JSON}}", data_json).replace("{{GRAPH_JSON}}", graph_json)
(SITE / "index.html").write_text(out)
print("wrote", SITE / "index.html", len(out), "bytes")
