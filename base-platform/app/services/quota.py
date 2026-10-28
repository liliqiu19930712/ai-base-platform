from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ids import new_id
from app.models import AgentQuota


def get_quota(db: Session, tenant_id: str, agent_id: str) -> AgentQuota | None:
    return (
        db.query(AgentQuota)
        .filter(AgentQuota.tenant_id == tenant_id, AgentQuota.agent_id == agent_id)
        .first()
    )


def require_agent_quota(db: Session, tenant_id: str, agent_id: str) -> AgentQuota:
    """调用侧：智能体必须已在本租户登记，禁止随意 agent_id 自动建配额。"""
    agent_id = (agent_id or "").strip()
    if not agent_id:
        raise AppError("AGENT_REQUIRED", "缺少 agent_id", 400)
    quota = get_quota(db, tenant_id, agent_id)
    if not quota:
        raise AppError(
            "AGENT_NOT_REGISTERED",
            f"智能体未在本租户登记: {agent_id}。请先在管理后台为该租户配置智能体配额。",
            403,
        )
    return quota


def list_tenant_agents(db: Session, tenant_id: str) -> list[dict]:
    rows = (
        db.query(AgentQuota)
        .filter(AgentQuota.tenant_id == tenant_id)
        .order_by(AgentQuota.agent_id.asc())
        .all()
    )
    return [
        {
            "agent_id": q.agent_id,
            "quota_id": q.quota_id,
            "quota_type": q.quota_type,
            "limit_value": q.limit_value,
            "used_value": q.used_value,
            "remain_value": max(0, q.limit_value - q.used_value),
            "reset_cycle": q.reset_cycle,
        }
        for q in rows
    ]


def register_or_update_quota(
    db: Session,
    tenant_id: str,
    agent_id: str,
    limit_value: int,
) -> AgentQuota:
    """管理侧：登记/更新智能体配额。"""
    agent_id = (agent_id or "").strip()
    if not agent_id:
        raise AppError("AGENT_REQUIRED", "缺少 agent_id", 400)
    if limit_value <= 0:
        raise AppError("INVALID_QUOTA", "配额必须大于 0")
    quota = get_quota(db, tenant_id, agent_id)
    if not quota:
        quota = AgentQuota(
            quota_id=new_id("qt_"),
            tenant_id=tenant_id,
            agent_id=agent_id,
            quota_type="token_month",
            limit_value=limit_value,
            used_value=0,
            reset_cycle="month",
        )
    else:
        quota.limit_value = limit_value
    db.add(quota)
    db.commit()
    db.refresh(quota)
    return quota


def assert_quota_available(db: Session, tenant_id: str, agent_id: str, estimate: int = 1) -> AgentQuota:
    quota = require_agent_quota(db, tenant_id, agent_id)
    if quota.used_value + estimate > quota.limit_value:
        raise AppError(
            "QUOTA_EXCEEDED",
            f"配额已用尽：used={quota.used_value}, limit={quota.limit_value}",
            429,
        )
    return quota


def consume_quota(db: Session, tenant_id: str, agent_id: str, tokens: int) -> AgentQuota:
    quota = assert_quota_available(db, tenant_id, agent_id, estimate=tokens)
    quota.used_value += tokens
    db.add(quota)
    db.commit()
    db.refresh(quota)
    return quota


# 兼容旧引用名（管理侧建租户时仍会用）
def get_or_create_quota(db: Session, tenant_id: str, agent_id: str) -> AgentQuota:
    existing = get_quota(db, tenant_id, agent_id)
    if existing:
        return existing
    return register_or_update_quota(db, tenant_id, agent_id, 100000)
