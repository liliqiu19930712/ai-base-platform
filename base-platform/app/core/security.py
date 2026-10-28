import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.config import get_settings

ALGORITHM = "HS256"
settings = get_settings()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        algo, salt, digest = hashed.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 120000)
        return hmac.compare_digest(check.hex(), digest)
    except ValueError:
        return False


def create_access_token(subject: dict[str, Any], expires_minutes: int | None = None) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {**subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("无效或过期的 token") from exc
