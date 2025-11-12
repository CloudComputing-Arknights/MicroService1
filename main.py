from __future__ import annotations
import os
import json, hashlib
from typing import Optional, Any
from uuid import UUID
from fastapi import FastAPI, HTTPException, Response, Query, Depends
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.concurrency import run_in_threadpool
from models.user import UserCreate, UserRead, UserUpdate
from models.address import AddressCreate, AddressRead, AddressUpdate
from utils.cache import (
    user_cache, address_cache, user_list_cache, address_list_cache,
    filters_key, invalidate_user, invalidate_address
)
from utils.auth import hash_password, verify_password, create_access_token, decode_access_token
from pydantic import BaseModel
from services.user_repo import (
    create_user as repo_create_user,
    get_user as repo_get_user,
    list_users as repo_list_users,
    update_user as repo_update_user,
    delete_user as repo_delete_user,
    get_user_by_username as repo_get_user_by_username,
    upsert_password_hash,
    get_password_hash_by_user_id,
)
from services.address_repo import (
    create_address as repo_create_address,
    get_address as repo_get_address,
    list_addresses as repo_list_addresses,
    update_address as repo_update_address,
    delete_address as repo_delete_address,
)
from sqlalchemy.exc import IntegrityError

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
    addr_read = await repo_create_address(address)
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
        page = await repo_list_addresses(filters, limit, offset)
        address_list_cache[key] = page

    items = []
    for a in page:
        d = a.model_dump()
        d["_links"] = _address_links(a.id)
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
        out = await repo_get_address(sid)
        if not out:
            raise HTTPException(status_code=404, detail="Address not found")
        address_cache[sid] = out
    set_cache_headers(response, ttl=address_cache.ttl, etag=etag_for(out.model_dump()))
    return out
@app.put("/addresses/{address_id}", response_model=AddressRead)
async def update_address(address_id: UUID, update: AddressUpdate):
    new_addr = await repo_update_address(str(address_id), update)
    if not new_addr:
        raise HTTPException(status_code=404, detail="Address not found")
    invalidate_address(address_id)
    return new_addr
@app.delete("/addresses/{address_id}", status_code=204)
async def delete_address(address_id: UUID):
    ok = await repo_delete_address(str(address_id))
    if not ok:
        raise HTTPException(status_code=404, detail="Address not found")
    invalidate_address(address_id)
    return

# -----------------------------------------------------------------------------
# User endpoints
# -----------------------------------------------------------------------------
@app.post("/users", response_model=UserRead, status_code=201)
async def create_user(user: UserCreate, response: Response):
    try:
        hashed = await run_in_threadpool(hash_password, user.password)
        user_read = await repo_create_user(user)
        await upsert_password_hash(str(user_read.id), hashed)
        invalidate_user(user_read.id)
        response.headers["Location"] = f"/users/{user_read.id}"
        return user_read
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Username or email already exists")


@app.get("/users")
async def list_users(
    response: Response,
    username: Optional[str] = Query(None, description="Filter by username"),
    email: Optional[str] = Query(None, description="Filter by email"),
    phone: Optional[str] = Query(None, description="Filter by phone number"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    filters = {
        "username": username,
        "email": email,
        "phone": phone,
    }
    key = filters_key(filters, limit=limit, offset=offset)

    if key in user_list_cache:
        page = user_list_cache[key]
    else:
        page = await repo_list_users(filters, limit, offset)
        user_list_cache[key] = page

    items = []
    for u in page:
        d = u.model_dump()
        d["_links"] = _user_links(u.id)
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
        out = await repo_get_user(sid)
        if not out:
            raise HTTPException(status_code=404, detail="User not found")
        user_cache[sid] = out
    set_cache_headers(response, ttl=user_cache.ttl, etag=etag_for(out.model_dump()))
    return out

@app.put("/users/{user_id}", response_model=UserRead)
async def update_user(user_id: UUID, update: UserUpdate):
    try:
        new_user = await repo_update_user(str(user_id), update)
        if not new_user:
            raise HTTPException(status_code=404, detail="User not found")
        invalidate_user(user_id)
        return new_user
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Username or email already exists")

@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID):
    ok = await repo_delete_user(str(user_id))
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
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
    username = form.username
    user = await repo_get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    hashed = await get_password_hash_by_user_id(str(user.id))
    ok = hashed and await run_in_threadpool(verify_password, form.password, hashed)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(str(user.id))
    return Token(access_token=token)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserRead:
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = str(UUID(sub))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await repo_get_user(user_id)
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
