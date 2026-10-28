import uuid


def new_id(prefix: str = "") -> str:
    uid = uuid.uuid4().hex[:16]
    return f"{prefix}{uid}" if prefix else uid
