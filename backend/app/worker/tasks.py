"""Job handlers. Imported for side-effect registration."""
import importlib
from app.worker.queue import handler  # noqa: F401

for _m in ["app.rag.indexing", "app.agents.runtime", "app.workflows.service", "app.worker.misc"]:
    try:
        importlib.import_module(_m)
    except ModuleNotFoundError as e:
        if e.name != _m:
            raise
