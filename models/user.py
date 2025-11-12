from __future__ import annotations
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import date, datetime, timezone
from pydantic import BaseModel, Field, EmailStr, AnyUrl

from .address import AddressBase

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
    avatar_url: Optional[AnyUrl] = Field(
        None,
        description="URL to avatar image.",
        json_schema_extra={"example": "https://cdn.neighborhood.com/avatars/alice.png"},
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "username": "alice",
                    "email": "alice@example.com",
                    "phone": "+1-212-555-0199",
                    "birth_date": "2000-09-01",
                }
            ]
        }
    }


class UserCreate(UserBase):
    """Creation payload for a User."""
    password: str = Field(
        ..., min_length=8, max_length=72,
        description="Plaintext password (will be hashed server-side).",
        json_schema_extra={"example": "Str0ngP@ss!"}
    )


class UserUpdate(BaseModel):
    """Partial update for a User; supply only fields to change."""
    username: Optional[str] = Field(None, json_schema_extra={"example": "alice_new"})
    email: Optional[EmailStr] = Field(None, json_schema_extra={"example": "alice@newmail.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "+44 20 7946 0958"})
    birth_date: Optional[date] = Field(None, json_schema_extra={"example": "2000-09-01"})
    avatar_url: Optional[AnyUrl] = Field(
        None,
        description="URL to avatar image.",
        json_schema_extra={"example": "https://cdn.neighborhood.com/avatars/alice.png"}
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"username": "alice_new"},
                {"email": "alice@newmail.com"},
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
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp (UTC).",
        json_schema_extra={"example": "2025-01-15T10:20:30Z"},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
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
                    "created_at": "2025-01-15T10:20:30Z",
                    "updated_at": "2025-01-16T12:00:00Z",
                }
            ]
        }
    }
