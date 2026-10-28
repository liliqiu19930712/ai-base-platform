import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30)
login = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()
print("login", login["code"], login["data"].get("is_platform_admin"))
assert login["code"] == "OK" and login["data"]["is_platform_admin"]
token = login["data"]["access_token"]
h = {"Authorization": f"Bearer {token}"}

lst = c.get("/api/v1/admin/tenants", headers=h).json()
print("tenants", len(lst["data"]))

created = c.post(
    "/api/v1/admin/tenants",
    headers=h,
    json={
        "tenant_id": "tenant_health",
        "tenant_name": "健康智能体子平台",
        "tenant_desc": "管理后台创建测试",
        "admin_username": "health_admin",
        "admin_password": "health123",
        "enable_gateway": True,
        "enable_kb": True,
        "enable_workflow": False,
        "enable_plugin": False,
        "default_quota_limit": 50000,
        "default_agent_id": "agent_health",
        "contact_name": "张三",
    },
).json()
print("create", created)
assert created["code"] == "OK"

sub = c.post(
    "/api/v1/auth/login",
    json={"username": "health_admin", "password": "health123", "tenant_id": "tenant_health"},
).json()
print("sub login", sub["code"], sub["data"].get("tenant_id"))
assert sub["code"] == "OK"
sh = {
    "Authorization": f"Bearer {sub['data']['access_token']}",
    "X-Tenant-Id": "tenant_health",
}
chat = c.post(
    "/api/v1/gateway/chat/completions",
    headers=sh,
    json={"agent_id": "agent_health", "messages": [{"role": "user", "content": "你好"}]},
).json()
print("chat", chat["code"])
assert chat["code"] == "OK"

wf = c.post(
    "/api/v1/workflow/run",
    headers=sh,
    json={"dsl": {"steps": []}, "input": {}},
).json()
print("workflow disabled", wf["code"])
assert wf["code"] == "FEATURE_DISABLED"
print("ADMIN FLOW OK")
