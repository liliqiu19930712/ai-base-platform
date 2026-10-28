from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str
    tenant_id: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    agent_id: str = Field(..., description="智能体实例 ID")
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = 0.7


class KbCreateRequest(BaseModel):
    repo_name: str


class KbSearchRequest(BaseModel):
    repo_id: str
    query: str
    top_n: int = 5
    tags: str | None = None


class PromptSaveRequest(BaseModel):
    name: str
    content: str
    prompt_id: str | None = None


class WorkflowRunRequest(BaseModel):
    wf_id: str | None = None
    name: str | None = None
    dsl: dict | None = None
    input: dict = Field(default_factory=dict)


class PluginRegisterRequest(BaseModel):
    name: str
    endpoint: str
    param_schema: dict = Field(default_factory=dict)
    method: str = "POST"
    timeout_sec: int = 10
    category: str = "custom"


class PluginCallRequest(BaseModel):
    plugin_id: str
    params: dict = Field(default_factory=dict)


class AdminTenantCreateRequest(BaseModel):
    tenant_id: str | None = None
    tenant_name: str
    tenant_desc: str = ""
    enable_gateway: bool = True
    enable_kb: bool = True
    enable_workflow: bool = True
    enable_plugin: bool = True
    default_quota_limit: int = 100000
    default_agent_id: str = "default_agent"
    admin_username: str
    admin_password: str
    admin_email: str = ""
    contact_name: str = ""
    contact_email: str = ""


class AdminTenantUpdateRequest(BaseModel):
    tenant_name: str | None = None
    tenant_desc: str | None = None
    status: str | None = None
    enable_gateway: bool | None = None
    enable_kb: bool | None = None
    enable_workflow: bool | None = None
    enable_plugin: bool | None = None
    default_quota_limit: int | None = None
    contact_name: str | None = None
    contact_email: str | None = None


class AdminQuotaUpsertRequest(BaseModel):
    agent_id: str
    limit_value: int
