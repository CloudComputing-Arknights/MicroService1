from __future__ import annotations
from datetime import datetime
import os
import json, hashlib
from typing import Dict, List, Optional
from uuid import UUID
from fastapi import FastAPI, HTTPException, Response, Query
from models.user import UserCreate, UserRead, UserUpdate
from models.address import AddressCreate, AddressRead, AddressUpdate
from utils.cache import (
    user_cache, address_cache, user_list_cache, address_list_cache,
    filters_key, invalidate_user, invalidate_address
)

port = int(os.environ.get("FASTAPIPORT", 8000))

def etag_for(obj) -> str:
    return hashlib.md5(json.dumps(obj, default=str, sort_keys=True).encode()).hexdigest()

def set_cache_headers(response: Response, ttl: int = 60, etag: str | None = None):
    response.headers["Cache-Control"] = f"public, max-age={ttl}"
    if etag:
        response.headers["ETag"] = etag
# -----------------------------------------------------------------------------
# Fake in-memory "databases"
# -----------------------------------------------------------------------------
users: Dict[UUID, UserRead] = {}
addresses: Dict[UUID, AddressRead] = {}

app = FastAPI(
    title="User/Address API",
    description="Demo FastAPI app using Pydantic v2 models for User and Address",
    version="0.1.0",
)

# -----------------------------------------------------------------------------
# Address endpoints
# -----------------------------------------------------------------------------

@app.post("/addresses", response_model=AddressRead, status_code=201)
def create_address(address: AddressCreate):
    if address.id in addresses:
        raise HTTPException(status_code=400, detail="Address already exists")
    addr_read = AddressRead(**address.model_dump())
    addresses[addr_read.id] = addr_read
    invalidate_address(addr_read.id)
    return addr_read
@app.get("/addresses", response_model=List[AddressRead])
def list_addresses(
    street: Optional[str] = Query(None, description="Filter by street"),
    city: Optional[str] = Query(None, description="Filter by city"),
    state: Optional[str] = Query(None, description="Filter by state/region"),
    postal_code: Optional[str] = Query(None, description="Filter by postal code"),
    country: Optional[str] = Query(None, description="Filter by country"),
    response: Response,
):
    filters = {
        "street": street,
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "country": country,
    }
    key = filters_key(filters)

    if key in address_list_cache:
        results = address_list_cache[key]
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
        address_list_cache[key] = results

    set_cache_headers(response, ttl=address_list_cache.ttl, etag=etag_for([a.model_dump() for a in results]))
    return results

@app.get("/addresses/{address_id}", response_model=AddressRead)
def get_address(address_id: UUID, response: Response):
    sid = str(address_id)
    if sid in address_cache:
        out = address_cache[sid]
    else:
        if address_id not in addresses:
            raise HTTPException(status_code=404, detail="Address not found")
        out = addresses[address_id]
        address_cache[sid] = out

    set_cache_headers(response, ttl=address_cache.ttl, etag=etag_for(out.model_dump()))
    return out
@app.put("/addresses/{address_id}", response_model=AddressRead)
def update_address(address_id: UUID, update: AddressUpdate):
    if address_id not in addresses:
        raise HTTPException(status_code=404, detail="Address not found")
    stored = addresses[address_id].model_dump()
    stored.update(update.model_dump(exclude_unset=True))
    stored["updated_at"] = datetime.utcnow()  # ok for now; you can swap to aware UTC later
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
            u.updated_at = datetime.utcnow()
            touched_user_ids.append(u.id)

    invalidate_address(address_id)
    user_list_cache.clear()
    for uid in touched_user_ids:
        invalidate_user(uid)
    return addresses[address_id]

@app.delete("/addresses/{address_id}", status_code=204)
def delete_address(address_id: UUID):
    if address_id not in addresses:
        raise HTTPException(status_code=404, detail="Address not found")

    touched_user_ids: list[UUID] = []

    for u in users.values():
        before = len(u.addresses)
        if before:
            u.addresses = [a for a in u.addresses if a.id != address_id]
            if len(u.addresses) != before:
                u.updated_at = datetime.utcnow()
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
def create_user(user: UserCreate):
    user_read = UserRead(**user.model_dump())
    users[user_read.id] = user_read
    invalidate_user(user_read.id)
    return user_read

@app.get("/users", response_model=List[UserRead])
def list_users(
    username: Optional[str] = Query(None, description="Filter by username"),
    email: Optional[str] = Query(None, description="Filter by email"),
    phone: Optional[str] = Query(None, description="Filter by phone number"),
    city: Optional[str] = Query(None, description="Filter by city of at least one address"),
    country: Optional[str] = Query(None, description="Filter by country of at least one address"),
    response: Response,
):
    filters = {
        "username": username,
        "email": email,
        "phone": phone,
        "city": city,
        "country": country,
    }
    key = filters_key(filters)

    if key in user_list_cache:
        results = user_list_cache[key]
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
        user_list_cache[key] = results

    set_cache_headers(response, ttl=user_list_cache.ttl, etag=etag_for([u.model_dump() for u in results]))
    return results

@app.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, response: Response):
    sid = str(user_id)
    if sid in user_cache:
        out = user_cache[sid]
    else:
        if user_id not in users:
            raise HTTPException(status_code=404, detail="User not found")
        out = users[user_id]
        user_cache[sid] = out

    set_cache_headers(response, ttl=user_cache.ttl, etag=etag_for(out.model_dump()))
    return out

@app.put("/users/{user_id}", response_model=UserRead)
def update_user(user_id: UUID, update: UserUpdate):
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    stored = users[user_id].model_dump()
    stored.update(update.model_dump(exclude_unset=True))
    stored["updated_at"] = datetime.utcnow()
    users[user_id] = UserRead(**stored)
    invalidate_user(user_id)
    return users[user_id]

@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: UUID):
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    del users[user_id]
    invalidate_user(user_id)
    return

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
