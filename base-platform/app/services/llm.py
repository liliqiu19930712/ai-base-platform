import json
from collections.abc import AsyncIterator

import httpx

from app.config import get_settings
from app.models import ModelConfig


settings = get_settings()


async def chat_completion(
    *,
    model_cfg: ModelConfig | None,
    messages: list[dict],
    temperature: float = 0.7,
) -> tuple[str, int]:
    """返回 (content, token_used)。未配置真实 LLM 时走 Mock。"""
    model_name = (model_cfg.model_name if model_cfg else None) or settings.llm_default_model
    endpoint = (model_cfg.endpoint if model_cfg else "") or settings.llm_base_url
    api_key = (model_cfg.api_key if model_cfg else "") or settings.llm_api_key

    if not endpoint or model_name.startswith("mock"):
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        content = (
            f"[基座 Mock 模型 · {model_name}]\n"
            f"已收到你的请求，并经智能体网关转发。\n"
            f"用户说：{last_user[:500]}\n"
            f"（配置 LLM_BASE_URL / model_config.endpoint 后可切换为真实模型）"
        )
        token_used = max(20, len(content) // 2)
        return content, token_used

    url = endpoint.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    token_used = int(usage.get("total_tokens") or max(20, len(content) // 2))
    return content, token_used


async def chat_completion_stream(
    *,
    model_cfg: ModelConfig | None,
    messages: list[dict],
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    model_name = (model_cfg.model_name if model_cfg else None) or settings.llm_default_model
    endpoint = (model_cfg.endpoint if model_cfg else "") or settings.llm_base_url
    api_key = (model_cfg.api_key if model_cfg else "") or settings.llm_api_key

    if not endpoint or model_name.startswith("mock"):
        content, _ = await chat_completion(model_cfg=model_cfg, messages=messages, temperature=temperature)
        # 模拟流式分片
        step = 12
        for i in range(0, len(content), step):
            yield content[i : i + step]
        return

    url = endpoint.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
