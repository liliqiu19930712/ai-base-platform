"""工作流执行引擎：retrieve / llm / plugin / prompt。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import ModelConfig, PluginRegister, PromptTemplate
from app.services import kb as kb_service
from app.services.llm import chat_completion
from app.services.plugin_svc import call_plugin


async def run_workflow(db: Session, *, tenant_id: str, user_id: str, dsl: dict, inputs: dict) -> dict:
    steps = dsl.get("steps") or []
    context: dict[str, Any] = {"input": inputs, "vars": {}}
    traces: list[dict] = []

    for step in steps:
        step_type = step.get("type")
        step_id = step.get("id") or step_type
        if step_type == "retrieve":
            repo_id = step.get("repo_id") or inputs.get("repo_id")
            query = step.get("query") or inputs.get("query") or ""
            if not repo_id:
                raise AppError("WF_INVALID", "retrieve 步骤缺少 repo_id")
            hits = kb_service.search_chunks(
                db,
                tenant_id=tenant_id,
                repo_id=repo_id,
                query=query,
                top_n=int(step.get("top_n", 3)),
            )
            context["vars"][step_id] = hits
            traces.append({"step": step_id, "type": step_type, "hits": len(hits)})
        elif step_type == "prompt":
            prompt_id = step.get("prompt_id")
            content = step.get("content")
            if prompt_id:
                pt = db.get(PromptTemplate, prompt_id)
                if not pt or pt.tenant_id != tenant_id:
                    raise AppError("PROMPT_NOT_FOUND", f"提示词不存在: {prompt_id}", 404)
                content = pt.content
            rendered = (content or "").format(**{**inputs, **{k: str(v) for k, v in context["vars"].items()}})
            context["vars"][step_id] = rendered
            traces.append({"step": step_id, "type": step_type})
        elif step_type == "llm":
            model_id = step.get("model_id") or inputs.get("model_id") or "mock-gpt"
            model_cfg = db.get(ModelConfig, model_id)
            prompt_tpl = step.get("prompt") or "请根据上下文回答：{query}\n上下文：{context}"
            retrieve_from = step.get("context_from")
            retrieved = context["vars"].get(retrieve_from, []) if retrieve_from else []
            if isinstance(retrieved, list):
                ctx_text = "\n".join(h.get("content", str(h)) if isinstance(h, dict) else str(h) for h in retrieved)
            else:
                ctx_text = str(retrieved)
            prompt = prompt_tpl.format(query=inputs.get("query", ""), context=ctx_text)
            content, tokens = await chat_completion(
                model_cfg=model_cfg,
                messages=[{"role": "user", "content": prompt}],
            )
            context["vars"][step_id] = {"content": content, "tokens": tokens}
            traces.append({"step": step_id, "type": step_type, "tokens": tokens, "model_id": model_id})
        elif step_type == "plugin":
            plugin_id = step.get("plugin_id")
            plugin = db.get(PluginRegister, plugin_id) if plugin_id else None
            if not plugin or plugin.tenant_id != tenant_id:
                raise AppError("PLUGIN_NOT_FOUND", f"插件不存在: {plugin_id}", 404)
            params = step.get("params") or inputs.get("plugin_params") or {}
            result = await call_plugin(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                plugin_id=plugin.plugin_id,
                params=params,
            )
            context["vars"][step_id] = result
            traces.append({"step": step_id, "type": step_type, "plugin": plugin.name, "status": result.get("status")})
        else:
            raise AppError("WF_INVALID", f"不支持的步骤类型: {step_type}")

    return {"tenant_id": tenant_id, "user_id": user_id, "traces": traces, "vars": context["vars"]}
