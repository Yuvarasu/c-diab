import uuid
from dataclasses import dataclass
from typing import Iterator, Optional

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.context import AppContext
from app.domain import Role
from app.models import Profile, utcnow

bearer = HTTPBearer(auto_error=False)


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_db(ctx: AppContext = Depends(get_ctx)) -> Iterator[Session]:
    with ctx.session_factory() as session:
        yield session


def _unauthorized(msg: str = "Authentication required") -> ApiError:
    return ApiError(401, "unauthorized", msg)


def verify_jwt(token: str, ctx: AppContext) -> dict:
    """Verify a Supabase access token. Only HS256 (configured secret) and asymmetric JWKS algs are accepted."""
    s = ctx.settings
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256" and s.supabase_jwt_secret:
            key = s.supabase_jwt_secret
        elif alg in ("RS256", "ES256") and ctx.jwks_client:
            key = ctx.jwks_client.get_signing_key_from_jwt(token).key
        else:
            raise _unauthorized("Unsupported token")
        claims = jwt.decode(token, key, algorithms=[alg], audience=s.jwt_audience, leeway=10,
                            options={"require": ["exp", "sub"]})
        if s.supabase_url and claims.get("iss") != f"{s.supabase_url.rstrip('/')}/auth/v1":
            raise _unauthorized("Invalid token issuer")
        uuid.UUID(claims["sub"])
        return claims
    except ApiError:
        raise
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized("Invalid or expired session")


@dataclass
class Principal:
    id: uuid.UUID
    role: str
    profile: Profile


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer), ctx: AppContext = Depends(get_ctx),
                 db: Session = Depends(get_db)) -> Principal:
    if not creds:
        raise _unauthorized()
    claims = verify_jwt(creds.credentials, ctx)
    uid = uuid.UUID(claims["sub"])
    profile = db.get(Profile, uid)
    if profile is None:  # normally created by the auth.users trigger; this is a safety net
        meta = claims.get("user_metadata") or {}
        profile = Profile(id=uid, email=claims.get("email"), full_name=meta.get("full_name"), role=Role.customer.value,
                          created_at=utcnow())
        db.add(profile)
        db.commit()
    if profile.deleted_at is not None:
        raise ApiError(403, "account_deleted", "This account has been deleted.")
    return Principal(uid, profile.role, profile)  # role comes from the database, never from the token


def require_roles(*roles: Role):
    allowed = {r.value for r in roles}

    def dep(user: Principal = Depends(current_user)) -> Principal:
        if user.role not in allowed:
            raise ApiError(403, "forbidden", "You do not have access to this resource.")
        return user
    return dep


def limit(name: str, count: int, window_s: int):
    def dep(user: Principal = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> None:
        if not ctx.limiter.allow(f"{name}:{user.id}", count, window_s):
            raise ApiError(429, "rate_limited", "Too many requests. Please wait a moment and try again.")
    return dep
