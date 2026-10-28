from fastapi import APIRouter

from app.api.v1 import (
    admin,
    agent,
    auth,
    compliance,
    gateway,
    iam,
    kb,
    log,
    model,
    plugin,
    prompt,
    quota,
    workflow,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(iam.router)
api_router.include_router(agent.router)
api_router.include_router(gateway.router)
api_router.include_router(model.router)
api_router.include_router(kb.router)
api_router.include_router(prompt.router)
api_router.include_router(workflow.router)
api_router.include_router(plugin.router)
api_router.include_router(quota.router)
api_router.include_router(compliance.router)
api_router.include_router(log.router)
