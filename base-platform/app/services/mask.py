import re


PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
ID_RE = re.compile(r"(?<!\d)(\d{6})\d{8}(\d{4}|\d{3}[Xx])(?!\d)")
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def mask_text(
    text: str,
    *,
    mask_phone: bool = True,
    mask_id_card: bool = True,
    mask_email: bool = True,
) -> str:
    if not text:
        return text
    out = text
    if mask_phone:
        out = PHONE_RE.sub(r"\1****\2", out)
    if mask_id_card:
        out = ID_RE.sub(r"\1********\2", out)
    if mask_email:
        out = EMAIL_RE.sub(r"\1***\2", out)
    return out
