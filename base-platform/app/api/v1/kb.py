from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import AppError, ok
from app.db import get_db
from app.models import KnowledgeRepo, KnowledgeSnapshot
from app.schemas.common import KbCreateRequest, KbSearchRequest
from app.services import kb as kb_service
from app.services.audit import write_audit
from app.services.tenant_admin import assert_feature_enabled

router = APIRouter(prefix="/kb", tags=["知识库服务"])


@router.post("/repo/create")
def create_repo(
    body: KbCreateRequest,
    user: CurrentUser = Depends(require_perm("kb:manage")),
    db: Session = Depends(get_db),
):
    assert_feature_enabled(db, user.tenant_id, "kb")
    repo = kb_service.create_repo(db, user.tenant_id, body.repo_name)
    write_audit(
        db,
        action="kb.repo.create",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=repo.repo_id,
        detail={"repo_name": repo.repo_name},
    )
    return ok(
        {
            "repo_id": repo.repo_id,
            "repo_name": repo.repo_name,
            "vector_index_name": repo.vector_index_name,
            "tenant_id": repo.tenant_id,
            "version": repo.version,
        }
    )


@router.get("/repo/list")
def list_repos(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = (
        db.query(KnowledgeRepo)
        .filter(KnowledgeRepo.tenant_id == user.tenant_id, KnowledgeRepo.status == "active")
        .order_by(KnowledgeRepo.create_time.desc())
        .all()
    )
    return ok(
        [
            {
                "repo_id": r.repo_id,
                "repo_name": r.repo_name,
                "version": r.version,
                "vector_index_name": r.vector_index_name,
            }
            for r in rows
        ]
    )


@router.post("/repo/document/upload")
async def upload_document(
    repo_id: str = Form(...),
    tags: str = Form(""),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_perm("kb:manage")),
    db: Session = Depends(get_db),
):
    assert_feature_enabled(db, user.tenant_id, "kb")
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="ignore")
    data = kb_service.ingest_document(
        db,
        tenant_id=user.tenant_id,
        repo_id=repo_id,
        doc_name=file.filename or "upload.txt",
        content=text,
        tags=tags,
    )
    write_audit(
        db,
        action="kb.doc.upload",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=data["doc_id"],
        detail=data,
    )
    return ok(data)


@router.get("/repo/{repo_id}/documents")
def list_documents(
    repo_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    return ok(kb_service.list_documents(db, user.tenant_id, repo_id))


@router.delete("/document/{doc_id}")
def delete_document(
    doc_id: str,
    user: CurrentUser = Depends(require_perm("kb:manage")),
    db: Session = Depends(get_db),
):
    kb_service.delete_document(db, user.tenant_id, doc_id)
    write_audit(
        db,
        action="kb.doc.delete",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=doc_id,
    )
    return ok({"doc_id": doc_id}, message="文档已删除")


@router.post("/repo/search")
def search(
    body: KbSearchRequest,
    user: CurrentUser = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    assert_feature_enabled(db, user.tenant_id, "kb")
    repo = db.get(KnowledgeRepo, body.repo_id)
    if not repo or repo.tenant_id != user.tenant_id:
        raise AppError("KB_NOT_FOUND", "知识库不存在或无权访问", 404)
    hits = kb_service.search_chunks(
        db,
        tenant_id=user.tenant_id,
        repo_id=body.repo_id,
        query=body.query,
        top_n=body.top_n,
        tags=body.tags,
    )
    return ok({"repo_id": body.repo_id, "query": body.query, "hits": hits})


@router.post("/repo/{repo_id}/snapshot")
def snapshot(
    repo_id: str,
    note: str = "",
    user: CurrentUser = Depends(require_perm("kb:manage")),
    db: Session = Depends(get_db),
):
    data = kb_service.create_snapshot(db, user.tenant_id, repo_id, note=note)
    return ok(data, message="知识库快照已创建")


@router.get("/repo/{repo_id}/snapshots")
def list_snapshots(
    repo_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(KnowledgeSnapshot)
        .filter(KnowledgeSnapshot.tenant_id == user.tenant_id, KnowledgeSnapshot.repo_id == repo_id)
        .order_by(KnowledgeSnapshot.create_time.desc())
        .all()
    )
    return ok(
        [
            {
                "snapshot_id": r.snapshot_id,
                "version": r.version,
                "note": r.note,
                "create_time": r.create_time.isoformat() + "Z" if r.create_time else None,
            }
            for r in rows
        ]
    )


@router.post("/repo/{repo_id}/reindex")
def reindex_repo(
    repo_id: str,
    user: CurrentUser = Depends(require_perm("kb:manage")),
    db: Session = Depends(get_db),
):
    data = kb_service.reindex_repo(db, user.tenant_id, repo_id)
    write_audit(
        db,
        action="kb.reindex",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=repo_id,
        detail=data,
    )
    return ok(data, message="向量索引已重建")
