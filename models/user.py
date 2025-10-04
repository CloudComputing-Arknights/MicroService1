from __future__ import annotations
from typing import Optional, List, Annotated
from uuid import UUID, uuid4
from datetime import date, datetime
from pydantic import BaseModel, Field, EmailStr, StringConstraints
from fastapi import HTTPException, Query
from .address import AddressBase

# Columbia UNI: 2–3 lowercase letters + 1–4 digits (e.g., abc1234)

class UserBase(BaseModel):
    username: str = Field(
        ...,
        description="Unique handle for the user.",
        json_schema_extra={"example": "alice"},
    )
    email: EmailStr = Field(
        ...,
        description="Primary email address.",
        json_schema_extra={"example": "alice@example.com"},
    )
    phone: Optional[str] = Field(
        None,
        description="Contact phone number.",
        json_schema_extra={"example": "+1-212-555-0199"},
    )
    birth_date: Optional[date] = Field(
        None,
        description="Date of birth (YYYY-MM-DD).",
        json_schema_extra={"example": "2000-09-01"},
    )

    # Embed addresses (each with persistent Address ID)
    addresses: List[AddressBase] = Field(
        default_factory=list,
        description="Addresses linked to this user (each has a persistent Address ID).",
        json_schema_extra={
            "example": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "street": "123 Main St",
                    "city": "New York",
                    "state": "NY",
                    "postal_code": "10001",
                    "country": "USA",
                }
            ]
        },
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "username": "alice",
                    "email": "alice@example.com",
                    "phone": "+1-212-555-0199",
                    "birth_date": "2000-09-01",
                    "addresses": [
                        {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "street": "123 Main St",
                            "city": "New York",
                            "state": "NY",
                            "postal_code": "10001",
                            "country": "USA",
                        }
                    ],
                }
            ]
        }
    }


class UserCreate(UserBase):
    """Creation payload for a User."""
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "username": "bob",
                    "email": "bob@example.com",
                    "phone": "+1-202-555-0101",
                    "birth_date": "1999-04-02",
                    "addresses": [
                        {
                            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                            "street": "221B Baker St",
                            "city": "London",
                            "state": None,
                            "postal_code": "NW1 6XE",
                            "country": "UK",
                        }
                    ],
                }
            ]
        }
    }


class UserUpdate(BaseModel):
    """Partial update for a User; supply only fields to change."""
    username: Optional[str] = Field(None, json_schema_extra={"example": "alice_new"})
    email: Optional[EmailStr] = Field(None, json_schema_extra={"example": "alice@newmail.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "+44 20 7946 0958"})
    birth_date: Optional[date] = Field(None, json_schema_extra={"example": "2000-09-01"})
    addresses: Optional[List[AddressBase]] = Field(
        None,
        description="Replace the entire set of addresses with this list.",
        json_schema_extra={
            "example": [
                {
                    "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    "street": "10 Downing St",
                    "city": "London",
                    "state": None,
                    "postal_code": "SW1A 2AA",
                    "country": "UK",
                }
            ]
        },
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"username": "alice_new"},
                {"email": "alice@newmail.com"},
                {
                    "addresses": [
                        {
                            "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                            "street": "10 Downing St",
                            "city": "London",
                            "state": None,
                            "postal_code": "SW1A 2AA",
                            "country": "UK",
                        }
                    ]
                },
            ]
        }
    }


class UserRead(UserBase):
    """Server representation returned to clients."""
    id: UUID = Field(
        default_factory=uuid4,
        description="Server-generated User ID.",
        json_schema_extra={"example": "99999999-9999-4999-8999-999999999999"},
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp (UTC).",
        json_schema_extra={"example": "2025-01-15T10:20:30Z"},
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp (UTC).",
        json_schema_extra={"example": "2025-01-16T12:00:00Z"},
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "99999999-9999-4999-8999-999999999999",
                    "username": "alice",
                    "email": "alice@example.com",
                    "phone": "+1-212-555-0199",
                    "birth_date": "2000-09-01",
                    "addresses": [
                        {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "street": "123 Main St",
                            "city": "New York",
                            "state": "NY",
                            "postal_code": "10001",
                            "country": "USA",
                        }
                    ],
                    "created_at": "2025-01-15T10:20:30Z",
                    "updated_at": "2025-01-16T12:00:00Z",
                }
            ]
        }
    }
