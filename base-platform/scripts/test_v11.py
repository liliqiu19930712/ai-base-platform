import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30)
print("health", c.get("/health").json())

login = c.post(
    "/api/v1/auth/login",
    json={"username": "demo", "password": "demo123", "tenant_id": "tenant_edu"},
).json()
assert login["code"] == "OK", login
h = {
    "Authorization": f"Bearer {login['data']['access_token']}",
    "X-Tenant-Id": "tenant_edu",
}

# 1 IAM
perms = c.get("/api/v1/iam/my-permissions", headers=h).json()
print("perms", perms["data"]["permissions"][:5], "...")

# 2 gateway
agents = c.get("/api/v1/agent/list", headers=h).json()
print("agents", [a["agent_id"] for a in agents["data"]])
chat = c.post(
    "/api/v1/gateway/chat/completions",
    headers=h,
    json={
        "agent_id": "agent_yuwen",
        "messages": [{"role": "user", "content": "文化基座测试"}],
    },
).json()
assert chat["code"] == "OK", chat
print("chat tokens", chat["data"]["usage"]["total_tokens"], "cost", chat["data"]["billing"]["cost"])

# 3 kb
kb = c.post("/api/v1/kb/repo/create", headers=h, json={"repo_name": "v11-culture"}).json()
assert kb["code"] == "OK", kb
repo_id = kb["data"]["repo_id"]
up = c.post(
    "/api/v1/kb/repo/document/upload",
    headers=h,
    data={"repo_id": repo_id, "tags": "culture"},
    files={"file": ("a.txt", "文化智能体基座提供统一身份与知识库。".encode("utf-8"), "text/plain")},
).json()
assert up["code"] == "OK", up
search = c.post(
    "/api/v1/kb/repo/search",
    headers=h,
    json={"repo_id": repo_id, "query": "知识库", "top_n": 3},
).json()
print("kb hits", len(search["data"]["hits"]))

# 4 workflow
wf = c.post(
    "/api/v1/workflow/run",
    headers=h,
    json={
        "name": "rag",
        "dsl": {
            "steps": [
                {"id": "r1", "type": "retrieve", "top_n": 2},
                {"id": "l1", "type": "llm", "model_id": "mock-gpt", "context_from": "r1"},
            ]
        },
        "input": {"repo_id": repo_id, "query": "基座"},
    },
).json()
assert wf["code"] == "OK", wf
print("workflow traces", len(wf["data"]["traces"]))

# 5 plugin
pg = c.post(
    "/api/v1/plugin/register",
    headers=h,
    json={"name": "echo", "endpoint": "https://httpbin.org/post", "method": "POST"},
).json()
assert pg["code"] == "OK", pg
call = c.post(
    "/api/v1/plugin/call",
    headers=h,
    json={"plugin_id": pg["data"]["plugin_id"], "params": {"x": 1}},
).json()
assert call["code"] == "OK", call
print("plugin status", call["data"]["status"])

# 6 compliance
mask = c.post(
    "/api/v1/compliance/mask-preview",
    headers=h,
    json={"text": "手机13812345678"},
).json()
assert "****" in mask["data"]["masked"]
audit = c.get("/api/v1/log/audit/list", headers=h).json()
print("audit total", audit["data"]["total"])
print("V1.1 SIX CAPABILITIES OK")
