import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import AppError, ok
from app.core.ids import new_id
from app.db import get_db
from app.models import ChatMessage, ChatSession, ComplianceConfig, ModelCallLog, ModelConfig
from app.schemas.common import ChatCompletionRequest
from app.services.agent_svc import require_active_agent
from app.services.audit import write_audit
from app.services.llm import chat_completion, chat_completion_stream
from app.services.mask import mask_text
from app.services.quota import assert_quota_available, consume_quota
from app.services.ratelimit import check_rate_limit
from app.services.tenant_admin import assert_feature_enabled

router = APIRouter(prefix="/gateway", tags=["智能体网关"])


def _resolve_model(db: Session, model_id: str | None) -> ModelConfig | None:
    mid = model_id or "mock-gpt"
    cfg = db.get(ModelConfig, mid)
    if cfg is None and mid != "mock-gpt":
        raise AppError("MODEL_NOT_FOUND", f"模型不存在: {mid}", 404)
    if cfg and cfg.status != "active":
        raise AppError("MODEL_DISABLED", f"模型已停用: {mid}", 403)
    return cfg


def _mask_cfg(db: Session, tenant_id: str) -> ComplianceConfig | None:
    return db.query(ComplianceConfig).filter(ComplianceConfig.tenant_id == tenant_id).first()


def _apply_mask(db: Session, tenant_id: str, text: str) -> str:
    cfg = _mask_cfg(db, tenant_id)
    if not cfg:
        return mask_text(text)
    return mask_text(
        text,
        mask_phone=cfg.mask_phone,
        mask_id_card=cfg.mask_id_card,
        mask_email=cfg.mask_email,
    )


def _calc_cost(model_cfg: ModelConfig | None, tokens: int) -> float:
    price = getattr(model_cfg, "price_per_1k", 0.01) if model_cfg else 0.01
    return round(tokens / 1000.0 * float(price or 0.01), 6)


def _write_log(
    db: Session,
    *,
    tenant_id: str,
    agent_id: str,
    user_id: str,
    model_id: str,
    input_snippet: str,
    output_snippet: str,
    token_used: int,
    status: str,
    model_cfg: ModelConfig | None = None,
) -> ModelCallLog:
    log = ModelCallLog(
        log_id=new_id("log_"),
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        model_id=model_id,
        input_snippet=_apply_mask(db, tenant_id, input_snippet)[:500],
        output_snippet=_apply_mask(db, tenant_id, output_snippet)[:500],
        token_used=token_used,
        status=status,
        cost=_calc_cost(model_cfg, token_used),
        call_time=datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    return log


def _save_session(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    agent_id: str,
    user_text: str,
    assistant_text: str,
) -> str:
    session = ChatSession(
        session_id=new_id("ses_"),
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=agent_id,
        title=user_text[:40] or "会话",
    )
    db.add(session)
    db.add(
        ChatMessage(
            msg_id=new_id("msg_"),
            session_id=session.session_id,
            tenant_id=tenant_id,
            role="user",
            content=user_text,
        )
    )
    db.add(
        ChatMessage(
            msg_id=new_id("msg_"),
            session_id=session.session_id,
            tenant_id=tenant_id,
            role="assistant",
            content=assistant_text,
        )
    )
    db.commit()
    return session.session_id


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    user: CurrentUser = Depends(require_perm("gateway:invoke")),
    db: Session = Depends(get_db),
):
    assert_feature_enabled(db, user.tenant_id, "gateway")
    require_active_agent(db, user.tenant_id, body.agent_id)
    check_rate_limit(user.tenant_id, body.agent_id)
    assert_quota_available(db, user.tenant_id, body.agent_id)

    agent = require_active_agent(db, user.tenant_id, body.agent_id)
    default_model = getattr(agent, "default_model_id", None) if agent else None
    model_cfg = _resolve_model(db, body.model or default_model)
    model_id = model_cfg.model_id if model_cfg else (body.model or default_model or "mock-gpt")
    messages = [m.model_dump() for m in body.messages]
    last_user = next((m.content for m in reversed(body.messages) if m.role == "user"), "")

    if body.stream:
        async def event_gen():
            chunks: list[str] = []
            try:
                async for delta in chat_completion_stream(
                    model_cfg=model_cfg, messages=messages, temperature=body.temperature
                ):
                    chunks.append(delta)
                    payload = {
                        "id": "chatcmpl-stream",
                        "object": "chat.completion.chunk",
                        "choices": [{"delta": {"content": delta}, "index": 0}],
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                full = "".join(chunks)
                tokens = max(20, len(full) // 2)
                consume_quota(db, user.tenant_id, body.agent_id, tokens)
                _write_log(
                    db,
                    tenant_id=user.tenant_id,
                    agent_id=body.agent_id,
                    user_id=user.user_id,
                    model_id=model_id,
                    input_snippet=last_user,
                    output_snippet=full,
                    token_used=tokens,
                    status="success",
                    model_cfg=model_cfg,
                )
                _save_session(
                    db,
                    tenant_id=user.tenant_id,
                    user_id=user.user_id,
                    agent_id=body.agent_id,
                    user_text=last_user,
                    assistant_text=full,
                )
                yield "data: [DONE]\n\n"
            except Exception as exc:  # noqa: BLE001
                _write_log(
                    db,
                    tenant_id=user.tenant_id,
                    agent_id=body.agent_id,
                    user_id=user.user_id,
                    model_id=model_id,
                    input_snippet=last_user,
                    output_snippet=str(exc),
                    token_used=0,
                    status="failed",
                    model_cfg=model_cfg,
                )
                err = {"code": "GATEWAY_ERROR", "message": str(exc)}
                yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    try:
        content, tokens = await chat_completion(
            model_cfg=model_cfg, messages=messages, temperature=body.temperature
        )
        consume_quota(db, user.tenant_id, body.agent_id, tokens)
        log = _write_log(
            db,
            tenant_id=user.tenant_id,
            agent_id=body.agent_id,
            user_id=user.user_id,
            model_id=model_id,
            input_snippet=last_user,
            output_snippet=content,
            token_used=tokens,
            status="success",
            model_cfg=model_cfg,
        )
        session_id = _save_session(
            db,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            agent_id=body.agent_id,
            user_text=last_user,
            assistant_text=content,
        )
        write_audit(
            db,
            action="gateway.chat",
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            resource=body.agent_id,
            detail={"model_id": model_id, "tokens": tokens},
            ip=request.client.host if request.client else "",
        )
        return ok(
            {
                "id": log.log_id,
                "session_id": session_id,
                "model": model_id,
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"total_tokens": tokens},
                "billing": {"cost": log.cost},
            }
        )
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        _write_log(
            db,
            tenant_id=user.tenant_id,
            agent_id=body.agent_id,
            user_id=user.user_id,
            model_id=model_id,
            input_snippet=last_user,
            output_snippet=str(exc),
            token_used=0,
            status="failed",
            model_cfg=model_cfg,
        )
        raise AppError("GATEWAY_ERROR", f"模型调用失败: {exc}", 502) from exc


@router.get("/call-stat")
def call_stat(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    total = (
        db.query(func.count(ModelCallLog.log_id))
        .filter(ModelCallLog.tenant_id == user.tenant_id)
        .scalar()
        or 0
    )
    success = (
        db.query(func.count(ModelCallLog.log_id))
        .filter(ModelCallLog.tenant_id == user.tenant_id, ModelCallLog.status == "success")
        .scalar()
        or 0
    )
    tokens = (
        db.query(func.coalesce(func.sum(ModelCallLog.token_used), 0))
        .filter(ModelCallLog.tenant_id == user.tenant_id)
        .scalar()
        or 0
    )
    cost = (
        db.query(func.coalesce(func.sum(ModelCallLog.cost), 0.0))
        .filter(ModelCallLog.tenant_id == user.tenant_id)
        .scalar()
        or 0.0
    )
    failed = total - success
    return ok(
        {
            "tenant_id": user.tenant_id,
            "total_calls": total,
            "success_calls": success,
            "failed_calls": failed,
            "error_rate": round(failed / total, 4) if total else 0,
            "token_used": int(tokens),
            "total_cost": float(cost),
        }
    )


@router.get("/billing")
def billing(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = (
        db.query(
            ModelCallLog.agent_id,
            ModelCallLog.model_id,
            func.count(ModelCallLog.log_id),
            func.coalesce(func.sum(ModelCallLog.token_used), 0),
            func.coalesce(func.sum(ModelCallLog.cost), 0.0),
        )
        .filter(ModelCallLog.tenant_id == user.tenant_id, ModelCallLog.status == "success")
        .group_by(ModelCallLog.agent_id, ModelCallLog.model_id)
        .all()
    )
    items = [
        {
            "agent_id": r[0],
            "model_id": r[1],
            "calls": int(r[2]),
            "token_used": int(r[3]),
            "cost": float(r[4]),
        }
        for r in rows
    ]
    return ok({"tenant_id": user.tenant_id, "items": items})
