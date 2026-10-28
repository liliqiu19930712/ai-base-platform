from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_tenant
from app.core.errors import AppError, ok
from app.db import get_db
from app.services import agent_svc
from app.services.quota import require_agent_quota

router = APIRouter(prefix="/quota", tags=["配额与计费"])


@router.get("/agents")
def list_agents(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    """当前租户已登记的智能体列表（调用侧只能用这些 agent_id）。"""
    return ok(agent_svc.list_agents(db, user.tenant_id))


@router.get("/get")
def get_quota(
    agent_id: str = Query(..., description="智能体实例 ID"),
    user: CurrentUser = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    try:
        quota = require_agent_quota(db, user.tenant_id, agent_id)
    except AppError:
        raise
    remain = max(0, quota.limit_value - quota.used_value)
    return ok(
        {
            "quota_id": quota.quota_id,
            "tenant_id": quota.tenant_id,
            "agent_id": quota.agent_id,
            "quota_type": quota.quota_type,
            "limit_value": quota.limit_value,
            "used_value": quota.used_value,
            "remain_value": remain,
            "reset_cycle": quota.reset_cycle,
        }
    )
