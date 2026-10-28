import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import AppError, ok
from app.core.ids import new_id
from app.db import get_db
from app.models import PluginCallLog, PluginRegister
from app.schemas.common import PluginCallRequest, PluginRegisterRequest
from app.services.audit import write_audit
from app.services.plugin_svc import call_plugin
from app.services.tenant_admin import assert_feature_enabled

router = APIRouter(prefix="/plugin", tags=["插件框架"])


@router.post("/register")
def register_plugin(
    body: PluginRegisterRequest,
    user: CurrentUser = Depends(require_perm("plugin:manage")),
    db: Session = Depends(get_db),
):
    assert_feature_enabled(db, user.tenant_id, "plugin")
    row = PluginRegister(
        plugin_id=new_id("pg_"),
        tenant_id=user.tenant_id,
        name=body.name,
        endpoint=body.endpoint,
        method=getattr(body, "method", None) or "POST",
        param_schema=json.dumps(body.param_schema, ensure_ascii=False),
        timeout_sec=getattr(body, "timeout_sec", None) or 10,
        category=getattr(body, "category", None) or "custom",
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    write_audit(
        db,
        action="plugin.register",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=row.plugin_id,
        detail={"name": row.name, "endpoint": row.endpoint},
    )
    return ok(
        {
            "plugin_id": row.plugin_id,
            "name": row.name,
            "endpoint": row.endpoint,
            "method": row.method,
            "category": row.category,
            "status": row.status,
        }
    )


@router.get("/list")
def list_plugins(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = (
        db.query(PluginRegister)
        .filter(PluginRegister.tenant_id == user.tenant_id)
        .order_by(PluginRegister.create_time.desc())
        .all()
    )
    return ok(
        [
            {
                "plugin_id": r.plugin_id,
                "name": r.name,
                "endpoint": r.endpoint,
                "method": getattr(r, "method", "POST"),
                "category": getattr(r, "category", "custom"),
                "status": r.status,
                "timeout_sec": getattr(r, "timeout_sec", 10),
            }
            for r in rows
        ]
    )


@router.get("/marketplace")
def marketplace(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    """插件市场：当前返回本租户插件 + 内置模板目录。"""
    owned = (
        db.query(PluginRegister)
        .filter(PluginRegister.tenant_id == user.tenant_id, PluginRegister.status == "active")
        .all()
    )
    templates = [
        {
            "template_id": "tpl_http_echo",
            "name": "HTTP Echo 调试插件",
            "category": "debug",
            "endpoint": "https://httpbin.org/post",
            "method": "POST",
            "desc": "用于联调的通用 HTTP 回显插件",
        },
        {
            "template_id": "tpl_weather",
            "name": "天气查询模板",
            "category": "tool",
            "endpoint": "https://api.example.com/weather",
            "method": "GET",
            "desc": "示例外部天气 API（需替换真实地址）",
        },
    ]
    return ok(
        {
            "installed": [
                {"plugin_id": r.plugin_id, "name": r.name, "category": getattr(r, "category", "custom")}
                for r in owned
            ],
            "templates": templates,
        }
    )


@router.post("/call")
async def call_plugin_api(
    body: PluginCallRequest,
    user: CurrentUser = Depends(require_perm("plugin:manage")),
    db: Session = Depends(get_db),
):
    assert_feature_enabled(db, user.tenant_id, "plugin")
    data = await call_plugin(
        db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        plugin_id=body.plugin_id,
        params=body.params,
    )
    return ok(data)


@router.get("/call-logs")
def call_logs(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = (
        db.query(PluginCallLog)
        .filter(PluginCallLog.tenant_id == user.tenant_id)
        .order_by(PluginCallLog.call_time.desc())
        .limit(50)
        .all()
    )
    return ok(
        [
            {
                "log_id": r.log_id,
                "plugin_id": r.plugin_id,
                "status": r.status,
                "latency_ms": r.latency_ms,
                "request_snippet": r.request_snippet,
                "response_snippet": r.response_snippet,
                "call_time": r.call_time.isoformat() + "Z" if r.call_time else None,
            }
            for r in rows
        ]
    )
