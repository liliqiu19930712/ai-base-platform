from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import ok
from app.db import get_db
from app.models import ChatMessage, ChatSession, ModelCallLog
from app.services.audit import list_audits

router = APIRouter(prefix="/log", tags=["审计日志"])


@router.get("/model-call/list")
def list_model_call_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    q = (
        db.query(ModelCallLog)
        .filter(ModelCallLog.tenant_id == user.tenant_id)
        .order_by(ModelCallLog.call_time.desc())
    )
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    items = [
        {
            "log_id": r.log_id,
            "tenant_id": r.tenant_id,
            "agent_id": r.agent_id,
            "user_id": r.user_id,
            "model_id": r.model_id,
            "input_snippet": r.input_snippet,
            "output_snippet": r.output_snippet,
            "token_used": r.token_used,
            "status": r.status,
            "cost": r.cost,
            "call_time": r.call_time.isoformat() + "Z",
        }
        for r in rows
    ]
    return ok({"total": total, "page": page, "page_size": page_size, "items": items})


@router.get("/audit/list")
def audit_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_perm("audit:read")),
    db: Session = Depends(get_db),
):
    tenant_id = None if user.is_platform_admin else user.tenant_id
    return ok(list_audits(db, tenant_id=tenant_id, page=page, page_size=page_size))


@router.get("/sessions")
def list_sessions(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = (
        db.query(ChatSession)
        .filter(ChatSession.tenant_id == user.tenant_id, ChatSession.user_id == user.user_id)
        .order_by(ChatSession.create_time.desc())
        .limit(50)
        .all()
    )
    return ok(
        [
            {
                "session_id": r.session_id,
                "agent_id": r.agent_id,
                "title": r.title,
                "create_time": r.create_time.isoformat() + "Z" if r.create_time else None,
            }
            for r in rows
        ]
    )


@router.get("/sessions/{session_id}/messages")
def session_messages(
    session_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    session = db.get(ChatSession, session_id)
    if not session or session.tenant_id != user.tenant_id:
        return ok([])
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.create_time.asc())
        .all()
    )
    return ok(
        [
            {
                "msg_id": r.msg_id,
                "role": r.role,
                "content": r.content,
                "create_time": r.create_time.isoformat() + "Z" if r.create_time else None,
            }
            for r in rows
        ]
    )
