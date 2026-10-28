from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user
from app.core.errors import AppError, ok
from app.core.security import create_access_token, verify_password
from app.db import get_db
from app.models import PlatformAdmin, Role, Tenant, User, UserTenantRel
from app.schemas.common import LoginRequest

router = APIRouter(prefix="/auth", tags=["身份鉴权"])


def _tenant_item(tenant: Tenant) -> dict:
    return {
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.tenant_name,
        "tenant_desc": tenant.tenant_desc,
        "status": tenant.status,
    }


@router.get("/active-tenants")
def active_tenants(db: Session = Depends(get_db)):
    """登录页下拉：返回全部启用中的租户（无需登录）。"""
    rows = (
        db.query(Tenant)
        .filter(Tenant.status == "active")
        .order_by(Tenant.create_time.desc())
        .all()
    )
    return ok([_tenant_item(t) for t in rows])


@router.get("/login-tenants")
def login_tenants(username: str = Query("", description="用户名"), db: Session = Depends(get_db)):
    """按用户名返回可选租户；未填用户名时返回全部启用租户。"""
    username = (username or "").strip()
    if not username:
        rows = (
            db.query(Tenant)
            .filter(Tenant.status == "active")
            .order_by(Tenant.create_time.desc())
            .all()
        )
        return ok([_tenant_item(t) for t in rows])

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return ok([])

    if db.get(PlatformAdmin, user.user_id):
        rows = (
            db.query(Tenant)
            .filter(Tenant.status == "active")
            .order_by(Tenant.create_time.desc())
            .all()
        )
        return ok([_tenant_item(t) for t in rows])

    items = []
    rels = db.query(UserTenantRel).filter(UserTenantRel.user_id == user.user_id).all()
    for rel in rels:
        tenant = db.get(Tenant, rel.tenant_id)
        if tenant and tenant.status == "active":
            items.append(_tenant_item(tenant))
    return ok(items)


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise AppError("LOGIN_FAILED", "用户名或密码错误", 401)
    if getattr(user, "status", "active") == "disabled":
        raise AppError("USER_DISABLED", "账号已停用", 403)

    is_platform_admin = db.get(PlatformAdmin, user.user_id) is not None
    rels = db.query(UserTenantRel).filter(UserTenantRel.user_id == user.user_id).all()

    tenant_id = body.tenant_id
    if is_platform_admin:
        # 平台管理员可不选租户，直接进入管理后台
        if tenant_id and not any(r.tenant_id == tenant_id for r in rels):
            # 允许管理员切换查看任意租户上下文
            pass
        if not tenant_id and rels:
            tenant_id = rels[0].tenant_id
    else:
        if not rels:
            raise AppError("NO_TENANT", "用户未绑定任何租户", 403)
        tenant_id = tenant_id or rels[0].tenant_id
        if not any(r.tenant_id == tenant_id for r in rels):
            raise AppError("TENANT_FORBIDDEN", "无权访问该租户", 403)

    payload = {"sub": user.user_id, "username": user.username}
    if tenant_id:
        payload["tenant_id"] = tenant_id
    token = create_access_token(payload)
    return ok(
        {
            "access_token": token,
            "token_type": "Bearer",
            "tenant_id": tenant_id,
            "user_id": user.user_id,
            "username": user.username,
            "is_platform_admin": is_platform_admin,
        }
    )


@router.get("/user-info")
def user_info(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.user_id)
    roles = []
    if user.tenant_id:
        rel = (
            db.query(UserTenantRel)
            .filter(UserTenantRel.user_id == user.user_id, UserTenantRel.tenant_id == user.tenant_id)
            .first()
        )
        if rel and rel.role_ids:
            for rid in rel.role_ids.split(","):
                role = db.get(Role, rid.strip())
                if role:
                    roles.append({"role_id": role.role_id, "role_name": role.role_name})
    return ok(
        {
            "user_id": u.user_id,
            "username": u.username,
            "email": u.email,
            "phone": u.phone,
            "tenant_id": user.tenant_id,
            "roles": roles,
            "permissions": sorted(user.permissions),
            "is_platform_admin": user.is_platform_admin,
        }
    )


@router.get("/tenant-list")
def tenant_list(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rels = db.query(UserTenantRel).filter(UserTenantRel.user_id == user.user_id).all()
    items = []
    for rel in rels:
        tenant = db.get(Tenant, rel.tenant_id)
        if tenant:
            items.append(
                {
                    "tenant_id": tenant.tenant_id,
                    "tenant_name": tenant.tenant_name,
                    "tenant_desc": tenant.tenant_desc,
                    "status": tenant.status,
                }
            )
    return ok(items)


# ---------- SSO ----------
from pydantic import BaseModel, Field

from app.services import sso as sso_svc


class SsoTicketRequest(BaseModel):
    redirect_uri: str = ""
    tenant_id: str | None = None


class SsoExchangeRequest(BaseModel):
    ticket: str


@router.post("/sso/ticket")
def sso_ticket(
    body: SsoTicketRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = sso_svc.issue_ticket(
        db,
        user_id=user.user_id,
        tenant_id=body.tenant_id or user.tenant_id or "",
        redirect_uri=body.redirect_uri,
    )
    return ok(data, message="SSO 票据已签发")


@router.post("/sso/exchange")
def sso_exchange(body: SsoExchangeRequest, db: Session = Depends(get_db)):
    return ok(sso_svc.exchange_ticket(db, body.ticket), message="SSO 登录成功")


@router.get("/sso/wecom/authorize")
def wecom_authorize(redirect_uri: str = Query(""), state: str = Query("culture")):
    return ok(sso_svc.wecom_authorize_url(state=state, redirect_uri=redirect_uri))


@router.get("/sso/wecom/mock-callback")
async def wecom_mock_callback(
    state: str = Query("culture"),
    redirect_uri: str = Query(""),
    code: str = Query("mockuser"),
    tenant_id: str = Query(""),
    db: Session = Depends(get_db),
):
    data = await sso_svc.wecom_exchange_code(db, code=code or state, tenant_id=tenant_id)
    if redirect_uri:
        data["next"] = redirect_uri
    return ok(data, message="企业微信 mock SSO 成功")


@router.get("/sso/wecom/callback")
async def wecom_callback(
    code: str = Query(""),
    state: str = Query(""),
    tenant_id: str = Query(""),
    db: Session = Depends(get_db),
):
    data = await sso_svc.wecom_exchange_code(db, code=code, tenant_id=tenant_id)
    data["state"] = state
    return ok(data, message="企业微信 SSO 成功")
