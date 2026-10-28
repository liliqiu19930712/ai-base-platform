import json
import secrets

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ids import new_id
from app.core.security import hash_password
from app.models import (
    AgentQuota,
    AgentRegistry,
    ComplianceConfig,
    PlatformAdmin,
    Role,
    Tenant,
    TenantFeature,
    User,
    UserTenantRel,
)
from app.models.tables import now


def is_platform_admin(db: Session, user_id: str) -> bool:
    return db.get(PlatformAdmin, user_id) is not None


def ensure_feature(db: Session, tenant_id: str) -> TenantFeature:
    feature = db.get(TenantFeature, tenant_id)
    if feature:
        return feature
    feature = TenantFeature(
        tenant_id=tenant_id,
        enable_gateway=True,
        enable_kb=True,
        enable_workflow=True,
        enable_plugin=True,
        default_quota_limit=100000,
        api_credential=secrets.token_urlsafe(16),
    )
    db.add(feature)
    db.commit()
    db.refresh(feature)
    return feature


def assert_feature_enabled(db: Session, tenant_id: str, feature_name: str) -> TenantFeature:
    tenant = db.get(Tenant, tenant_id)
    if not tenant or tenant.status != "active":
        raise AppError("TENANT_DISABLED", "租户不存在或已停用", 403)
    feature = ensure_feature(db, tenant_id)
    mapping = {
        "gateway": feature.enable_gateway,
        "kb": feature.enable_kb,
        "workflow": feature.enable_workflow,
        "plugin": feature.enable_plugin,
    }
    if feature_name not in mapping:
        raise AppError("FEATURE_UNKNOWN", f"未知能力: {feature_name}")
    if not mapping[feature_name]:
        raise AppError("FEATURE_DISABLED", f"租户未开通能力: {feature_name}", 403)
    return feature


def serialize_tenant(db: Session, tenant: Tenant) -> dict:
    feature = ensure_feature(db, tenant.tenant_id)
    quotas = db.query(AgentQuota).filter(AgentQuota.tenant_id == tenant.tenant_id).all()
    admin_rels = (
        db.query(UserTenantRel, User)
        .join(User, User.user_id == UserTenantRel.user_id)
        .filter(UserTenantRel.tenant_id == tenant.tenant_id)
        .all()
    )
    admins = []
    for rel, user in admin_rels:
        role_ids = rel.role_ids or ""
        is_admin = False
        for rid in [x.strip() for x in role_ids.split(",") if x.strip()]:
            role = db.get(Role, rid)
            if role and (role.role_name == "管理员" or "admin" in rid):
                is_admin = True
                break
        if is_admin or "admin" in role_ids:
            admins.append({"user_id": user.user_id, "username": user.username, "email": user.email})
    return {
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.tenant_name,
        "tenant_desc": tenant.tenant_desc,
        "status": tenant.status,
        "create_time": tenant.create_time.isoformat() + "Z" if tenant.create_time else None,
        "features": {
            "enable_gateway": feature.enable_gateway,
            "enable_kb": feature.enable_kb,
            "enable_workflow": feature.enable_workflow,
            "enable_plugin": feature.enable_plugin,
            "default_quota_limit": feature.default_quota_limit,
            "api_credential": feature.api_credential,
            "contact_name": feature.contact_name,
            "contact_email": feature.contact_email,
        },
        "quotas": [
            {
                "agent_id": q.agent_id,
                "limit_value": q.limit_value,
                "used_value": q.used_value,
                "quota_type": q.quota_type,
            }
            for q in quotas
        ],
        "admins": admins,
    }


def create_tenant(
    db: Session,
    *,
    tenant_id: str | None,
    tenant_name: str,
    tenant_desc: str = "",
    enable_gateway: bool = True,
    enable_kb: bool = True,
    enable_workflow: bool = True,
    enable_plugin: bool = True,
    default_quota_limit: int = 100000,
    default_agent_id: str = "default_agent",
    admin_username: str,
    admin_password: str,
    admin_email: str = "",
    contact_name: str = "",
    contact_email: str = "",
) -> dict:
    tid = (tenant_id or "").strip() or f"tenant_{new_id()}"
    if db.get(Tenant, tid):
        raise AppError("TENANT_EXISTS", f"租户已存在: {tid}", 409)
    if db.query(User).filter(User.username == admin_username).first():
        raise AppError("USER_EXISTS", f"管理员用户名已存在: {admin_username}", 409)
    if default_quota_limit <= 0:
        raise AppError("INVALID_QUOTA", "默认配额必须大于 0")

    tenant = Tenant(
        tenant_id=tid,
        tenant_name=tenant_name.strip(),
        tenant_desc=tenant_desc.strip(),
        status="active",
    )
    credential = secrets.token_urlsafe(16)
    feature = TenantFeature(
        tenant_id=tid,
        enable_gateway=enable_gateway,
        enable_kb=enable_kb,
        enable_workflow=enable_workflow,
        enable_plugin=enable_plugin,
        default_quota_limit=default_quota_limit,
        api_credential=credential,
        contact_name=contact_name,
        contact_email=contact_email or admin_email,
        update_time=now(),
    )
    role = Role(
        role_id=f"role_{tid}_admin",
        tenant_id=tid,
        role_name="管理员",
        permission_json=json.dumps(
            [
                "gateway:invoke",
                "kb:manage",
                "workflow:manage",
                "plugin:manage",
                "audit:read",
                "tenant:admin",
            ]
        ),
    )
    user = User(
        user_id=new_id("user_"),
        username=admin_username.strip(),
        password_hash=hash_password(admin_password),
        email=admin_email,
        status="active",
    )
    rel = UserTenantRel(
        rel_id=new_id("rel_"),
        user_id=user.user_id,
        tenant_id=tid,
        role_ids=role.role_id,
    )
    agent_id = default_agent_id.strip() or "default_agent"
    agent = AgentRegistry(
        reg_id=new_id("reg_"),
        agent_id=agent_id,
        tenant_id=tid,
        agent_name=f"{tenant_name.strip()}-默认智能体",
        description="租户创建时自动登记",
        default_model_id="mock-gpt",
        status="active",
    )
    quota = AgentQuota(
        quota_id=new_id("qt_"),
        tenant_id=tid,
        agent_id=agent_id,
        quota_type="token_month",
        limit_value=default_quota_limit,
        used_value=0,
        reset_cycle="month",
    )
    compliance = ComplianceConfig(
        config_id=new_id("cmp_"),
        tenant_id=tid,
        title="合规免责提示",
        content=f"【{tenant_name.strip()}】本智能体输出仅供参考，不构成专业意见。业务合规由子平台负责。",
        mask_phone=True,
        mask_id_card=True,
        mask_email=True,
    )
    db.add_all([tenant, feature, role, user, rel, agent, quota, compliance])
    db.commit()
    return {
        **serialize_tenant(db, tenant),
        "initial_admin": {
            "username": admin_username,
            "password": admin_password,
            "note": "请妥善保管并通知子平台负责人尽快修改密码",
        },
    }


def update_tenant(
    db: Session,
    tenant_id: str,
    *,
    tenant_name: str | None = None,
    tenant_desc: str | None = None,
    status: str | None = None,
    enable_gateway: bool | None = None,
    enable_kb: bool | None = None,
    enable_workflow: bool | None = None,
    enable_plugin: bool | None = None,
    default_quota_limit: int | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
) -> dict:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise AppError("TENANT_NOT_FOUND", "租户不存在", 404)
    feature = ensure_feature(db, tenant_id)

    if tenant_name is not None:
        tenant.tenant_name = tenant_name.strip()
    if tenant_desc is not None:
        tenant.tenant_desc = tenant_desc.strip()
    if status is not None:
        if status not in {"active", "disabled"}:
            raise AppError("INVALID_STATUS", "status 仅支持 active/disabled")
        tenant.status = status
    if enable_gateway is not None:
        feature.enable_gateway = enable_gateway
    if enable_kb is not None:
        feature.enable_kb = enable_kb
    if enable_workflow is not None:
        feature.enable_workflow = enable_workflow
    if enable_plugin is not None:
        feature.enable_plugin = enable_plugin
    if default_quota_limit is not None:
        if default_quota_limit <= 0:
            raise AppError("INVALID_QUOTA", "默认配额必须大于 0")
        feature.default_quota_limit = default_quota_limit
    if contact_name is not None:
        feature.contact_name = contact_name
    if contact_email is not None:
        feature.contact_email = contact_email
    feature.update_time = now()
    db.add(tenant)
    db.add(feature)
    db.commit()
    db.refresh(tenant)
    return serialize_tenant(db, tenant)


def upsert_quota(db: Session, tenant_id: str, agent_id: str, limit_value: int) -> dict:
    from app.services.quota import register_or_update_quota

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise AppError("TENANT_NOT_FOUND", "租户不存在", 404)
    feature = ensure_feature(db, tenant_id)
    quota = register_or_update_quota(db, tenant_id, agent_id, limit_value)
    feature.default_quota_limit = limit_value
    feature.update_time = now()
    db.add(feature)
    db.commit()
    return {
        "tenant_id": tenant_id,
        "agent_id": quota.agent_id,
        "limit_value": quota.limit_value,
        "used_value": quota.used_value,
    }


def rotate_credential(db: Session, tenant_id: str) -> dict:
    feature = ensure_feature(db, tenant_id)
    feature.api_credential = secrets.token_urlsafe(16)
    feature.update_time = now()
    db.add(feature)
    db.commit()
    return {"tenant_id": tenant_id, "api_credential": feature.api_credential}
