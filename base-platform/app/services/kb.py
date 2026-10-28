import json
import re

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ids import new_id
from app.models import KnowledgeChunk, KnowledgeDocument, KnowledgeRepo, KnowledgeSnapshot
from app.services.embedding import (
    embed_text,
    embedding_from_json,
    embedding_to_json,
    top_k_by_vector,
)


def create_repo(db: Session, tenant_id: str, repo_name: str) -> KnowledgeRepo:
    repo = KnowledgeRepo(
        repo_id=new_id("kb_"),
        tenant_id=tenant_id,
        repo_name=repo_name,
        vector_index_name=f"idx_{tenant_id}_{repo_name}",
        status="active",
        version=1,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def split_text(text: str, chunk_size: int = 400) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[。！？；\n])", text)
    chunks: list[str] = []
    buf = ""
    for p in parts:
        if not p.strip():
            continue
        if len(buf) + len(p) <= chunk_size:
            buf += p
        else:
            if buf:
                chunks.append(buf.strip())
            if len(p) <= chunk_size:
                buf = p
            else:
                for i in range(0, len(p), chunk_size):
                    chunks.append(p[i : i + chunk_size].strip())
                buf = ""
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def ingest_document(
    db: Session,
    *,
    tenant_id: str,
    repo_id: str,
    doc_name: str,
    content: str,
    tags: str = "",
) -> dict:
    repo = db.get(KnowledgeRepo, repo_id)
    if not repo or repo.tenant_id != tenant_id:
        raise AppError("KB_NOT_FOUND", "知识库不存在或无权访问", 404)

    doc = KnowledgeDocument(
        doc_id=new_id("doc_"),
        repo_id=repo_id,
        tenant_id=tenant_id,
        doc_name=doc_name,
        tags=tags,
        chunk_count=0,
        version=1,
        status="active",
    )
    db.add(doc)
    chunks = []
    for part in split_text(content):
        vec = embed_text(part)
        chunk = KnowledgeChunk(
            chunk_id=new_id("ck_"),
            repo_id=repo_id,
            tenant_id=tenant_id,
            doc_id=doc.doc_id,
            doc_name=doc_name,
            content=part,
            tags=tags,
            embedding_json=embedding_to_json(vec),
        )
        db.add(chunk)
        chunks.append(chunk)
    doc.chunk_count = len(chunks)
    repo.version = (repo.version or 1) + 1
    db.add(doc)
    db.add(repo)
    db.commit()
    return {
        "doc_id": doc.doc_id,
        "doc_name": doc_name,
        "chunk_count": len(chunks),
        "repo_version": repo.version,
        "vectorized": True,
        "embedding_dim": len(embed_text("dim")),
    }


def list_documents(db: Session, tenant_id: str, repo_id: str) -> list[dict]:
    rows = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.repo_id == repo_id,
            KnowledgeDocument.status == "active",
        )
        .order_by(KnowledgeDocument.create_time.desc())
        .all()
    )
    return [
        {
            "doc_id": r.doc_id,
            "doc_name": r.doc_name,
            "tags": r.tags,
            "chunk_count": r.chunk_count,
            "version": r.version,
            "create_time": r.create_time.isoformat() + "Z" if r.create_time else None,
        }
        for r in rows
    ]


def delete_document(db: Session, tenant_id: str, doc_id: str) -> None:
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise AppError("DOC_NOT_FOUND", "文档不存在", 404)
    doc.status = "deleted"
    db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id).delete()
    repo = db.get(KnowledgeRepo, doc.repo_id)
    if repo:
        repo.version = (repo.version or 1) + 1
        db.add(repo)
    db.add(doc)
    db.commit()


def create_snapshot(db: Session, tenant_id: str, repo_id: str, note: str = "") -> dict:
    repo = db.get(KnowledgeRepo, repo_id)
    if not repo or repo.tenant_id != tenant_id:
        raise AppError("KB_NOT_FOUND", "知识库不存在", 404)
    docs = list_documents(db, tenant_id, repo_id)
    snap = KnowledgeSnapshot(
        snapshot_id=new_id("ks_"),
        repo_id=repo_id,
        tenant_id=tenant_id,
        version=repo.version or 1,
        note=note,
        payload_json=json.dumps({"documents": docs}, ensure_ascii=False),
    )
    db.add(snap)
    db.commit()
    return {
        "snapshot_id": snap.snapshot_id,
        "repo_id": repo_id,
        "version": snap.version,
        "note": note,
        "doc_count": len(docs),
    }


def reindex_repo(db: Session, tenant_id: str, repo_id: str) -> dict:
    rows = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.tenant_id == tenant_id, KnowledgeChunk.repo_id == repo_id)
        .all()
    )
    for row in rows:
        row.embedding_json = embedding_to_json(embed_text(row.content))
        db.add(row)
    db.commit()
    return {"repo_id": repo_id, "reindexed": len(rows)}


def search_chunks(
    db: Session,
    *,
    tenant_id: str,
    repo_id: str,
    query: str,
    top_n: int = 5,
    tags: str | None = None,
) -> list[dict]:
    q = db.query(KnowledgeChunk).filter(
        KnowledgeChunk.tenant_id == tenant_id,
        KnowledgeChunk.repo_id == repo_id,
    )
    if tags:
        q = q.filter(KnowledgeChunk.tags.contains(tags))
    rows = q.all()
    query_vec = embed_text(query)
    candidates = []
    for row in rows:
        vec = embedding_from_json(getattr(row, "embedding_json", "") or "")
        if vec is None:
            vec = embed_text(row.content)
            row.embedding_json = embedding_to_json(vec)
            db.add(row)
        candidates.append(
            (
                row.chunk_id,
                vec,
                {
                    "chunk_id": row.chunk_id,
                    "doc_id": row.doc_id,
                    "doc_name": row.doc_name,
                    "content": row.content,
                    "tags": row.tags,
                },
            )
        )
    db.commit()
    return top_k_by_vector(query_vec, candidates, top_n=top_n)
