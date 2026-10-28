from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def now() -> datetime:
    return datetime.utcnow()


class Tenant(Base):
    __tablename__ = "sys_tenant"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_desc: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class TenantFeature(Base):
    __tablename__ = "sys_tenant_feature"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enable_gateway: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_kb: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_workflow: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_plugin: Mapped[bool] = mapped_column(Boolean, default=True)
    default_quota_limit: Mapped[int] = mapped_column(Integer, default=100000)
    api_credential: Mapped[str] = mapped_column(String(128), default="")
    contact_name: Mapped[str] = mapped_column(String(64), default="")
    contact_email: Mapped[str] = mapped_column(String(128), default="")
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class PlatformAdmin(Base):
    __tablename__ = "sys_platform_admin"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    remark: Mapped[str] = mapped_column(String(256), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class User(Base):
    __tablename__ = "sys_user"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active/disabled
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class UserTenantRel(Base):
    __tablename__ = "sys_user_tenant_rel"

    rel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role_ids: Mapped[str] = mapped_column(String(512), default="")


class Role(Base):
    __tablename__ = "sys_role"

    role_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_json: Mapped[str] = mapped_column(Text, default="[]")


class Permission(Base):
    __tablename__ = "sys_permission"

    perm_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    perm_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    perm_desc: Mapped[str] = mapped_column(String(256), default="")


class ModelConfig(Base):
    __tablename__ = "model_config"

    model_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), default="")
    api_key: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    max_token: Mapped[int] = mapped_column(Integer, default=4096)
    price_per_1k: Mapped[float] = mapped_column(Float, default=0.01)
    provider: Mapped[str] = mapped_column(String(64), default="mock")


class AgentRegistry(Base):
    """租户内智能体实例登记（同一 agent_id 可在不同租户各自存在）。"""

    __tablename__ = "agent_registry"

    reg_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    default_model_id: Mapped[str] = mapped_column(String(64), default="mock-gpt")
    status: Mapped[str] = mapped_column(String(32), default="active")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class AgentQuota(Base):
    __tablename__ = "agent_quota"

    quota_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    quota_type: Mapped[str] = mapped_column(String(32), default="token_month")
    limit_value: Mapped[int] = mapped_column(Integer, default=100000)
    used_value: Mapped[int] = mapped_column(Integer, default=0)
    reset_cycle: Mapped[str] = mapped_column(String(32), default="month")


class ModelCallLog(Base):
    __tablename__ = "model_call_log"

    log_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[str] = mapped_column(String(64), default="")
    model_id: Mapped[str] = mapped_column(String(64), default="")
    input_snippet: Mapped[str] = mapped_column(Text, default="")
    output_snippet: Mapped[str] = mapped_column(Text, default="")
    token_used: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="success")
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    call_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class KnowledgeRepo(Base):
    __tablename__ = "kb_repo"

    repo_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False)
    vector_index_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class KnowledgeDocument(Base):
    __tablename__ = "kb_document"

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repo_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    doc_name: Mapped[str] = mapped_column(String(256), nullable=False)
    tags: Mapped[str] = mapped_column(String(256), default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class KnowledgeChunk(Base):
    __tablename__ = "kb_chunk"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repo_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    doc_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    doc_name: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(String(256), default="")
    embedding_json: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class KnowledgeSnapshot(Base):
    """知识库版本快照（简易：保存当时文档清单 JSON）。"""

    __tablename__ = "kb_snapshot"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repo_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str] = mapped_column(String(256), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class PromptTemplate(Base):
    __tablename__ = "prompt_template"

    prompt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class WorkflowDef(Base):
    __tablename__ = "workflow_def"

    wf_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    dsl_json: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class PluginRegister(Base):
    __tablename__ = "plugin_register"

    plugin_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(String(16), default="POST")
    param_schema: Mapped[str] = mapped_column(Text, default="{}")
    timeout_sec: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(32), default="active")
    category: Mapped[str] = mapped_column(String(64), default="custom")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class PluginCallLog(Base):
    __tablename__ = "plugin_call_log"

    log_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plugin_id: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[str] = mapped_column(String(64), default="")
    request_snippet: Mapped[str] = mapped_column(Text, default="")
    response_snippet: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="success")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    call_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChatSession(Base):
    __tablename__ = "chat_session"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChatMessage(Base):
    __tablename__ = "chat_message"

    msg_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class ComplianceConfig(Base):
    __tablename__ = "compliance_config"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(128), default="合规免责提示")
    content: Mapped[str] = mapped_column(Text, default="")
    mask_phone: Mapped[bool] = mapped_column(Boolean, default=True)
    mask_id_card: Mapped[bool] = mapped_column(Boolean, default=True)
    mask_email: Mapped[bool] = mapped_column(Boolean, default=True)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class GrayRelease(Base):
    __tablename__ = "gray_release"

    gray_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), default="prompt")  # prompt/workflow
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    percent: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    status: Mapped[str] = mapped_column(String(32), default="active")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class AbExperiment(Base):
    __tablename__ = "ab_experiment"

    exp_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), default="prompt")
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    treatment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    traffic_percent: Mapped[int] = mapped_column(Integer, default=50)  # 进入 treatment 的比例
    status: Mapped[str] = mapped_column(String(32), default="active")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class AbEvent(Base):
    __tablename__ = "ab_event"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    exp_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="")
    variant: Mapped[str] = mapped_column(String(32), default="control")  # control/treatment
    metric: Mapped[str] = mapped_column(String(64), default="call")
    value: Mapped[float] = mapped_column(Float, default=1.0)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class SsoTicket(Base):
    __tablename__ = "sso_ticket"

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), default="")
    redirect_uri: Mapped[str] = mapped_column(String(512), default="")
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    expire_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "sys_audit_log"

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(128), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
