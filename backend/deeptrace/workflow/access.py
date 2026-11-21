"""Backend authorization. Frontend checks are not sufficient."""

import hashlib
import hmac
import re
from secrets import token_bytes

from deeptrace.db.models import Analysis, User

INVESTIGATOR = {"analyst", "investigator"}
DISPOSITIONS = {"agree", "disagree", "uncertain", "needs_expert_review"}
EDITABLE_STATUSES = {"AI_SCREENING_COMPLETE", "INVESTIGATOR_REVIEW", "CHANGES_REQUESTED"}


class WorkflowError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def canonical_role(role: str) -> str:
    if role in INVESTIGATOR:
        return "investigator"
    return role


def hash_password(password: str) -> str:
    salt = token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


def can_read(user: dict, analysis: Analysis) -> bool:
    role = canonical_role(str(user.get("role", "")))
    if role == "administrator" or role == "supervisor":
        return True
    if role == "investigator" and analysis.owner.username == user.get("sub"):
        return True
    if role == "forensic_reviewer" and analysis.status == "EXPERT_REVIEW_REQUESTED":
        return True
    return False


def can_review_finding(user: dict, analysis: Analysis) -> bool:
    role = canonical_role(str(user.get("role", "")))
    if role == "investigator" and analysis.owner.username == user.get("sub"):
        return True
    if role == "forensic_reviewer" and analysis.status == "EXPERT_REVIEW_REQUESTED":
        return True
    if role == "administrator":
        return True
    return False


def mentions_in(body: str) -> list[str]:
    return sorted(set(re.findall(r"@([A-Za-z0-9._-]{1,128})", body)))


def display_user(user: User) -> dict:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role_name,
        "active": user.active,
    }
