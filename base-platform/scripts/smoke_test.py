"""主链路冒烟测试：登录 -> 对话 -> 配额 -> 知识库 -> 日志"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=30)
    health = client.get("/health").json()
    print("health:", health)

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "demo", "password": "demo123", "tenant_id": "tenant_edu"},
    ).json()
    assert login["code"] == "OK", login
    token = login["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": "tenant_edu"}
    print("login ok, tenant=", login["data"]["tenant_id"])

    chat = client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json={
            "agent_id": "agent_yuwen",
            "model": "mock-gpt",
            "messages": [{"role": "user", "content": "冒烟测试：基座网关是否可用？"}],
        },
    ).json()
    assert chat["code"] == "OK", chat
    print("chat ok, tokens=", chat["data"]["usage"]["total_tokens"])

    quota = client.get("/api/v1/quota/get", headers=headers, params={"agent_id": "agent_yuwen"}).json()
    assert quota["code"] == "OK", quota
    print("quota used=", quota["data"]["used_value"])

    kb = client.post("/api/v1/kb/repo/create", headers=headers, json={"repo_name": "smoke-kb"}).json()
    assert kb["code"] == "OK", kb
    repo_id = kb["data"]["repo_id"]

    files = {
        "file": (
            "smoke.txt",
            "基座平台提供网关与知识库底座能力。".encode("utf-8"),
            "text/plain",
        )
    }
    data = {"repo_id": repo_id, "tags": "smoke"}
    up = client.post("/api/v1/kb/repo/document/upload", headers=headers, data=data, files=files).json()
    assert up["code"] == "OK", up

    search = client.post(
        "/api/v1/kb/repo/search",
        headers=headers,
        json={"repo_id": repo_id, "query": "网关", "top_n": 3},
    ).json()
    assert search["code"] == "OK", search
    print("kb hits=", len(search["data"]["hits"]))

    logs = client.get("/api/v1/log/model-call/list", headers=headers).json()
    assert logs["code"] == "OK", logs
    print("logs total=", logs["data"]["total"])
    print("\nSMOKE TEST PASSED")
    print(json.dumps({"repo_id": repo_id, "quota": quota["data"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
