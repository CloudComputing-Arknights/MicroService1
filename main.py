from __future__ import annotations
import os
import json, hashlib
import secrets
import logging
import uuid
from typing import Optional, Any
from uuid import UUID
from fastapi import FastAPI, HTTPException, Query, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.concurrency import run_in_threadpool
from models.user import UserCreate, UserRead, UserUpdate, UserInDB, UserPublic, UserPrivate, UserAdminView
from models.address import AddressCreate, AddressRead, AddressUpdate
from utils.cache import (
    user_cache, address_cache, user_list_cache, address_list_cache,
    filters_key, invalidate_user, invalidate_address
)
from utils.auth import hash_password, verify_password, create_access_token, decode_access_token, verify_google_id_token
from pydantic import BaseModel
from services.user_repo import (
    create_user as repo_create_user,
    get_user as repo_get_user,
    list_users as repo_list_users,
    update_user as repo_update_user,
    delete_user as repo_delete_user,
    get_user_with_auth_by_username as repo_get_user_with_auth_by_username,
    upsert_password_hash,
    get_user_with_auth_by_id as repo_get_user_with_auth_by_id,
    list_users_with_auth as repo_list_users_with_auth,
    get_user_by_email as repo_get_user_by_email,
)
from services.address_repo import (
    create_address as repo_create_address,
    get_address as repo_get_address,
    list_addresses as repo_list_addresses,
    update_address as repo_update_address,
    delete_address as repo_delete_address,
)
from sqlalchemy.exc import IntegrityError
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware

port = int(os.environ.get("FASTAPIPORT", 8000))

logger = logging.getLogger("user_address_service")

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):

        corr_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.state.correlation_id = corr_id

        logger.info(
            "Incoming request %s %s (correlation_id=%s)",
            request.method,
            request.url.path,
            corr_id,
        )

        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id

        logger.info(
            "Outgoing response %s %s (status=%s, correlation_id=%s)",
            request.method,
            request.url.path,
            response.status_code,
            corr_id,
        )
        return response

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

app.add_middleware(CorrelationIdMiddleware)

# -----------------------------------------------------------------------------
# Login & admin
# -----------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class CurrentPrincipal(BaseModel):
    id: UUID
    username: str
    role: str  # "user" or "admin"

class GoogleLoginRequest(BaseModel):
    id_token: str

@app.post("/auth/token", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user: UserInDB | None = await repo_get_user_with_auth_by_username(form.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    ok = await run_in_threadpool(verify_password, form.password, user.password_hash)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = create_access_token(
        user_id=str(user.id),
        username=user.username,
        is_admin=user.is_admin,
    )

    return Token(access_token=access_token, token_type="bearer")

@app.post("/auth/google", response_model=Token)
async def google_login(payload: GoogleLoginRequest):
    try:
        info = await verify_google_id_token(payload.id_token)
    except Exception as e:
        logger.warning("Google token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid Google token")

    email = info.email
    base_username = email.split("@")[0]

    user = await repo_get_user_by_email(email)

    if not user:
        tmp_password = secrets.token_urlsafe(32)
        hashed = await run_in_threadpool(hash_password, tmp_password)

        user_create = UserCreate(
            username=base_username,
            email=email,
            password=tmp_password,
        )

        try:
            user = await repo_create_user(user_create)
            await upsert_password_hash(str(user.id), hashed)
            logger.info(
                "Created local user from Google login: email=%s, user_id=%s",
                email,
                user.id,
            )
        except IntegrityError:
            logger.error("Integrity error while creating Google user for email=%s", email)
            raise HTTPException(status_code=400, detail="Unable to create user from Google account")

    access_token = create_access_token(
        user_id=str(user.id),
        username=user.username,
        is_admin=getattr(user, "is_admin", False),
    )

    logger.info("Issued JWT for Google user: email=%s, user_id=%s", email, user.id)

    return Token(access_token=access_token, token_type="bearer")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_principal(token: str = Depends(oauth2_scheme)) -> CurrentPrincipal:
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        username = payload.get("username")
        role = payload.get("role", "user")

        if not sub or not username:
            raise HTTPException(status_code=401, detail="Invalid token")

        return CurrentPrincipal(id=UUID(sub), username=username, role=role)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_admin(principal: CurrentPrincipal = Depends(get_current_principal)) -> CurrentPrincipal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return principal

async def get_current_user(
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> UserRead:
    user = await repo_get_user(str(principal.id))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@app.get("/auth/me", response_model=UserRead)
async def read_me(current_user: UserRead = Depends(get_current_user)):
    return current_user

@app.get("/admin/users", response_model=list[UserAdminView])
async def list_users_admin(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: CurrentPrincipal = Depends(get_current_admin),
):
    users = await repo_list_users_with_auth(limit, offset)

    return [
        UserAdminView(
            id=u.id,
            username=u.username,
            email=u.email,
            phone=u.phone,
            birth_date=u.birth_date,
            is_admin=u.is_admin,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]

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

@app.get("/users/{user_id}/public", response_model=UserPublic)
async def get_user_public(user_id: UUID, response: Response):
    sid = str(user_id)
    if sid in user_cache:
        u = user_cache[sid]
    else:
        u = await repo_get_user(sid)
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        user_cache[sid] = u

    public = UserPublic(id=u.id, username=u.username)
    set_cache_headers(response, ttl=user_cache.ttl, etag=etag_for(public.model_dump()))
    return public

@app.get("/users/{user_id}/private", response_model=UserPrivate)
async def get_user_private(
    user_id: UUID,
    response: Response,
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    # Authorization: owner or admin
    if principal.id != user_id and principal.role != "admin":
        raise HTTPException(status_code=403, detail="Not permitted to view this user")

    sid = str(user_id)
    u = await repo_get_user(sid)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    private = UserPrivate(
        id=u.id,
        username=u.username,
        email=u.email,
        phone=u.phone,
        birth_date=u.birth_date,
    )
    set_cache_headers(response, ttl=user_cache.ttl, etag=etag_for(private.model_dump()))
    return private

@app.get("/admin/users/{user_id}", response_model=UserAdminView)
async def get_user_admin(
    user_id: UUID,
    response: Response,
    principal: CurrentPrincipal = Depends(get_current_admin),
):
    sid = str(user_id)
    u = await repo_get_user_with_auth_by_id(sid)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    admin_view = UserAdminView(
        id=u.id,
        username=u.username,
        email=u.email,
        phone=u.phone,
        birth_date=u.birth_date,
        is_admin=u.is_admin,
        created_at=u.created_at,
        updated_at=u.updated_at,
    )
    set_cache_headers(response, ttl=user_cache.ttl, etag=etag_for(admin_view.model_dump()))
    return admin_view
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