"""
Pydantic v2 schemas for authentication, users, organizations, and invitations.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Auth ────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    org_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── User ────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserWithOrgResponse(UserResponse):
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    role: Optional[str] = None


# ── Organization ────────────────────────────────────────────────────

class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str
    role: str
    joined_at: datetime


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(pattern="^(admin|analyst|viewer)$")


# ── Invitation ──────────────────────────────────────────────────────

class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="viewer", pattern="^(admin|analyst|viewer)$")


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: str
    accepted: bool
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
