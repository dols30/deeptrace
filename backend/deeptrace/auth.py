from __future__ import annotations

from functools import lru_cache
from datetime import datetime, timedelta, timezone
import hmac
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from deeptrace.config import Settings, settings

bearer = HTTPBearer(auto_error=False)


def local_auto_login_available(config: Settings = settings) -> bool:
    return bool(config.local_auto_login and config.deployment_mode == 'local'
                and config.auth_enabled and config.auth_mode == 'employee')


def _configured(config: Settings) -> tuple[str, str]:
    issuer = config.cognito_issuer
    client_id = config.cognito_app_client_id
    if not issuer or not client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is enabled but Cognito is not fully configured")
    return issuer, client_id


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_jwk_set=True, lifespan=3600)


def validate_access_token(token: str, config: Settings = settings) -> dict[str, Any]:
    if config.auth_mode == "employee":
        if not config.jwt_secret:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Employee authentication is not configured")
        try:
            return jwt.decode(token, config.jwt_secret, algorithms=["HS256"],
                issuer="deeptrace", audience="deeptrace-frontend", options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.PyJWTError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"}) from exc
    issuer, client_id = _configured(config)
    try:
        key = _jwks_client(issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer,
            options={"verify_aud": False}, required=["exp", "iat", "iss", "sub", "token_use", "client_id"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}) from exc
    if claims.get("token_use") != "access" or claims.get("client_id") != client_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token is not a valid access token for this application",
            headers={"WWW-Authenticate": "Bearer"})
    return claims


def employee_login(username: str, password: str, config: Settings = settings) -> tuple[str, str]:
    if not config.employee_username or not config.employee_password or not config.jwt_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Employee authentication is not configured")
    credentials = [
        (config.employee_username, config.employee_password, "analyst"),
        (config.supervisor_username, config.supervisor_password, "supervisor"),
        (config.reviewer_username, config.reviewer_password, "forensic_reviewer"),
        (config.admin_username, config.admin_password, "administrator"),
    ]
    role = None
    known_account = False
    for candidate_user, candidate_password, candidate_role in credentials:
        if not candidate_user or not hmac.compare_digest(username.encode(), candidate_user.encode()):
            continue
        known_account = True
        if candidate_password and hmac.compare_digest(password.encode(), candidate_password.encode()):
            role = candidate_role
        break
    if role is None and not known_account:
        from deeptrace.db.session import session_scope
        from deeptrace.workflow.service import authenticate_directory_user
        with session_scope() as session:
            directory_role = authenticate_directory_user(session, username, password)
        if directory_role == "investigator":
            role = "investigator"
        elif directory_role in {"forensic_reviewer", "supervisor", "administrator"}:
            role = directory_role
    if role is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": username, "role": role, "iat": now, "exp": now + timedelta(minutes=config.token_minutes),
        "iss": "deeptrace", "aud": "deeptrace-frontend", "auth_mode": "employee"}, config.jwt_secret, algorithm="HS256")
    return token, role


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
    if not settings.auth_enabled:
        return {"sub": "local-development", "role": "analyst", "auth_mode": "disabled"}
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required",
            headers={"WWW-Authenticate": "Bearer"})
    claims = validate_access_token(credentials.credentials)
    if "role" not in claims:
        groups = claims.get("cognito:groups", [])
        claims["role"] = "supervisor" if "supervisor" in groups else "analyst"
    return claims
