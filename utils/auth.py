import os
import httpx
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from passlib.hash import bcrypt_sha256

# hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return bcrypt_sha256.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt_sha256.verify(plain, hashed)

# JWT
ALGO = "HS256"
JWT_EXPIRES_MIN = int(os.getenv("JWT_EXPIRES_MIN", "60"))

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_DEV_ONLY")  # put real secret in Secret Manager for prod
if os.getenv("ENV") == "prod" and JWT_SECRET == "CHANGE_ME_DEV_ONLY":
    raise RuntimeError("JWT_SECRET must be set in production")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
if not GOOGLE_CLIENT_ID:
    print("WARNING: GOOGLE_CLIENT_ID not set; Google OAuth will not work properly.")

def create_access_token(
    user_id: str,
    username: str,
    is_admin: bool,
    minutes: Optional[int] = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes or JWT_EXPIRES_MIN)
    payload = {
        "sub": user_id,
        "username": username,
        "role": "admin" if is_admin else "user",
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGO)

def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGO])

class GoogleTokenInfo(BaseModel):
    iss: str
    sub: str
    aud: str
    email: str
    email_verified: str | bool
    name: str | None = None
    picture: str | None = None
    iat: str | int
    exp: str | int

async def verify_google_id_token(id_token: str) -> GoogleTokenInfo:
    if not GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured")

    url = "https://oauth2.googleapis.com/tokeninfo"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, params={"id_token": id_token})

    if resp.status_code != 200:
        raise ValueError("Invalid Google ID token")

    data = resp.json()
    info = GoogleTokenInfo(**data)

    if info.aud != GOOGLE_CLIENT_ID:
        raise ValueError("Invalid audience for Google ID token")

    email_verified = (
        info.email_verified
        if isinstance(info.email_verified, bool)
        else info.email_verified.lower() == "true"
    )
    if not email_verified:
        raise ValueError("Google email not verified")

    return info
