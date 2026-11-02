"""Role-based access control. Roles are ordered; permissions map to the minimum role that holds them."""
ROLE_RANK = {"viewer": 10, "member": 20, "manager": 30, "admin": 40, "owner": 50}

PERMISSIONS: dict[str, str] = {
    "org.read": "viewer",
    "org.update": "admin",
    "org.delete": "owner",
    "members.read": "viewer",
    "members.invite": "admin",
    "members.manage": "admin",
    "workspaces.write": "admin",
    "chat.use": "member",
    "documents.read": "viewer",
    "documents.write": "member",
    "documents.delete": "manager",
    "agents.read": "viewer",
    "agents.write": "manager",
    "agents.run": "member",
    "approvals.decide": "manager",
    "workflows.read": "viewer",
    "workflows.write": "manager",
    "workflows.run": "member",
    "datasets.read": "viewer",
    "datasets.write": "member",
    "tasks.read": "viewer",
    "tasks.write": "member",
    "analytics.read": "manager",
    "billing.read": "admin",
    "billing.manage": "owner",
    "integrations.read": "member",
    "integrations.manage": "admin",
    "audit.read": "admin",
}


def role_at_least(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]


def has_permission(role: str, permission: str) -> bool:
    minimum = PERMISSIONS.get(permission)
    if minimum is None:
        return False  # deny unknown permissions by default
    return role_at_least(role, minimum)


def permissions_for(role: str) -> list[str]:
    return sorted(p for p in PERMISSIONS if has_permission(role, p))
