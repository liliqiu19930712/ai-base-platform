"""SQLite 简易迁移：为已有库补齐新增列。"""

from sqlalchemy import text

from app.db import engine


ALTERS = [
    ("sys_user", "status", "VARCHAR(32) DEFAULT 'active'"),
    ("model_config", "price_per_1k", "FLOAT DEFAULT 0.01"),
    ("model_config", "provider", "VARCHAR(64) DEFAULT 'mock'"),
    ("kb_repo", "version", "INTEGER DEFAULT 1"),
    ("kb_chunk", "doc_id", "VARCHAR(64) DEFAULT ''"),
    ("prompt_template", "is_active", "BOOLEAN DEFAULT 1"),
    ("workflow_def", "status", "VARCHAR(32) DEFAULT 'active'"),
    ("plugin_register", "method", "VARCHAR(16) DEFAULT 'POST'"),
    ("plugin_register", "timeout_sec", "INTEGER DEFAULT 10"),
    ("plugin_register", "category", "VARCHAR(64) DEFAULT 'custom'"),
    ("sys_audit_log", "resource", "VARCHAR(128) DEFAULT ''"),
    ("sys_audit_log", "ip", "VARCHAR(64) DEFAULT ''"),
    ("kb_chunk", "embedding_json", "TEXT DEFAULT ''"),
]


def migrate_schema() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        # 旧版 agent_registry 以 agent_id 做全局主键，与多租户冲突，重建
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_registry'")).fetchall()
        if rows:
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(agent_registry)")).fetchall()}
            if "reg_id" not in cols:
                conn.execute(text("DROP TABLE agent_registry"))

        for table, column, coltype in ALTERS:
            info = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            if not info:
                continue
            existing = {r[1] for r in info}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
