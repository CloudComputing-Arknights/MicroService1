from __future__ import annotations
from typing import Optional, List, Dict, Any
from uuid import uuid4
from sqlalchemy import text
from db import engine
from models.address import AddressCreate, AddressRead, AddressUpdate

async def create_address(payload: AddressCreate) -> AddressRead:
    addr_id = str(uuid4())
    data = payload.model_dump()
    sql = text("""
        INSERT INTO addresses (id, street, city, state, postal_code, country)
        VALUES (:id, :street, :city, :state, :postal_code, :country)
    """)
    params = {"id": addr_id, **data}
    async with engine.begin() as conn:
        await conn.execute(sql, params)
        row = await _fetch_address_by_id(conn, addr_id)
    return _to_address_read(row)

async def get_address(address_id: str) -> Optional[AddressRead]:
    async with engine.connect() as conn:
        row = await _fetch_address_by_id(conn, address_id)
    return _to_address_read(row) if row else None

async def list_addresses(filters: Dict[str, Any], limit: int, offset: int) -> List[AddressRead]:
    clauses, params = [], {"limit": limit, "offset": offset}
    for k in ("street", "city", "state", "postal_code", "country"):
        v = filters.get(k)
        if v is not None:
            clauses.append(f"{k} = :{k}")
            params[k] = v
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = text(f"SELECT * FROM addresses {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    async with engine.connect() as conn:
        res = await conn.execute(sql, params)
        rows = res.mappings().all()
    return [_to_address_read(r) for r in rows]

async def update_address(address_id: str, patch: AddressUpdate) -> Optional[AddressRead]:
    data = patch.model_dump(exclude_unset=True)
    if not data:
        return await get_address(address_id)

    sets = []
    params = {"id": address_id}
    for k in ("street", "city", "state", "postal_code", "country"):
        if k in data:
            sets.append(f"{k} = :{k}")
            params[k] = data[k]
    if not sets:
        return await get_address(address_id)

    sql = text(f"UPDATE addresses SET {', '.join(sets)} WHERE id = :id")
    async with engine.begin() as conn:
        await conn.execute(sql, params)
        row = await _fetch_address_by_id(conn, address_id)
    return _to_address_read(row) if row else None

async def delete_address(address_id: str) -> bool:
    async with engine.begin() as conn:
        res = await conn.execute(text("DELETE FROM addresses WHERE id=:id"), {"id": address_id})
        return (res.rowcount or 0) > 0

# helpers
async def _fetch_address_by_id(conn, addr_id: str):
    res = await conn.execute(text("SELECT * FROM addresses WHERE id=:id"), {"id": addr_id})
    return res.mappings().first()

def _to_address_read(row) -> AddressRead:
    return AddressRead(
        id=row["id"],
        street=row["street"],
        city=row["city"],
        state=row["state"],
        postal_code=row["postal_code"],
        country=row["country"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )