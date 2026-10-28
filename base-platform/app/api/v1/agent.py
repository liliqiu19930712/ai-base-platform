from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import AppError, ok
from app.db import get_db
from app.models import AgentRegistry
from app.services import agent_svc
from app.services.audit import write_audit

router = APIRouter(prefix="/agent", tags=["智能体实例"])


class AgentCreateRequest(BaseModel):
    agent_id: str | None = None
    agent_name: str
    description: str = ""
    default_model_id: str = "mock-gpt"
    quota_limit: int = 100000


class AgentUpdateRequest(BaseModel):
    agent_name: str | None = None
    description: str | None = None
    default_model_id: str | None = None
    status: str | None = None
    quota_limit: int | None = None


@router.get("/list")
def list_agents(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    return ok(agent_svc.list_agents(db, user.tenant_id))


@router.post("/register")
def register_agent(
    body: AgentCreateRequest,
    user: CurrentUser = Depends(require_perm("tenant:admin")),
    db: Session = Depends(get_db),
):
    data = agent_svc.register_agent(
        db,
        tenant_id=user.tenant_id,
        agent_id=body.agent_id,
        agent_name=body.agent_name,
        description=body.description,
        default_model_id=body.default_model_id,
        quota_limit=body.quota_limit,
    )
    write_audit(
        db,
        action="agent.register",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=data["agent_id"],
        detail=data,
    )
    return ok(data, message="智能体已登记")


@router.patch("/{agent_id}")
def update_agent(
    agent_id: str,
    body: AgentUpdateRequest,
    user: CurrentUser = Depends(require_perm("tenant:admin")),
    db: Session = Depends(get_db),
):
    row = (
        db.query(AgentRegistry)
        .filter(AgentRegistry.tenant_id == user.tenant_id, AgentRegistry.agent_id == agent_id)
        .first()
    )
    if not row:
        if body.agent_name:
            data = agent_svc.register_agent(
                db,
                tenant_id=user.tenant_id,
                agent_id=agent_id,
                agent_name=body.agent_name,
                description=body.description or "",
                default_model_id=body.default_model_id or "mock-gpt",
                quota_limit=body.quota_limit or 100000,
            )
            return ok(data)
        raise AppError("AGENT_NOT_FOUND", "智能体不存在", 404)
    if body.agent_name is not None:
        row.agent_name = body.agent_name
    if body.description is not None:
        row.description = body.description
    if body.default_model_id is not None:
        row.default_model_id = body.default_model_id
    if body.status is not None:
        if body.status not in {"active", "disabled"}:
            raise AppError("INVALID_STATUS", "status 仅支持 active/disabled")
        row.status = body.status
    db.add(row)
    if body.quota_limit is not None:
        from app.services.quota import register_or_update_quota

        register_or_update_quota(db, user.tenant_id, agent_id, body.quota_limit)
    db.commit()
    return ok(agent_svc.serialize_agent(db, row), message="智能体已更新")
