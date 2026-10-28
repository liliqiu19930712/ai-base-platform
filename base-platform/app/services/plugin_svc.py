import json
import time

import httpx
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ids import new_id
from app.models import PluginCallLog, PluginRegister


async def call_plugin(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    plugin_id: str,
    params: dict,
) -> dict:
    plugin = db.get(PluginRegister, plugin_id)
    if not plugin or plugin.tenant_id != tenant_id:
        raise AppError("PLUGIN_NOT_FOUND", "插件不存在或无权访问", 404)
    if plugin.status != "active":
        raise AppError("PLUGIN_DISABLED", "插件已停用", 400)

    started = time.time()
    status = "success"
    response_body: dict | str = {}
    try:
        timeout = plugin.timeout_sec or 10
        method = (plugin.method or "POST").upper()
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(plugin.endpoint, params=params)
            else:
                resp = await client.request(method, plugin.endpoint, json=params)
            # 外呼失败时降级为模拟结果，保证演示可走通
            if resp.status_code >= 400:
                status = "fallback"
                response_body = {
                    "echo": params,
                    "note": f"外呼失败 HTTP {resp.status_code}，已降级模拟",
                    "endpoint": plugin.endpoint,
                }
            else:
                try:
                    response_body = resp.json()
                except Exception:  # noqa: BLE001
                    response_body = {"raw": resp.text[:1000]}
    except Exception as exc:  # noqa: BLE001
        status = "fallback"
        response_body = {
            "echo": params,
            "note": f"外呼异常已降级模拟: {exc}",
            "endpoint": plugin.endpoint,
        }

    latency = int((time.time() - started) * 1000)
    log = PluginCallLog(
        log_id=new_id("pcl_"),
        tenant_id=tenant_id,
        plugin_id=plugin_id,
        user_id=user_id,
        request_snippet=json.dumps(params, ensure_ascii=False)[:500],
        response_snippet=json.dumps(response_body, ensure_ascii=False)[:500],
        status=status,
        latency_ms=latency,
    )
    db.add(log)
    db.commit()
    return {
        "plugin_id": plugin.plugin_id,
        "name": plugin.name,
        "endpoint": plugin.endpoint,
        "status": status,
        "latency_ms": latency,
        "result": response_body,
    }
