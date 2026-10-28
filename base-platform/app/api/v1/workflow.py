import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import AppError, ok
from app.core.ids import new_id
from app.db import get_db
from app.models import WorkflowDef
from app.schemas.common import WorkflowRunRequest
from app.services.audit import write_audit
from app.services.tenant_admin import assert_feature_enabled
from app.services.workflow import run_workflow

router = APIRouter(prefix="/workflow", tags=["工作流引擎"])


class WorkflowSaveRequest(BaseModel):
    name: str
    dsl: dict
    wf_id: str | None = None


@router.post("/save")
def save_workflow(
    body: WorkflowSaveRequest,
    user: CurrentUser = Depends(require_perm("workflow:manage")),
    db: Session = Depends(get_db),
):
    assert_feature_enabled(db, user.tenant_id, "workflow")
    version = 1
    wf_id = body.wf_id or new_id("wf_")
    if body.wf_id:
        old = db.get(WorkflowDef, body.wf_id)
        if old and old.tenant_id == user.tenant_id:
            # 新版本：用新 id
            version = old.version + 1
            wf_id = f"{body.wf_id.split('_v')[0]}_v{version}"
            old.status = "archived"
            db.add(old)
    row = WorkflowDef(
        wf_id=wf_id,
        tenant_id=user.tenant_id,
        name=body.name,
        dsl_json=json.dumps(body.dsl, ensure_ascii=False),
        version=version,
        status="active",
    )
    db.add(row)
    db.commit()
    write_audit(
        db,
        action="workflow.save",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=row.wf_id,
        detail={"name": row.name, "version": row.version},
    )
    return ok({"wf_id": row.wf_id, "name": row.name, "version": row.version, "status": row.status})


@router.get("/list")
def list_workflows(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = (
        db.query(WorkflowDef)
        .filter(WorkflowDef.tenant_id == user.tenant_id)
        .order_by(WorkflowDef.create_time.desc())
        .all()
    )
    return ok(
        [
            {
                "wf_id": r.wf_id,
                "name": r.name,
                "version": r.version,
                "status": getattr(r, "status", "active"),
                "dsl": json.loads(r.dsl_json),
            }
            for r in rows
        ]
    )


@router.post("/run")
async def workflow_run(
    body: WorkflowRunRequest,
    user: CurrentUser = Depends(require_perm("workflow:manage")),
    db: Session = Depends(get_db),
):
    assert_feature_enabled(db, user.tenant_id, "workflow")
    dsl = body.dsl
    wf_id = body.wf_id

    routing = None
    if wf_id:
        # A/B 或灰度可能改写最终工作流
        from app.services.experiment import assign_ab_variant, record_ab_event, resolve_gray_target

        ab = assign_ab_variant(
            db, tenant_id=user.tenant_id, target_type="workflow", user_id=user.user_id
        )
        if ab:
            wf_id = ab["selected_id"]
            routing = {"mode": "ab", **ab}
            record_ab_event(
                db,
                exp_id=ab["exp_id"],
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                variant=ab["variant"],
                metric="workflow_run",
            )
        else:
            gray = resolve_gray_target(
                db,
                tenant_id=user.tenant_id,
                target_type="workflow",
                default_id=wf_id,
                user_id=user.user_id,
            )
            wf_id = gray["selected_id"]
            routing = {"mode": "gray", **gray}

        wf = db.get(WorkflowDef, wf_id)
        if not wf or wf.tenant_id != user.tenant_id:
            raise AppError("WF_NOT_FOUND", "工作流不存在", 404)
        dsl = json.loads(wf.dsl_json)
    elif dsl and body.name:
        wf = WorkflowDef(
            wf_id=new_id("wf_"),
            tenant_id=user.tenant_id,
            name=body.name,
            dsl_json=json.dumps(dsl, ensure_ascii=False),
            version=1,
            status="active",
        )
        db.add(wf)
        db.commit()
        wf_id = wf.wf_id
    elif not dsl:
        raise AppError("WF_INVALID", "请提供 wf_id 或 dsl")

    result = await run_workflow(
        db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        dsl=dsl,
        inputs=body.input,
    )
    result["wf_id"] = wf_id
    if routing:
        result["routing"] = routing
    write_audit(
        db,
        action="workflow.run",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=wf_id or "",
        detail={"traces": result.get("traces")},
    )
    return ok(result)
