from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_platform_admin
from app.core.errors import AppError, ok
from app.db import get_db
from app.models import Tenant
from app.schemas.common import (
    AdminQuotaUpsertRequest,
    AdminTenantCreateRequest,
    AdminTenantUpdateRequest,
)
from app.services import tenant_admin as svc

router = APIRouter(prefix="/admin", tags=["基座管理后台"])


@router.get("/tenants")
def list_tenants(
    _: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(Tenant).order_by(Tenant.create_time.desc()).all()
    return ok([svc.serialize_tenant(db, t) for t in rows])


@router.get("/tenants/{tenant_id}")
def get_tenant(
    tenant_id: str,
    _: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise AppError("TENANT_NOT_FOUND", "租户不存在", 404)
    return ok(svc.serialize_tenant(db, tenant))


@router.post("/tenants")
def create_tenant(
    body: AdminTenantCreateRequest,
    _: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    data = svc.create_tenant(
        db,
        tenant_id=body.tenant_id,
        tenant_name=body.tenant_name,
        tenant_desc=body.tenant_desc,
        enable_gateway=body.enable_gateway,
        enable_kb=body.enable_kb,
        enable_workflow=body.enable_workflow,
        enable_plugin=body.enable_plugin,
        default_quota_limit=body.default_quota_limit,
        default_agent_id=body.default_agent_id,
        admin_username=body.admin_username,
        admin_password=body.admin_password,
        admin_email=body.admin_email,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
    )
    return ok(data, message="租户创建成功")


@router.patch("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: str,
    body: AdminTenantUpdateRequest,
    _: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    data = svc.update_tenant(
        db,
        tenant_id,
        tenant_name=body.tenant_name,
        tenant_desc=body.tenant_desc,
        status=body.status,
        enable_gateway=body.enable_gateway,
        enable_kb=body.enable_kb,
        enable_workflow=body.enable_workflow,
        enable_plugin=body.enable_plugin,
        default_quota_limit=body.default_quota_limit,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
    )
    return ok(data, message="租户已更新")


@router.post("/tenants/{tenant_id}/quota")
def upsert_quota(
    tenant_id: str,
    body: AdminQuotaUpsertRequest,
    _: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    data = svc.upsert_quota(db, tenant_id, body.agent_id, body.limit_value)
    return ok(data, message="配额已更新")


@router.post("/tenants/{tenant_id}/rotate-credential")
def rotate_credential(
    tenant_id: str,
    _: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    if not db.get(Tenant, tenant_id):
        raise AppError("TENANT_NOT_FOUND", "租户不存在", 404)
    return ok(svc.rotate_credential(db, tenant_id), message="凭证已轮换")
