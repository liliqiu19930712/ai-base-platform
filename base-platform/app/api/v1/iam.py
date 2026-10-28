import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require_perm, require_tenant
from app.core.errors import AppError, ok
from app.core.ids import new_id
from app.core.security import hash_password, verify_password
from app.db import get_db
from app.models import Role, User, UserTenantRel
from app.services.audit import write_audit
from app.services.rbac import get_user_permissions

router = APIRouter(prefix="/iam", tags=["身份与权限"])


class RegisterRequest(BaseModel):
    username: str
    password: str = Field(min_length=6)
    email: str = ""
    phone: str = ""


class RoleCreateRequest(BaseModel):
    role_name: str
    permissions: list[str] = Field(default_factory=list)


class BindRoleRequest(BaseModel):
    user_id: str
    role_ids: list[str]


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


@router.post("/register")
def register_user(
    body: RegisterRequest,
    user: CurrentUser = Depends(require_perm("tenant:admin")),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == body.username).first():
        raise AppError("USER_EXISTS", "用户名已存在", 409)
    # 默认访客角色
    role = (
        db.query(Role)
        .filter(Role.tenant_id == user.tenant_id, Role.role_name == "普通用户")
        .first()
    )
    if not role:
        role = Role(
            role_id=new_id("role_"),
            tenant_id=user.tenant_id,
            role_name="普通用户",
            permission_json=json.dumps(["gateway:invoke", "kb:manage"]),
        )
        db.add(role)
        db.flush()
    u = User(
        user_id=new_id("user_"),
        username=body.username.strip(),
        password_hash=hash_password(body.password),
        email=body.email,
        phone=body.phone,
        status="active",
    )
    rel = UserTenantRel(
        rel_id=new_id("rel_"),
        user_id=u.user_id,
        tenant_id=user.tenant_id,
        role_ids=role.role_id,
    )
    db.add_all([u, rel])
    db.commit()
    write_audit(
        db,
        action="iam.register",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=u.user_id,
        detail={"username": u.username},
    )
    return ok({"user_id": u.user_id, "username": u.username, "role_id": role.role_id})


@router.get("/users")
def list_users(user: CurrentUser = Depends(require_perm("tenant:admin")), db: Session = Depends(get_db)):
    rels = db.query(UserTenantRel).filter(UserTenantRel.tenant_id == user.tenant_id).all()
    items = []
    for rel in rels:
        u = db.get(User, rel.user_id)
        if not u:
            continue
        items.append(
            {
                "user_id": u.user_id,
                "username": u.username,
                "email": u.email,
                "phone": u.phone,
                "status": getattr(u, "status", "active"),
                "role_ids": rel.role_ids,
            }
        )
    return ok(items)


@router.post("/roles")
def create_role(
    body: RoleCreateRequest,
    user: CurrentUser = Depends(require_perm("tenant:admin")),
    db: Session = Depends(get_db),
):
    role = Role(
        role_id=new_id("role_"),
        tenant_id=user.tenant_id,
        role_name=body.role_name,
        permission_json=json.dumps(body.permissions, ensure_ascii=False),
    )
    db.add(role)
    db.commit()
    write_audit(
        db,
        action="iam.role.create",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=role.role_id,
        detail={"role_name": role.role_name, "permissions": body.permissions},
    )
    return ok(
        {
            "role_id": role.role_id,
            "role_name": role.role_name,
            "permissions": body.permissions,
        }
    )


@router.get("/roles")
def list_roles(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    rows = db.query(Role).filter(Role.tenant_id == user.tenant_id).all()
    items = []
    for r in rows:
        try:
            perms = json.loads(r.permission_json or "[]")
        except json.JSONDecodeError:
            perms = []
        items.append({"role_id": r.role_id, "role_name": r.role_name, "permissions": perms})
    return ok(items)


@router.post("/bind-role")
def bind_role(
    body: BindRoleRequest,
    user: CurrentUser = Depends(require_perm("tenant:admin")),
    db: Session = Depends(get_db),
):
    rel = (
        db.query(UserTenantRel)
        .filter(UserTenantRel.user_id == body.user_id, UserTenantRel.tenant_id == user.tenant_id)
        .first()
    )
    if not rel:
        raise AppError("USER_NOT_IN_TENANT", "用户不在当前租户", 404)
    rel.role_ids = ",".join(body.role_ids)
    db.add(rel)
    db.commit()
    write_audit(
        db,
        action="iam.bind_role",
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        resource=body.user_id,
        detail={"role_ids": body.role_ids},
    )
    return ok({"user_id": body.user_id, "role_ids": body.role_ids})


@router.get("/my-permissions")
def my_permissions(user: CurrentUser = Depends(require_tenant), db: Session = Depends(get_db)):
    perms = sorted(get_user_permissions(db, user.user_id, user.tenant_id))
    return ok({"tenant_id": user.tenant_id, "permissions": perms, "is_platform_admin": user.is_platform_admin})


@router.post("/change-password")
def change_password(
    body: PasswordChangeRequest,
    user: CurrentUser = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    u = db.get(User, user.user_id)
    if not u or not verify_password(body.old_password, u.password_hash):
        raise AppError("PASSWORD_INVALID", "原密码错误", 400)
    u.password_hash = hash_password(body.new_password)
    db.add(u)
    db.commit()
    return ok({"user_id": u.user_id}, message="密码已更新")
