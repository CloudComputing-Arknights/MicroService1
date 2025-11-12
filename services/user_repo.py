from __future__ import annotations
from typing import Optional, List, Dict, Any
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from db import engine
from models.user import UserCreate, UserRead, UserUpdate

# ---- CRUD ----

async def create_user(payload: UserCreate) -> UserRead:
    user_id = str(uuid4())
    data = payload.model_dump(exclude={"password"})  # password is stored separately
    sql = text("""
        INSERT INTO users (id, username, email, phone, birth_date, avatar_url)
        VALUES (:id, :username, :email, :phone, :birth_date, :avatar_url)
    """)
    params = {
        "id": user_id,
        "username": data.get("username"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "birth_date": data.get("birth_date"),
        "avatar_url": str(data.get("avatar_url")) if data.get("avatar_url") else None,
    }
    try:
        async with engine.begin() as conn:
            await conn.execute(sql, params)
            row = await _fetch_user_by_id(conn, user_id)
    except IntegrityError as e:
        # username/email unique conflicts → 400 upstream
        raise e
    return _to_user_read(row)

async def get_user(user_id: str) -> Optional[UserRead]:
    async with engine.connect() as conn:
        row = await _fetch_user_by_id(conn, user_id)
    return _to_user_read(row) if row else None

async def get_user_by_username(username: str) -> Optional[UserRead]:
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT * FROM users WHERE username=:u"), {"u": username})
        row = res.mappings().first()
    return _to_user_read(row) if row else None

async def list_users(filters: Dict[str, Any], limit: int, offset: int) -> List[UserRead]:
    clauses = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    for k in ("username", "email", "phone"):
        v = filters.get(k)
        if v is not None:
            clauses.append(f"{k} = :{k}")
            params[k] = v
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = text(f"SELECT * FROM users {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    async with engine.connect() as conn:
        res = await conn.execute(sql, params)
        rows = res.mappings().all()
    return [_to_user_read(r) for r in rows]

async def update_user(user_id: str, patch: UserUpdate) -> Optional[UserRead]:
    data = patch.model_dump(exclude_unset=True)
    if not data:
        return await get_user(user_id)

    sets = []
    params: Dict[str, Any] = {"id": user_id}
    for k in ("username", "email", "phone", "birth_date", "avatar_url"):
        if k in data:
            sets.append(f"{k} = :{k}")
            params[k] = str(data[k]) if k == "avatar_url" and data[k] is not None else data[k]
    if not sets:
        return await get_user(user_id)

    sql = text(f"UPDATE users SET {', '.join(sets)} WHERE id = :id")
    try:
        async with engine.begin() as conn:
            await conn.execute(sql, params)
            row = await _fetch_user_by_id(conn, user_id)
    except IntegrityError as e:
        raise e
    return _to_user_read(row) if row else None

async def delete_user(user_id: str) -> bool:
    async with engine.begin() as conn:
        res = await conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
        deleted = res.rowcount or 0
        await conn.execute(text("DELETE FROM users_credentials WHERE user_id=:id"), {"id": user_id})
    return deleted > 0

# ---- Credentials ----

async def upsert_password_hash(user_id: str, password_hash: str) -> None:
    sql = text("""
        INSERT INTO users_credentials(user_id, password_hash)
        VALUES (:id, :h)
        ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash)
    """)
    async with engine.begin() as conn:
        await conn.execute(sql, {"id": user_id, "h": password_hash})

async def get_password_hash_by_user_id(user_id: str) -> Optional[str]:
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT password_hash FROM users_credentials WHERE user_id=:id"),
                                 {"id": user_id})
        row = res.mappings().first()
    return row["password_hash"] if row else None

# ---- helpers ----

async def _fetch_user_by_id(conn, user_id: str):
    res = await conn.execute(text("SELECT * FROM users WHERE id=:id"), {"id": user_id})
    return res.mappings().first()

def _to_user_read(row) -> UserRead:
    # row is a Mapping with DB columns
    return UserRead(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        phone=row["phone"],
        birth_date=row["birth_date"],
        avatar_url=row["avatar_url"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )