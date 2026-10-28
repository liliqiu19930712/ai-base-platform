"""启动时补齐平台管理员、租户能力、智能体登记与合规配置。"""

from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.security import hash_password
from app.models import (
    AgentQuota,
    AgentRegistry,
    ComplianceConfig,
    PlatformAdmin,
    Tenant,
    User,
)
from app.services.tenant_admin import ensure_feature


def ensure_bootstrap(db: Session) -> None:
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            user_id="user_platform_admin",
            username="admin",
            password_hash=hash_password("admin123"),
            email="admin@base.local",
            status="active",
        )
        db.add(admin)
        db.flush()
    else:
        if not getattr(admin, "status", None):
            admin.status = "active"
            db.add(admin)

    if not db.get(PlatformAdmin, admin.user_id):
        db.add(PlatformAdmin(user_id=admin.user_id, remark="基座默认平台管理员"))

    for tenant in db.query(Tenant).all():
        ensure_feature(db, tenant.tenant_id)

        # 配额补登记到 AgentRegistry（按租户隔离）
        quotas = db.query(AgentQuota).filter(AgentQuota.tenant_id == tenant.tenant_id).all()
        for q in quotas:
            exists = (
                db.query(AgentRegistry)
                .filter(AgentRegistry.tenant_id == q.tenant_id, AgentRegistry.agent_id == q.agent_id)
                .first()
            )
            if not exists:
                db.add(
                    AgentRegistry(
                        reg_id=new_id("reg_"),
                        agent_id=q.agent_id,
                        tenant_id=q.tenant_id,
                        agent_name=q.agent_id,
                        description="历史配额自动补登记",
                        default_model_id="mock-gpt",
                        status="active",
                    )
                )

        # 合规配置补齐
        exists = db.query(ComplianceConfig).filter(ComplianceConfig.tenant_id == tenant.tenant_id).first()
        if not exists:
            db.add(
                ComplianceConfig(
                    config_id=new_id("cmp_"),
                    tenant_id=tenant.tenant_id,
                    title="合规免责提示",
                    content=f"【{tenant.tenant_name}】本智能体输出仅供参考，不构成专业意见。",
                    mask_phone=True,
                    mask_id_card=True,
                    mask_email=True,
                )
            )

    db.commit()
