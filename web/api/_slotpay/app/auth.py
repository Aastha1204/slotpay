"""Supabase JWT verification for /admin/* routes."""
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient

from . import db
from .config import get_settings

_jwks: PyJWKClient | None = None


def _decode(token: str) -> dict:
    s = get_settings()
    global _jwks
    try:
        if s.supabase_jwks_url:
            if _jwks is None:
                _jwks = PyJWKClient(s.supabase_jwks_url)
            key = _jwks.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=["RS256", "ES256"], audience="authenticated")
        if s.supabase_jwt_secret:
            return jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError as e:
        raise HTTPException(401, "Invalid token") from e
    raise HTTPException(500, "Auth is not configured")


@dataclass
class Staff:
    id: UUID
    business_id: UUID
    email: str
    role: str


async def current_staff(authorization: str | None = Header(default=None)) -> Staff:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    claims = _decode(authorization.split(" ", 1)[1])
    async with db.connection() as conn:
        cur = await conn.execute(
            "select id, business_id, email, role from staff_user where id = %s", (claims["sub"],)
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(403, "Not a staff user")
    return Staff(**row)


def require_role(*roles: str):
    async def dep(staff: Staff = Depends(current_staff)) -> Staff:
        if staff.role not in roles:
            raise HTTPException(403, "Insufficient role")
        return staff

    return dep
