import json

from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.security import hash_password
from app.models import (
    AgentQuota,
    ModelConfig,
    Permission,
    PluginRegister,
    PromptTemplate,
    Role,
    Tenant,
    User,
    UserTenantRel,
    WorkflowDef,
)


def seed_if_empty(db: Session) -> None:
    if db.query(User).first():
        return

    # 权限项
    perms = [
        ("perm_gateway", "gateway:invoke", "调用智能体网关"),
        ("perm_kb", "kb:manage", "管理知识库"),
        ("perm_admin", "tenant:admin", "租户管理"),
    ]
    for pid, key, desc in perms:
        db.add(Permission(perm_id=pid, perm_key=key, perm_desc=desc))

    # 两个样板租户：教育、企业
    tenants = [
        ("tenant_edu", "教育智能体子平台", "样板：教育类智能体接入示例"),
        ("tenant_ent", "企业智能体子平台", "样板：企业类智能体接入示例"),
    ]
    for tid, name, desc in tenants:
        db.add(Tenant(tenant_id=tid, tenant_name=name, tenant_desc=desc, status="active"))

    # 角色
    edu_admin = Role(
        role_id="role_edu_admin",
        tenant_id="tenant_edu",
        role_name="管理员",
        permission_json=json.dumps(
            [
                "gateway:invoke",
                "kb:manage",
                "workflow:manage",
                "plugin:manage",
                "audit:read",
                "tenant:admin",
            ]
        ),
    )
    ent_admin = Role(
        role_id="role_ent_admin",
        tenant_id="tenant_ent",
        role_name="管理员",
        permission_json=json.dumps(
            [
                "gateway:invoke",
                "kb:manage",
                "workflow:manage",
                "plugin:manage",
                "audit:read",
                "tenant:admin",
            ]
        ),
    )
    db.add(edu_admin)
    db.add(ent_admin)

    # 演示账号
    user = User(
        user_id="user_demo",
        username="demo",
        password_hash=hash_password("demo123"),
        phone="13800000000",
        email="demo@base.local",
    )
    db.add(user)
    db.add(
        UserTenantRel(
            rel_id=new_id("rel_"),
            user_id=user.user_id,
            tenant_id="tenant_edu",
            role_ids="role_edu_admin",
        )
    )
    db.add(
        UserTenantRel(
            rel_id=new_id("rel_"),
            user_id=user.user_id,
            tenant_id="tenant_ent",
            role_ids="role_ent_admin",
        )
    )

    # 模型配置
    db.add(
        ModelConfig(
            model_id="mock-gpt",
            model_name="mock-gpt",
            endpoint="",
            api_key="",
            status="active",
            max_token=4096,
            price_per_1k=0.01,
            provider="mock",
        )
    )

    # 配额
    for tenant_id, agent_id in [
        ("tenant_edu", "agent_yuwen"),
        ("tenant_ent", "agent_diagnose"),
    ]:
        db.add(
            AgentQuota(
                quota_id=new_id("qt_"),
                tenant_id=tenant_id,
                agent_id=agent_id,
                quota_type="token_month",
                limit_value=100000,
                used_value=0,
                reset_cycle="month",
            )
        )

    # Prompt 样例
    db.add(
        PromptTemplate(
            prompt_id="pt_edu_tutor_v1",
            tenant_id="tenant_edu",
            name="语文辅导助手",
            content="你是语文辅导老师，请用简洁易懂的方式回答学生问题。",
            version=1,
        )
    )

    # 插件样例
    db.add(
        PluginRegister(
            plugin_id="pg_edu_dict",
            tenant_id="tenant_edu",
            name="词典查询插件",
            endpoint="http://localhost:9001/dict",
            param_schema=json.dumps({"word": "string"}),
            status="active",
        )
    )

    # 工作流样例：检索 -> 大模型
    dsl = {
        "steps": [
            {"id": "r1", "type": "retrieve", "repo_id": "{{repo_id}}", "query": "{{query}}", "top_n": 3},
            {
                "id": "l1",
                "type": "llm",
                "model_id": "mock-gpt",
                "context_from": "r1",
                "prompt": "基于知识库回答。\n问题：{query}\n资料：{context}",
            },
        ]
    }
    # 注意：MVP 工作流 retrieve 使用 input.repo_id，这里存固定说明 DSL
    dsl_fixed = {
        "steps": [
            {"id": "r1", "type": "retrieve", "top_n": 3},
            {
                "id": "l1",
                "type": "llm",
                "model_id": "mock-gpt",
                "context_from": "r1",
                "prompt": "基于知识库回答。\n问题：{query}\n资料：{context}",
            },
        ]
    }
    db.add(
        WorkflowDef(
            wf_id="wf_edu_rag",
            tenant_id="tenant_edu",
            name="教育RAG问答",
            dsl_json=json.dumps(dsl_fixed, ensure_ascii=False),
            version=1,
        )
    )
    _ = dsl

    db.commit()
