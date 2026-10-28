import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30)
login = c.post(
    "/api/v1/auth/login",
    json={"username": "health_admin", "password": "health123", "tenant_id": "tenant_health"},
).json()
assert login["code"] == "OK", login
h = {
    "Authorization": f"Bearer {login['data']['access_token']}",
    "X-Tenant-Id": "tenant_health",
}

agents = c.get("/api/v1/quota/agents", headers=h).json()
print("agents", agents["data"])

bad = c.post(
    "/api/v1/gateway/chat/completions",
    headers=h,
    json={
        "agent_id": "agent_yuwen",
        "messages": [{"role": "user", "content": "should fail"}],
    },
).json()
print("wrong agent", bad["code"], bad["message"])
assert bad["code"] == "AGENT_NOT_REGISTERED"

ok = c.post(
    "/api/v1/gateway/chat/completions",
    headers=h,
    json={
        "agent_id": "agent_health",
        "messages": [{"role": "user", "content": "should work"}],
    },
).json()
print("registered agent", ok["code"])
assert ok["code"] == "OK"
print("AGENT GUARD OK")
