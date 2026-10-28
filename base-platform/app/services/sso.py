"""SSO：基座签发一次性票据，子平台兑换登录态；可选企业微信 OAuth。"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.security import create_access_token
from app.models import PlatformAdmin, SsoTicket, User, UserTenantRel

settings = get_settings()


def issue_ticket(
    db: Session,
    *,
    user_id: str,
    tenant_id: str = "",
    redirect_uri: str = "",
    ttl_seconds: int = 120,
) -> dict:
    ticket_id = new_id("sso_")
    row = SsoTicket(
        ticket_id=ticket_id,
        user_id=user_id,
        tenant_id=tenant_id or "",
        redirect_uri=redirect_uri or "",
        consumed=False,
        expire_time=datetime.utcnow() + timedelta(seconds=ttl_seconds),
    )
    db.add(row)
    db.commit()
    return {
        "ticket": ticket_id,
        "expire_in": ttl_seconds,
        "redirect_uri": redirect_uri,
        "exchange_url": "/api/v1/auth/sso/exchange",
    }


def exchange_ticket(db: Session, ticket: str) -> dict:
    row = db.get(SsoTicket, ticket)
    if not row:
        raise AppError("SSO_TICKET_INVALID", "SSO 票据无效", 401)
    if row.consumed:
        raise AppError("SSO_TICKET_USED", "SSO 票据已使用", 401)
    if row.expire_time < datetime.utcnow():
        raise AppError("SSO_TICKET_EXPIRED", "SSO 票据已过期", 401)
    user = db.get(User, row.user_id)
    if not user or getattr(user, "status", "active") == "disabled":
        raise AppError("SSO_USER_INVALID", "用户不可用", 401)

    row.consumed = True
    db.add(row)
    db.commit()

    tenant_id = row.tenant_id
    if not tenant_id:
        rel = db.query(UserTenantRel).filter(UserTenantRel.user_id == user.user_id).first()
        tenant_id = rel.tenant_id if rel else ""
    is_admin = db.get(PlatformAdmin, user.user_id) is not None
    payload = {"sub": user.user_id, "username": user.username}
    if tenant_id:
        payload["tenant_id"] = tenant_id
    token = create_access_token(payload)
    return {
        "access_token": token,
        "token_type": "Bearer",
        "tenant_id": tenant_id,
        "user_id": user.user_id,
        "username": user.username,
        "is_platform_admin": is_admin,
        "redirect_uri": row.redirect_uri,
    }


def wecom_authorize_url(state: str, redirect_uri: str) -> dict:
    corp_id = settings.wecom_corp_id
    agent_id = settings.wecom_agent_id
    if not corp_id or not agent_id:
        # 未配置时返回演示模式说明
        return {
            "mode": "mock",
            "authorize_url": f"/api/v1/auth/sso/wecom/mock-callback?state={state}&redirect_uri={redirect_uri}",
            "message": "未配置企业微信，已提供 mock SSO 回调用于联调",
        }
    params = {
        "appid": corp_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "snsapi_base",
        "state": state,
        "agentid": agent_id,
    }
    url = "https://open.weixin.qq.com/connect/oauth2/authorize?" + urlencode(params) + "#wechat_redirect"
    return {"mode": "wecom", "authorize_url": url}


async def wecom_exchange_code(db: Session, code: str, tenant_id: str = "") -> dict:
    """真实企业微信：用 code 换 userid，再映射/创建本地用户。未配置时走 mock。"""
    if not settings.wecom_corp_id or not settings.wecom_secret:
        # mock：code 即用户名后缀
        username = f"wecom_{code[:16] or 'demo'}"
        user = db.query(User).filter(User.username == username).first()
        if not user:
            from app.core.security import hash_password

            user = User(
                user_id=new_id("user_"),
                username=username,
                password_hash=hash_password(new_id("pwd_")),
                email="",
                status="active",
            )
            db.add(user)
            db.commit()
        ticket = issue_ticket(db, user_id=user.user_id, tenant_id=tenant_id)
        return exchange_ticket(db, ticket["ticket"])

    # 真实调用：先取 access_token，再取 userinfo
    async with httpx.AsyncClient(timeout=20) as client:
        token_resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": settings.wecom_corp_id, "corpsecret": settings.wecom_secret},
        )
        token_data = token_resp.json()
        if token_data.get("errcode", 0) != 0:
            raise AppError("WECOM_TOKEN_FAIL", f"企业微信 token 失败: {token_data}", 502)
        access_token = token_data["access_token"]
        info_resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo",
            params={"access_token": access_token, "code": code},
        )
        info = info_resp.json()
        userid = info.get("UserId") or info.get("userid")
        if not userid:
            raise AppError("WECOM_USER_FAIL", f"企业微信用户解析失败: {info}", 502)

    username = f"wecom_{userid}"
    user = db.query(User).filter(User.username == username).first()
    if not user:
        from app.core.security import hash_password

        user = User(
            user_id=new_id("user_"),
            username=username,
            password_hash=hash_password(new_id("pwd_")),
            status="active",
        )
        db.add(user)
        db.commit()
    ticket = issue_ticket(db, user_id=user.user_id, tenant_id=tenant_id)
    return exchange_ticket(db, ticket["ticket"])
