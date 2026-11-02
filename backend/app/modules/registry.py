"""Domain routers are registered here so main.py stays small. Each module is a bounded context of the modular monolith."""
import importlib

MODULES = ["knowledge", "chat", "agents", "workflows", "data", "tasks", "billing", "integrations", "analytics", "admin", "public", "experiments"]


def routers():
    out = []
    for name in MODULES:
        try:
            mod = importlib.import_module(f"app.modules.{name}")
        except ModuleNotFoundError as e:
            if e.name == f"app.modules.{name}":
                continue
            raise
        out.extend(getattr(mod, "ROUTERS", [mod.router]))
    return out
