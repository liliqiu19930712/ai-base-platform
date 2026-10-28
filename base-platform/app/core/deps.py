from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db import get_db
from app.models import PlatformAdmin, User, UserTenantRel
from app.services.rbac import assert_permission, get_user_permissions


class CurrentUser:
    def __init__(
        self,
        user_id: str,
        username: str,
        tenant_id: str | None = None,
        is_platform_admin: bool = False,
        permissions: set[str] | None = None,
    ):
        self.user_id = user_id
        self.username = username
        self.tenant_id = tenant_id
        self.is_platform_admin = is_platform_admin
        self.permissions = permissions or set()


def get_current_user(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("AUTH_REQUIRED", "缺少 Bearer Token", 401)
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise AppError("AUTH_INVALID", str(exc), 401) from exc

    user_id = payload.get("sub")
    username = payload.get("username")
    if not user_id or not username:
        raise AppError("AUTH_INVALID", "token 载荷无效", 401)

    user = db.get(User, user_id)
    if not user:
        raise AppError("AUTH_INVALID", "用户不存在", 401)
    if getattr(user, "status", "active") == "disabled":
        raise AppError("USER_DISABLED", "账号已停用", 403)

    is_admin = db.get(PlatformAdmin, user_id) is not None
    tenant_id = x_tenant_id or payload.get("tenant_id")
    if tenant_id and not is_admin:
        rel = (
            db.query(UserTenantRel)
            .filter(UserTenantRel.user_id == user_id, UserTenantRel.tenant_id == tenant_id)
            .first()
        )
        if not rel:
            raise AppError("TENANT_FORBIDDEN", "当前用户无权访问该租户", 403)

    perms = get_user_permissions(db, user_id, tenant_id)
    return CurrentUser(
        user_id=user_id,
        username=username,
        tenant_id=tenant_id,
        is_platform_admin=is_admin,
        permissions=perms,
    )


def require_tenant(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.tenant_id:
        raise AppError("TENANT_REQUIRED", "请在 Header 中传入 X-Tenant-Id", 400)
    return user


def require_platform_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_platform_admin:
        raise AppError("ADMIN_FORBIDDEN", "需要基座平台管理员权限", 403)
    return user


def require_perm(perm: str):
    def _inner(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)) -> CurrentUser:
        if user.is_platform_admin:
            return user
        assert_permission(db, user.user_id, user.tenant_id, perm)
        return user

    return _inner
