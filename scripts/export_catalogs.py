"""Regenerate the JSON snapshots of agent templates, workflow recipes and the integration catalogue."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agents.templates import TEMPLATES  # noqa: E402
from app.agents.tools import tool_catalog  # noqa: E402
from app.workflows.templates import WORKFLOW_TEMPLATES  # noqa: E402
from app.integrations.providers import CATALOG  # noqa: E402
(ROOT / "agent-workflows/templates.json").write_text(json.dumps({"agent_templates": TEMPLATES, "tools": tool_catalog()}, indent=2))
(ROOT / "automation/workflow-recipes.json").write_text(json.dumps(WORKFLOW_TEMPLATES, indent=2))
(ROOT / "integrations/catalog.json").write_text(json.dumps(CATALOG, indent=2))
print("ok")
