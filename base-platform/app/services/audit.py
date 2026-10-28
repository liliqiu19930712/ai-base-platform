import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.models import AuditLog


def write_audit(
    db: Session,
    *,
    action: str,
    tenant_id: str = "",
    user_id: str = "",
    resource: str = "",
    detail: Any = None,
    ip: str = "",
) -> AuditLog:
    if isinstance(detail, (dict, list)):
        detail_text = json.dumps(detail, ensure_ascii=False)[:2000]
    else:
        detail_text = str(detail or "")[:2000]
    row = AuditLog(
        audit_id=new_id("aud_"),
        tenant_id=tenant_id or "",
        user_id=user_id or "",
        action=action,
        resource=resource or "",
        detail=detail_text,
        ip=ip or "",
    )
    db.add(row)
    db.commit()
    return row


def list_audits(
    db: Session,
    *,
    tenant_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    q = db.query(AuditLog).filter(AuditLog.deleted.is_(False))
    if tenant_id:
        q = q.filter(AuditLog.tenant_id == tenant_id)
    total = q.count()
    rows = q.order_by(AuditLog.create_time.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "audit_id": r.audit_id,
                "tenant_id": r.tenant_id,
                "user_id": r.user_id,
                "action": r.action,
                "resource": r.resource,
                "detail": r.detail,
                "ip": r.ip,
                "create_time": r.create_time.isoformat() + "Z" if r.create_time else None,
            }
            for r in rows
        ],
    }
