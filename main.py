from __future__ import annotations

import os
import socket
from datetime import datetime

from typing import Dict, List
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi import Query, Path
from typing import Optional

from models.user import UserCreate, UserRead, UserUpdate
from models.address import AddressCreate, AddressRead, AddressUpdate
from models.health import Health

port = int(os.environ.get("FASTAPIPORT", 8000))

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
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

@app.get("/addresses", response_model=List[AddressRead])
def list_addresses(
    street: Optional[str] = Query(None, description="Filter by street"),
    city: Optional[str] = Query(None, description="Filter by city"),
    state: Optional[str] = Query(None, description="Filter by state/region"),
    postal_code: Optional[str] = Query(None, description="Filter by postal code"),
    country: Optional[str] = Query(None, description="Filter by country"),
):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

@app.get("/addresses/{address_id}", response_model=AddressRead)
def get_address(address_id: UUID):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

@app.put("/addresses/{address_id}", response_model=AddressRead)
def update_address(address_id: UUID, update: AddressUpdate):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

@app.delete("/addresses/{address_id}", status_code=204)
def delete_address(address_id: UUID):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

# -----------------------------------------------------------------------------
# User endpoints
# -----------------------------------------------------------------------------
@app.post("/users", response_model=UserRead, status_code=201)
def create_user(user: UserCreate):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

@app.get("/users", response_model=List[UserRead])
def list_users(
    username: Optional[str] = Query(None, description="Filter by username"),
    email: Optional[str] = Query(None, description="Filter by email"),
    phone: Optional[str] = Query(None, description="Filter by phone number"),
    city: Optional[str] = Query(None, description="Filter by city of at least one address"),
    country: Optional[str] = Query(None, description="Filter by country of at least one address"),
):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

@app.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: UUID):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

@app.put("/users/{user_id}", response_model=UserRead)
def update_user(user_id: UUID, update: UserUpdate):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: UUID):
    raise HTTPException(status_code=501, detail="NOT IMPLEMENTED")

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
