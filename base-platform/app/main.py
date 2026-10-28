from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.bootstrap import ensure_bootstrap
from app.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.db import Base, SessionLocal, engine
from app.migrate import migrate_schema
from app.seed import seed_if_empty

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "文化智能体 · 基座平台：统一身份权限、模型网关、知识库、工作流、插件框架、安全合规审计"
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(api_router)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "console.html")

        @app.get("/demo")
        def demo_page():
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/admin")
        def admin_page():
            return FileResponse(STATIC_DIR / "admin.html")

        @app.get("/console")
        def console_page():
            return FileResponse(STATIC_DIR / "console.html")

        @app.get("/workflow-editor")
        def workflow_editor_page():
            return FileResponse(STATIC_DIR / "workflow-editor.html")

        @app.get("/culture")
        def culture_portal():
            return FileResponse(STATIC_DIR / "culture" / "index.html")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "capabilities": [
                "iam",
                "gateway",
                "knowledge",
                "workflow",
                "plugin",
                "compliance",
            ],
        }

    @app.on_event("startup")
    def on_startup():
        Base.metadata.create_all(bind=engine)
        migrate_schema()
        Base.metadata.create_all(bind=engine)  # 重建 migrate 中 drop 的表
        db = SessionLocal()
        try:
            seed_if_empty(db)
            ensure_bootstrap(db)
        finally:
            db.close()

    return app


app = create_app()
