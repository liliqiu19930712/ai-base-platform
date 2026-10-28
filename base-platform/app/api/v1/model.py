from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_platform_admin, require_tenant
from app.core.errors import AppError, ok
from app.db import get_db
from app.models import ModelConfig
from app.services.audit import write_audit

router = APIRouter(prefix="/model", tags=["模型管理"])


class ModelUpsertRequest(BaseModel):
    model_id: str
    model_name: str
    endpoint: str = ""
    api_key: str = ""
    max_token: int = 4096
    price_per_1k: float = 0.01
    provider: str = "custom"
    status: str = "active"


@router.get("/list")
def list_models(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = db.query(ModelConfig).order_by(ModelConfig.model_id.asc()).all()
    return ok(
        [
            {
                "model_id": r.model_id,
                "model_name": r.model_name,
                "endpoint": r.endpoint,
                "status": r.status,
                "max_token": r.max_token,
                "price_per_1k": getattr(r, "price_per_1k", 0.01),
                "provider": getattr(r, "provider", "mock"),
            }
            for r in rows
        ]
    )


@router.post("/upsert")
def upsert_model(
    body: ModelUpsertRequest,
    user: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    row = db.get(ModelConfig, body.model_id)
    if not row:
        row = ModelConfig(model_id=body.model_id)
    row.model_name = body.model_name
    row.endpoint = body.endpoint
    row.api_key = body.api_key
    row.max_token = body.max_token
    row.price_per_1k = body.price_per_1k
    row.provider = body.provider
    row.status = body.status
    db.add(row)
    db.commit()
    write_audit(
        db,
        action="model.upsert",
        user_id=user.user_id,
        resource=row.model_id,
        detail={"model_name": row.model_name, "status": row.status},
    )
    return ok({"model_id": row.model_id}, message="模型配置已保存")


@router.post("/{model_id}/disable")
def disable_model(
    model_id: str,
    user: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    row = db.get(ModelConfig, model_id)
    if not row:
        raise AppError("MODEL_NOT_FOUND", "模型不存在", 404)
    row.status = "disabled"
    db.add(row)
    db.commit()
    return ok({"model_id": model_id, "status": "disabled"})
