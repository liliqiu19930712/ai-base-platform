from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import ok
from app.core.ids import new_id
from app.db import get_db
from app.models import ComplianceConfig, GrayRelease
from app.services.audit import write_audit
from app.services.mask import mask_text

router = APIRouter(prefix="/compliance", tags=["安全合规审计"])


class ComplianceUpsertRequest(BaseModel):
    title: str = "合规免责提示"
    content: str = ""
    mask_phone: bool = True
    mask_id_card: bool = True
    mask_email: bool = True


class MaskPreviewRequest(BaseModel):
    text: str


class GrayCreateRequest(BaseModel):
    target_type: str = "prompt"
    target_id: str
    percent: int = 10


@router.get("/config")
def get_config(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    row = db.query(ComplianceConfig).filter(ComplianceConfig.tenant_id == user.tenant_id).first()
    if not row:
        return ok(
            {
                "title": "合规免责提示",
                "content": "本智能体输出仅供参考。",
                "mask_phone": True,
                "mask_id_card": True,
                "mask_email": True,
            }
        )
    return ok(
        {
            "config_id": row.config_id,
            "title": row.title,
            "content": row.content,
            "mask_phone": row.mask_phone,
            "mask_id_card": row.mask_id_card,
            "mask_email": row.mask_email,
        }
    )


@router.post("/config")
def upsert_config(
    body: ComplianceUpsertRequest,
    user: CurrentUser = Depends(require_perm("tenant:admin")),
    db: Session = Depends(get_db),
):
    row = db.query(ComplianceConfig).filter(ComplianceConfig.tenant_id == user.tenant_id).first()
    if not row:
        row = ComplianceConfig(config_id=new_id("cmp_"), tenant_id=user.tenant_id)
    row.title = body.title
    row.content = body.content
    row.mask_phone = body.mask_phone
    row.mask_id_card = body.mask_id_card
    row.mask_email = body.mask_email
    db.add(row)
    db.commit()
    write_audit(
        db,
        action="compliance.config",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=row.config_id,
    )
    return ok({"config_id": row.config_id}, message="合规配置已保存")


@router.post("/mask-preview")
def mask_preview(body: MaskPreviewRequest, user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    cfg = db.query(ComplianceConfig).filter(ComplianceConfig.tenant_id == user.tenant_id).first()
    masked = mask_text(
        body.text,
        mask_phone=cfg.mask_phone if cfg else True,
        mask_id_card=cfg.mask_id_card if cfg else True,
        mask_email=cfg.mask_email if cfg else True,
    )
    return ok({"original": body.text, "masked": masked})


@router.post("/gray")
def create_gray(
    body: GrayCreateRequest,
    user: CurrentUser = Depends(require_perm("tenant:admin")),
    db: Session = Depends(get_db),
):
    row = GrayRelease(
        gray_id=new_id("gray_"),
        tenant_id=user.tenant_id,
        target_type=body.target_type,
        target_id=body.target_id,
        percent=max(0, min(100, body.percent)),
        status="active",
    )
    db.add(row)
    db.commit()
    return ok(
        {
            "gray_id": row.gray_id,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "percent": row.percent,
        }
    )


@router.get("/gray/list")
def list_gray(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = db.query(GrayRelease).filter(GrayRelease.tenant_id == user.tenant_id).all()
    return ok(
        [
            {
                "gray_id": r.gray_id,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "percent": r.percent,
                "status": r.status,
            }
            for r in rows
        ]
    )


class AbCreateRequest(BaseModel):
    name: str
    target_type: str = "prompt"
    control_id: str
    treatment_id: str
    traffic_percent: int = 50


@router.post("/ab")
def create_ab(
    body: AbCreateRequest,
    user: CurrentUser = Depends(require_perm("tenant:admin")),
    db: Session = Depends(get_db),
):
    from app.services.experiment import create_experiment

    row = create_experiment(
        db,
        tenant_id=user.tenant_id,
        name=body.name,
        target_type=body.target_type,
        control_id=body.control_id,
        treatment_id=body.treatment_id,
        traffic_percent=body.traffic_percent,
    )
    write_audit(
        db,
        action="ab.create",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=row.exp_id,
        detail={"name": row.name},
    )
    return ok(
        {
            "exp_id": row.exp_id,
            "name": row.name,
            "control_id": row.control_id,
            "treatment_id": row.treatment_id,
            "traffic_percent": row.traffic_percent,
        }
    )


@router.get("/ab/list")
def list_ab(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    from app.models import AbExperiment

    rows = db.query(AbExperiment).filter(AbExperiment.tenant_id == user.tenant_id).all()
    return ok(
        [
            {
                "exp_id": r.exp_id,
                "name": r.name,
                "target_type": r.target_type,
                "control_id": r.control_id,
                "treatment_id": r.treatment_id,
                "traffic_percent": r.traffic_percent,
                "status": r.status,
            }
            for r in rows
        ]
    )


@router.get("/ab/{exp_id}/stats")
def ab_stats(exp_id: str, user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    from app.services.experiment import experiment_stats

    return ok(experiment_stats(db, user.tenant_id, exp_id))


@router.get("/resolve")
def resolve_target(
    target_type: str = "prompt",
    default_id: str = "",
    user: CurrentUser = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    """对当前用户解析灰度/A-B 最终目标。优先 A/B，其次灰度。"""
    from app.services.experiment import assign_ab_variant, resolve_gray_target

    ab = assign_ab_variant(db, tenant_id=user.tenant_id, target_type=target_type, user_id=user.user_id)
    if ab:
        return ok({"mode": "ab", **ab})
    gray = resolve_gray_target(
        db,
        tenant_id=user.tenant_id,
        target_type=target_type,
        default_id=default_id,
        user_id=user.user_id,
    )
    return ok({"mode": "gray", **gray})
