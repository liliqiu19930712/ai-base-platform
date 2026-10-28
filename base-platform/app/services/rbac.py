import json

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import PlatformAdmin, Role, UserTenantRel


def get_user_permissions(db: Session, user_id: str, tenant_id: str | None) -> set[str]:
    if db.get(PlatformAdmin, user_id):
        return {"*"}
    if not tenant_id:
        return set()
    rel = (
        db.query(UserTenantRel)
        .filter(UserTenantRel.user_id == user_id, UserTenantRel.tenant_id == tenant_id)
        .first()
    )
    if not rel or not rel.role_ids:
        return set()
    perms: set[str] = set()
    for rid in rel.role_ids.split(","):
        role = db.get(Role, rid.strip())
        if not role:
            continue
        try:
            keys = json.loads(role.permission_json or "[]")
        except json.JSONDecodeError:
            keys = []
        for k in keys:
            perms.add(str(k))
    return perms


def assert_permission(db: Session, user_id: str, tenant_id: str | None, perm: str) -> None:
    perms = get_user_permissions(db, user_id, tenant_id)
    if "*" in perms or perm in perms:
        return
    # 兼容：管理员角色默认放行常用能力
    if "tenant:admin" in perms:
        return
    raise AppError("PERM_DENIED", f"缺少权限: {perm}", 403)
