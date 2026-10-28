from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ids import new_id
from app.models import AgentQuota, AgentRegistry
from app.services.quota import register_or_update_quota


def _get_by_tenant_agent(db: Session, tenant_id: str, agent_id: str) -> AgentRegistry | None:
    return (
        db.query(AgentRegistry)
        .filter(AgentRegistry.tenant_id == tenant_id, AgentRegistry.agent_id == agent_id)
        .first()
    )


def register_agent(
    db: Session,
    *,
    tenant_id: str,
    agent_id: str | None,
    agent_name: str,
    description: str = "",
    default_model_id: str = "mock-gpt",
    quota_limit: int = 100000,
) -> dict:
    aid = (agent_id or "").strip() or f"agent_{new_id()}"
    if _get_by_tenant_agent(db, tenant_id, aid):
        raise AppError("AGENT_EXISTS", f"智能体已存在: {aid}", 409)
    row = AgentRegistry(
        reg_id=new_id("reg_"),
        agent_id=aid,
        tenant_id=tenant_id,
        agent_name=agent_name.strip() or aid,
        description=description,
        default_model_id=default_model_id or "mock-gpt",
        status="active",
    )
    db.add(row)
    register_or_update_quota(db, tenant_id, aid, quota_limit)
    db.commit()
    db.refresh(row)
    return serialize_agent(db, row)


def serialize_agent(db: Session, row: AgentRegistry) -> dict:
    quota = (
        db.query(AgentQuota)
        .filter(AgentQuota.tenant_id == row.tenant_id, AgentQuota.agent_id == row.agent_id)
        .first()
    )
    return {
        "reg_id": row.reg_id,
        "agent_id": row.agent_id,
        "tenant_id": row.tenant_id,
        "agent_name": row.agent_name,
        "description": row.description,
        "default_model_id": row.default_model_id,
        "status": row.status,
        "quota": {
            "limit_value": quota.limit_value if quota else 0,
            "used_value": quota.used_value if quota else 0,
            "remain_value": max(0, (quota.limit_value if quota else 0) - (quota.used_value if quota else 0)),
        },
    }


def list_agents(db: Session, tenant_id: str) -> list[dict]:
    rows = (
        db.query(AgentRegistry)
        .filter(AgentRegistry.tenant_id == tenant_id)
        .order_by(AgentRegistry.create_time.desc())
        .all()
    )
    if not rows:
        quotas = db.query(AgentQuota).filter(AgentQuota.tenant_id == tenant_id).all()
        return [
            {
                "agent_id": q.agent_id,
                "tenant_id": q.tenant_id,
                "agent_name": q.agent_id,
                "description": "",
                "default_model_id": "mock-gpt",
                "status": "active",
                "quota": {
                    "limit_value": q.limit_value,
                    "used_value": q.used_value,
                    "remain_value": max(0, q.limit_value - q.used_value),
                },
            }
            for q in quotas
        ]
    return [serialize_agent(db, r) for r in rows]


def require_active_agent(db: Session, tenant_id: str, agent_id: str) -> AgentRegistry | None:
    row = _get_by_tenant_agent(db, tenant_id, agent_id)
    if row:
        if row.status != "active":
            raise AppError("AGENT_DISABLED", "智能体已停用", 403)
        return row
    quota = (
        db.query(AgentQuota)
        .filter(AgentQuota.tenant_id == tenant_id, AgentQuota.agent_id == agent_id)
        .first()
    )
    if not quota:
        raise AppError(
            "AGENT_NOT_REGISTERED",
            f"智能体未在本租户登记: {agent_id}",
            403,
        )
    return None
