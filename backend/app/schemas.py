"""Pydantic request/response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------- Users ----------

class UserResponse(BaseModel):
    """Public view of a row in the `users` table."""

    id: int
    email: EmailStr
    name: str
    created_at: datetime


# ---------- Auth ----------

class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


# ---------- Posts ----------

Tone = Literal[
    "professional",
    "conversational",
    "casual",
    "inspirational",
    "technical",
    "storytelling",
    "thought-leadership",
]
Length = Literal["short", "medium", "long"]
# New posts start as "pending"; the agent pipeline will move them through the rest.
PostStatus = Literal["pending", "generating", "completed", "failed"]


class _PostFields(BaseModel):
    @field_validator("topic", "audience", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class PostCreate(_PostFields):
    topic: str = Field(min_length=3, max_length=500)
    audience: str = Field(min_length=2, max_length=100)
    tone: Tone
    length: Length = "medium"


class PostUpdate(_PostFields):
    """Partial update: only the fields that are sent are changed."""

    topic: str | None = Field(default=None, min_length=3, max_length=500)
    audience: str | None = Field(default=None, min_length=2, max_length=100)
    tone: Tone | None = None
    length: Length | None = None


class PostResponse(BaseModel):
    """A row in the `posts` table."""

    id: int
    user_id: int
    topic: str
    audience: str
    tone: Tone
    length: Length
    status: PostStatus
    created_at: datetime


class PostListResponse(BaseModel):
    items: list[PostResponse]
    total: int
