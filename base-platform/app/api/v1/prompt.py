from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import AppError, ok
from app.core.ids import new_id
from app.db import get_db
from app.models import PromptTemplate
from app.schemas.common import PromptSaveRequest
from app.services.audit import write_audit

router = APIRouter(prefix="/prompt", tags=["提示词工程"])


@router.post("/template/save")
def save_template(
    body: PromptSaveRequest,
    user: CurrentUser = Depends(require_perm("workflow:manage")),
    db: Session = Depends(get_db),
):
    same_name = (
        db.query(PromptTemplate)
        .filter(PromptTemplate.tenant_id == user.tenant_id, PromptTemplate.name == body.name)
        .order_by(PromptTemplate.version.desc())
        .first()
    )
    version = (same_name.version + 1) if same_name else 1
    base_id = body.prompt_id or new_id("pt_")
    prompt_id = f"{base_id.split('_v')[0]}_v{version}"
    # 同名旧版本取消 active
    if same_name:
        olds = (
            db.query(PromptTemplate)
            .filter(PromptTemplate.tenant_id == user.tenant_id, PromptTemplate.name == body.name)
            .all()
        )
        for o in olds:
            o.is_active = False
            db.add(o)
    row = PromptTemplate(
        prompt_id=prompt_id,
        tenant_id=user.tenant_id,
        name=body.name,
        content=body.content,
        version=version,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    write_audit(
        db,
        action="prompt.save",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=row.prompt_id,
        detail={"name": row.name, "version": row.version},
    )
    return ok(
        {
            "prompt_id": row.prompt_id,
            "name": row.name,
            "version": row.version,
            "content": row.content,
            "is_active": row.is_active,
        }
    )


@router.get("/template/list")
def list_templates(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = (
        db.query(PromptTemplate)
        .filter(PromptTemplate.tenant_id == user.tenant_id)
        .order_by(PromptTemplate.name.asc(), PromptTemplate.version.desc())
        .all()
    )
    return ok(
        [
            {
                "prompt_id": r.prompt_id,
                "name": r.name,
                "version": r.version,
                "is_active": getattr(r, "is_active", True),
                "content": r.content,
                "create_time": r.create_time.isoformat() + "Z" if r.create_time else None,
            }
            for r in rows
        ]
    )


@router.post("/template/{prompt_id}/activate")
def activate_template(
    prompt_id: str,
    user: CurrentUser = Depends(require_perm("workflow:manage")),
    db: Session = Depends(get_db),
):
    row = db.get(PromptTemplate, prompt_id)
    if not row or row.tenant_id != user.tenant_id:
        raise AppError("PROMPT_NOT_FOUND", "提示词不存在", 404)
    siblings = (
        db.query(PromptTemplate)
        .filter(PromptTemplate.tenant_id == user.tenant_id, PromptTemplate.name == row.name)
        .all()
    )
    for s in siblings:
        s.is_active = s.prompt_id == prompt_id
        db.add(s)
    db.commit()
    return ok({"prompt_id": prompt_id, "name": row.name, "version": row.version}, message="已切换到该版本")
