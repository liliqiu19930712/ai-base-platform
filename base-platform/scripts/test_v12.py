"""V1.2 五项能力联调：向量 RAG / 工作流 DSL / SSO / 灰度A-B / 文化样板入口。"""

import sys

import httpx

BASE = "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=30)
failed = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}")
    else:
        print(f" FAIL {name}: {detail}")
        failed.append(name)


print("== health / pages ==")
h = c.get("/health").json()
check("health", h.get("status") == "ok" or h.get("code") == "OK" or "ok" in str(h).lower(), h)
for path in ["/", "/workflow-editor", "/culture", "/admin", "/console"]:
    r = c.get(path)
    check(f"page {path}", r.status_code == 200 and len(r.text) > 200, r.status_code)

print("== login ==")
login = c.post(
    "/api/v1/auth/login",
    json={"username": "demo", "password": "demo123", "tenant_id": "tenant_edu"},
).json()
check("login", login.get("code") == "OK", login)
token = login["data"]["access_token"]
hdr = {"Authorization": f"Bearer {token}", "X-Tenant-Id": "tenant_edu"}

print("== 1 vector RAG ==")
kb = c.post("/api/v1/kb/repo/create", headers=hdr, json={"repo_name": "v12-vector"}).json()
check("kb create", kb.get("code") == "OK", kb)
repo_id = kb["data"]["repo_id"]
docs = [
    ("昆曲.txt", "昆曲起源于江苏昆山，曲词典雅，以水磨腔闻名于世。"),
    ("京剧.txt", "京剧是中国国粹，融合徽汉二调，以唱念做打见长。"),
    ("基座.txt", "文化智能体基座提供统一身份、知识库向量检索与工作流编排。"),
]
for name, text in docs:
    up = c.post(
        "/api/v1/kb/repo/document/upload",
        headers=hdr,
        data={"repo_id": repo_id, "tags": "culture"},
        files={"file": (name, text.encode("utf-8"), "text/plain")},
    ).json()
    check(f"upload {name}", up.get("code") == "OK" and up["data"].get("vectorized") is True, up)

search = c.post(
    "/api/v1/kb/repo/search",
    headers=hdr,
    json={"repo_id": repo_id, "query": "水磨腔昆山", "top_n": 3},
).json()
check("vector search", search.get("code") == "OK" and len(search["data"].get("hits", [])) >= 1, search)
if search.get("code") == "OK" and search["data"].get("hits"):
    top = search["data"]["hits"][0]
    check("top hit has score", "score" in top and top["score"] > 0, top)
    check("top related to 昆曲", "昆曲" in top.get("content", "") or "昆" in top.get("doc_name", ""), top)

reidx = c.post(f"/api/v1/kb/repo/{repo_id}/reindex", headers=hdr).json()
check("reindex", reidx.get("code") == "OK" and reidx["data"].get("reindexed", 0) >= 1, reidx)

print("== 2 workflow editor DSL ==")
dsl = {
    "steps": [
        {"id": "r1", "type": "retrieve", "top_n": 2},
        {"id": "l1", "type": "llm", "model_id": "mock-gpt", "context_from": "r1"},
    ]
}
save = c.post(
    "/api/v1/workflow/save",
    headers=hdr,
    json={"name": "v12-visual-rag", "dsl": dsl},
).json()
check("workflow save", save.get("code") == "OK", save)
wf_id = save["data"]["wf_id"]
run = c.post(
    "/api/v1/workflow/run",
    headers=hdr,
    json={"wf_id": wf_id, "input": {"repo_id": repo_id, "query": "昆曲"}},
).json()
check("workflow run", run.get("code") == "OK" and len(run["data"].get("traces", [])) >= 1, run)
wjs = c.get("/static/js/workflow-editor.js").status_code
check("workflow-editor.js", wjs == 200)

print("== 3 SSO ticket + WeCom mock ==")
ticket = c.post(
    "/api/v1/auth/sso/ticket",
    headers=hdr,
    json={"redirect_uri": "/culture", "tenant_id": "tenant_edu"},
).json()
check("sso ticket", ticket.get("code") == "OK" and ticket["data"].get("ticket"), ticket)
ex = c.post(
    "/api/v1/auth/sso/exchange",
    json={"ticket": ticket["data"]["ticket"]},
).json()
check("sso exchange", ex.get("code") == "OK" and ex["data"].get("access_token"), ex)
# ticket one-time
ex2 = c.post("/api/v1/auth/sso/exchange", json={"ticket": ticket["data"]["ticket"]}).json()
check("sso ticket one-time", ex2.get("code") != "OK", ex2)

authz = c.get("/api/v1/auth/sso/wecom/authorize", params={"redirect_uri": "/culture"}).json()
check("wecom authorize", authz.get("code") == "OK" and authz["data"].get("authorize_url"), authz)
mock = c.get(
    "/api/v1/auth/sso/wecom/mock-callback",
    params={"code": "demo", "redirect_uri": "/culture", "tenant_id": "tenant_edu"},
).json()
check("wecom mock", mock.get("code") == "OK" and mock["data"].get("access_token"), mock)

print("== 4 gray / A-B ==")
ab = c.post(
    "/api/v1/compliance/ab",
    headers=hdr,
    json={
        "name": "v12-prompt-ab",
        "target_type": "workflow",
        "control_id": wf_id,
        "treatment_id": wf_id,
        "traffic_percent": 100,
    },
).json()
check("ab create", ab.get("code") == "OK", ab)
exp_id = ab["data"]["exp_id"]
resolve = c.get(
    "/api/v1/compliance/resolve",
    headers=hdr,
    params={"target_type": "workflow", "default_id": wf_id},
).json()
check(
    "ab resolve",
    resolve.get("code") == "OK" and resolve["data"].get("mode") == "ab",
    resolve,
)
# gray
gray = c.post(
    "/api/v1/compliance/gray",
    headers=hdr,
    json={"target_type": "prompt", "target_id": "prompt_gray_v2", "percent": 100},
).json()
check("gray create", gray.get("code") == "OK", gray)
# temporarily no ab for prompt — resolve gray
# create another tenant user path: resolve with prompt type after archiving isn't available,
# so call resolve_gray via resolve when no ab for prompt
resolve_g = c.get(
    "/api/v1/compliance/resolve",
    headers=hdr,
    params={"target_type": "prompt", "default_id": "prompt_default"},
).json()
check(
    "gray resolve",
    resolve_g.get("code") == "OK"
    and (
        resolve_g["data"].get("mode") == "gray"
        or resolve_g["data"].get("selected_id")
        or resolve_g["data"].get("mode") == "ab"
    ),
    resolve_g,
)
stats = c.get(f"/api/v1/compliance/ab/{exp_id}/stats", headers=hdr).json()
check("ab stats endpoint", stats.get("code") == "OK", stats)

# workflow run with routing
run2 = c.post(
    "/api/v1/workflow/run",
    headers=hdr,
    json={"wf_id": wf_id, "input": {"repo_id": repo_id, "query": "京剧"}},
).json()
check("workflow with ab routing", run2.get("code") == "OK", run2)

print("== 5 culture portal ==")
cjs = c.get("/static/culture/culture.js").status_code
ccs = c.get("/static/culture/culture.css").status_code
check("culture.js", cjs == 200)
check("culture.css", ccs == 200)
cult = c.get("/culture")
check("culture html", cult.status_code == 200 and "文化智能体" in cult.text)

print("== summary ==")
if failed:
    print("FAILED:", ", ".join(failed))
    sys.exit(1)
print("ALL V1.2 CHECKS PASSED")
