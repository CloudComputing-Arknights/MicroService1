import os
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

def create_access_token(sub: str, minutes: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes or JWT_EXPIRES_MIN)
    payload = {"sub": sub, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGO)

def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGO])