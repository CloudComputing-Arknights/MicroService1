from __future__ import annotations
import os
import json, hashlib
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID
from fastapi import FastAPI, HTTPException, Response, Query, Depends
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.concurrency import run_in_threadpool
from models.user import UserCreate, UserRead, UserUpdate
from models.address import AddressCreate, AddressRead, AddressUpdate
from db import ping
from utils.cache import (
    user_cache, address_cache, user_list_cache, address_list_cache,
    filters_key, invalidate_user, invalidate_address
)
from utils.auth import hash_password, verify_password, create_access_token, decode_access_token
from pydantic import BaseModel

port = int(os.environ.get("FASTAPIPORT", 8000))

def etag_for(obj) -> str:
    return hashlib.md5(json.dumps(obj, default=str, sort_keys=True).encode()).hexdigest()

def set_cache_headers(response: Response, ttl: int = 60, etag: str | None = None):
    response.headers["Cache-Control"] = f"public, max-age={ttl}"
    if etag:
        response.headers["ETag"] = etag

def _user_links(u_id: UUID):
    return {
        "self": {"href": f"/users/{u_id}"},
        "addresses": {"href": f"/users/{u_id}?include=addresses"},
    }

def _address_links(a_id: UUID):
    return {
        "self": {"href": f"/addresses/{a_id}"},
    }

def _rel_url(path: str, q: dict[str, Any]) -> str:
    # Build a relative URL like "/users?limit=50&offset=100&city=NY"
    parts = []
    for k, v in q.items():
        if v is None:
            continue
        parts.append(f"{k}={v}")
    return f"{path}{('?' + '&'.join(parts)) if parts else ''}"

write_lock = asyncio.Lock()
# -----------------------------------------------------------------------------
# Fake in-memory "databases"
# -----------------------------------------------------------------------------
users: Dict[UUID, UserRead] = {}
addresses: Dict[UUID, AddressRead] = {}

# credentials store (in-memory; replace with real DB later)
user_credentials: Dict[UUID, str] = {}
username_index: Dict[str, UUID] = {}

app = FastAPI(
    title="User/Address API",
    description="Demo FastAPI app using Pydantic v2 models for User and Address",
    version="0.1.0",
)

# -----------------------------------------------------------------------------
# Address endpoints
# -----------------------------------------------------------------------------

@app.post("/addresses", response_model=AddressRead, status_code=201)
async def create_address(address: AddressCreate, response: Response):
    async with write_lock:
        if address.id in addresses:
            raise HTTPException(status_code=400, detail="Address already exists")
        addr_read = AddressRead(**address.model_dump())
        addresses[addr_read.id] = addr_read
        invalidate_address(addr_read.id)
    response.headers["Location"] = f"/addresses/{addr_read.id}"
    return addr_read
@app.get("/addresses")
async def list_addresses(
    response: Response,
    street: Optional[str] = Query(None, description="Filter by street"),
    city: Optional[str] = Query(None, description="Filter by city"),
    state: Optional[str] = Query(None, description="Filter by state/region"),
    postal_code: Optional[str] = Query(None, description="Filter by postal code"),
    country: Optional[str] = Query(None, description="Filter by country"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    filters = {
        "street": street,
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "country": country,
    }
    key = filters_key(filters, limit=limit, offset=offset)

    if key in address_list_cache:
        page = address_list_cache[key]
    else:
        results = list(addresses.values())
        if street is not None:
            results = [a for a in results if a.street == street]
        if city is not None:
            results = [a for a in results if a.city == city]
        if state is not None:
            results = [a for a in results if a.state == state]
        if postal_code is not None:
            results = [a for a in results if a.postal_code == postal_code]
        if country is not None:
            results = [a for a in results if a.country == country]

        page = results[offset: offset + limit]

        async with write_lock:
            address_list_cache[key] = page
    items = []
    for a in page:
        d = a.model_dump()
        d["_links"] = {
            "self": {"href": f"/addresses/{a.id}"},
        }
        items.append(d)

        # collection links
    base_q = {**filters, "limit": limit, "offset": offset}
    next_q = {**base_q, "offset": offset + limit}
    prev_q = {**base_q, "offset": max(0, offset - limit)}

    collection_links = {
        "self": {"href": _rel_url("/addresses", base_q)},
        "next": {"href": _rel_url("/addresses", next_q)},
        "prev": {"href": _rel_url("/addresses", prev_q)},
    }

    response.headers["Link"] = (
        f'<{collection_links["next"]["href"]}>; rel="next", '
        f'<{collection_links["prev"]["href"]}>; rel="prev"'
    )
    set_cache_headers(response, ttl=address_list_cache.ttl, etag=etag_for([a.model_dump() for a in page]))
    return {"items": items, "_links": collection_links}

@app.get("/addresses/{address_id}", response_model=AddressRead)
async def get_address(address_id: UUID, response: Response):
    sid = str(address_id)
    if sid in address_cache:
        out = address_cache[sid]
    else:
        if address_id not in addresses:
            raise HTTPException(status_code=404, detail="Address not found")
        out = addresses[address_id]
        address_cache[sid] = out
    body = out.model_dump()
    body["_links"] = _address_links(out.id)
    set_cache_headers(response, ttl=address_cache.ttl, etag=etag_for(out.model_dump()))
    return body
@app.put("/addresses/{address_id}", response_model=AddressRead)
async def update_address(address_id: UUID, update: AddressUpdate):
    async with write_lock:
        if address_id not in addresses:
            raise HTTPException(status_code=404, detail="Address not found")
        stored = addresses[address_id].model_dump()
        stored.update(update.model_dump(exclude_unset=True))
        stored["updated_at"] = datetime.now(timezone.utc)  # ok for now; you can swap to aware UTC later
        new_addr = AddressRead(**stored)
        addresses[address_id] = new_addr

        touched_user_ids: list[UUID] = []
        for u in users.values():
            changed = False
            new_list = []
            for a in u.addresses:
                if a.id == address_id:
                    new_list.append(new_addr)
                    changed = True
                else:
                    new_list.append(a)
            if changed:
                u.addresses = new_list
                u.updated_at = datetime.now(timezone.utc)
                touched_user_ids.append(u.id)

        invalidate_address(address_id)
        user_list_cache.clear()
        for uid in touched_user_ids:
            invalidate_user(uid)
        return addresses[address_id]

@app.delete("/addresses/{address_id}", status_code=204)
async def delete_address(address_id: UUID):
    async with write_lock:
        if address_id not in addresses:
            raise HTTPException(status_code=404, detail="Address not found")

        touched_user_ids: list[UUID] = []

        for u in users.values():
            before = len(u.addresses)
            if before:
                u.addresses = [a for a in u.addresses if a.id != address_id]
                if len(u.addresses) != before:
                    u.updated_at = datetime.now(timezone.utc)
                    touched_user_ids.append(u.id)

        del addresses[address_id]
        invalidate_address(address_id)
        user_list_cache.clear()
        for uid in touched_user_ids:
            invalidate_user(uid)
    return

# -----------------------------------------------------------------------------
# User endpoints
# -----------------------------------------------------------------------------
@app.post("/users", response_model=UserRead, status_code=201)
async def create_user(user: UserCreate, response: Response):
    if user.username in username_index:
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed = await run_in_threadpool(hash_password, user.password)
    user_read = UserRead(**user.model_dump(exclude={"password"}))
    async with write_lock:
        users[user_read.id] = user_read
        user_credentials[user_read.id] = hashed
        username_index[user.username] = user_read.id

        invalidate_user(user_read.id)
    response.headers["Location"] = f"/users/{user_read.id}"
    return user_read

@app.get("/users")
async def list_users(
    response: Response,
    username: Optional[str] = Query(None, description="Filter by username"),
    email: Optional[str] = Query(None, description="Filter by email"),
    phone: Optional[str] = Query(None, description="Filter by phone number"),
    city: Optional[str] = Query(None, description="Filter by city of at least one address"),
    country: Optional[str] = Query(None, description="Filter by country of at least one address"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    filters = {
        "username": username,
        "email": email,
        "phone": phone,
        "city": city,
        "country": country,
    }
    key = filters_key(filters, limit=limit, offset=offset)

    if key in user_list_cache:
        page = user_list_cache[key]
    else:
        results = list(users.values())
        if username is not None:
            results = [u for u in results if u.username == username]
        if email is not None:
            results = [u for u in results if u.email == email]
        if phone is not None:
            results = [u for u in results if u.phone == phone]
        if city is not None:
            results = [u for u in results if any(addr.city == city for addr in u.addresses)]
        if country is not None:
            results = [u for u in results if any(addr.country == country for addr in u.addresses)]
        page = results[offset: offset + limit]
        async with write_lock:
            user_list_cache[key] = page

    items = []
    for u in page:
        d = u.model_dump()
        d["_links"] = {
            "self": {"href": f"/users/{u.id}"},
        }
        items.append(d)

    base_q = {**filters, "limit": limit, "offset": offset}
    next_q = {**base_q, "offset": offset + limit}
    prev_q = {**base_q, "offset": max(0, offset - limit)}

    collection_links = {
        "self": {"href": _rel_url("/users", base_q)},
        "next": {"href": _rel_url("/users", next_q)},
        "prev": {"href": _rel_url("/users", prev_q)},
    }

    response.headers["Link"] = (
        f'<{collection_links["next"]["href"]}>; rel="next", '
        f'<{collection_links["prev"]["href"]}>; rel="prev"'
    )

    set_cache_headers(response, ttl=user_list_cache.ttl, etag=etag_for([u.model_dump() for u in page]))
    return {"items": items, "_links": collection_links}

@app.get("/users/{user_id}", response_model=UserRead)
async def get_user(user_id: UUID, response: Response):
    sid = str(user_id)
    if sid in user_cache:
        out = user_cache[sid]
    else:
        if user_id not in users:
            raise HTTPException(status_code=404, detail="User not found")
        out = users[user_id]
        user_cache[sid] = out
    body = out.model_dump()
    body["_links"] = _user_links(out.id)
    set_cache_headers(response, ttl=user_cache.ttl, etag=etag_for(out.model_dump()))
    return out

@app.put("/users/{user_id}", response_model=UserRead)
async def update_user(user_id: UUID, update: UserUpdate):
    async with write_lock:
        if user_id not in users:
            raise HTTPException(status_code=404, detail="User not found")
        stored = users[user_id].model_dump()
        stored.update(update.model_dump(exclude_unset=True))
        stored["updated_at"] = datetime.now(timezone.utc)
        users[user_id] = UserRead(**stored)
        invalidate_user(user_id)
        return users[user_id]

@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID):
    async with write_lock:
        if user_id not in users:
            raise HTTPException(status_code=404, detail="User not found")
        del users[user_id]
        invalidate_user(user_id)
    return

# -----------------------------------------------------------------------------
# Login
# -----------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

@app.post("/auth/token", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """
    Accepts form fields: username, password.
    Returns: {access_token, token_type}
    """
    username = form.username
    if username not in username_index:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user_id = username_index[username]
    hashed = user_credentials.get(user_id)
    ok = hashed and await run_in_threadpool(verify_password, form.password, hashed)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(str(user_id))
    return Token(access_token=token)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserRead:
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = UUID(sub)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = users.get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@app.get("/auth/me", response_model=UserRead)
async def read_me(current_user: UserRead = Depends(get_current_user)):
    return current_user # to lock down some write operations later

# -----------------------------------------------------------------------------
# Root
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "Welcome to the User/Address API. See /docs for OpenAPI UI."}

# -----------------------------------------------------------------------------
# Entrypoint for `python main.py`
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
