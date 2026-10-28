"""灰度发布与 A/B 实验：按 user_id 稳定哈希分流。"""

from __future__ import annotations

import hashlib

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ids import new_id
from app.models import AbEvent, AbExperiment, GrayRelease


def _bucket(user_id: str, salt: str = "") -> int:
    raw = f"{salt}:{user_id or 'anonymous'}".encode("utf-8")
    return int(hashlib.md5(raw).hexdigest()[:8], 16) % 100


def resolve_gray_target(
    db: Session,
    *,
    tenant_id: str,
    target_type: str,
    default_id: str,
    user_id: str,
) -> dict:
    """若存在灰度配置且用户命中，则返回 gray 目标，否则返回 default。"""
    rows = (
        db.query(GrayRelease)
        .filter(
            GrayRelease.tenant_id == tenant_id,
            GrayRelease.target_type == target_type,
            GrayRelease.status == "active",
        )
        .all()
    )
    # 优先匹配与 default 同名族的灰度项；否则取任意启用项
    matched = [r for r in rows if r.target_id == default_id] or rows
    for row in matched:
        if _bucket(user_id, row.gray_id) < max(0, min(100, row.percent)):
            return {
                "selected_id": row.target_id,
                "source": "gray",
                "gray_id": row.gray_id,
                "percent": row.percent,
            }
    return {"selected_id": default_id, "source": "default", "gray_id": None, "percent": 0}


def assign_ab_variant(
    db: Session,
    *,
    tenant_id: str,
    target_type: str,
    user_id: str,
) -> dict | None:
    exp = (
        db.query(AbExperiment)
        .filter(
            AbExperiment.tenant_id == tenant_id,
            AbExperiment.target_type == target_type,
            AbExperiment.status == "active",
        )
        .order_by(AbExperiment.create_time.desc())
        .first()
    )
    if not exp:
        return None
    hit = _bucket(user_id, exp.exp_id) < max(0, min(100, exp.traffic_percent))
    variant = "treatment" if hit else "control"
    selected_id = exp.treatment_id if hit else exp.control_id
    return {
        "exp_id": exp.exp_id,
        "name": exp.name,
        "variant": variant,
        "selected_id": selected_id,
        "control_id": exp.control_id,
        "treatment_id": exp.treatment_id,
        "traffic_percent": exp.traffic_percent,
    }


def record_ab_event(
    db: Session,
    *,
    exp_id: str,
    tenant_id: str,
    user_id: str,
    variant: str,
    metric: str = "call",
    value: float = 1.0,
) -> None:
    db.add(
        AbEvent(
            event_id=new_id("abe_"),
            exp_id=exp_id,
            tenant_id=tenant_id,
            user_id=user_id,
            variant=variant,
            metric=metric,
            value=value,
        )
    )
    db.commit()


def create_experiment(
    db: Session,
    *,
    tenant_id: str,
    name: str,
    target_type: str,
    control_id: str,
    treatment_id: str,
    traffic_percent: int = 50,
) -> AbExperiment:
    if not control_id or not treatment_id:
        raise AppError("AB_INVALID", "control_id / treatment_id 必填")
    row = AbExperiment(
        exp_id=new_id("exp_"),
        tenant_id=tenant_id,
        name=name,
        target_type=target_type,
        control_id=control_id,
        treatment_id=treatment_id,
        traffic_percent=max(0, min(100, traffic_percent)),
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def experiment_stats(db: Session, tenant_id: str, exp_id: str) -> dict:
    exp = db.get(AbExperiment, exp_id)
    if not exp or exp.tenant_id != tenant_id:
        raise AppError("AB_NOT_FOUND", "实验不存在", 404)
    rows = (
        db.query(AbEvent.variant, func.count(AbEvent.event_id), func.coalesce(func.sum(AbEvent.value), 0.0))
        .filter(AbEvent.exp_id == exp_id)
        .group_by(AbEvent.variant)
        .all()
    )
    return {
        "exp_id": exp.exp_id,
        "name": exp.name,
        "status": exp.status,
        "variants": [
            {"variant": r[0], "events": int(r[1]), "value_sum": float(r[2])} for r in rows
        ],
    }
