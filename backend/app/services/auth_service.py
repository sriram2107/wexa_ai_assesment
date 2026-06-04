"""
Authentication service: registration, login, token management, invitations.
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.user import User, Organization, Membership, Invitation
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserWithOrgResponse,
    InviteRequest,
    InvitationResponse,
    MemberResponse,
)

import structlog

logger = structlog.get_logger()


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, req: RegisterRequest) -> TokenResponse:
        """Register a new user + create their organization."""
        # Check existing user
        result = await self.db.execute(select(User).where(User.email == req.email))
        if result.scalar_one_or_none():
            raise ValueError("Email already registered")

        # Create user
        user = User(
            email=req.email,
            full_name=req.full_name,
            hashed_password=hash_password(req.password),
            is_active=True,
            is_verified=True,
        )
        self.db.add(user)
        await self.db.flush()

        # Create organization
        slug = req.org_name.lower().replace(" ", "-")
        # Ensure unique slug
        existing = await self.db.execute(select(Organization).where(Organization.slug == slug))
        if existing.scalar_one_or_none():
            slug = f"{slug}-{secrets.token_hex(3)}"

        org = Organization(name=req.org_name, slug=slug)
        self.db.add(org)
        await self.db.flush()

        # Create membership with owner role
        membership = Membership(
            user_id=user.id,
            organization_id=org.id,
            role="owner",
        )
        self.db.add(membership)
        await self.db.flush()

        logger.info("user_registered", user_id=user.id, org_id=org.id)

        return self._create_tokens(user.id, org.id)

    async def login(self, req: LoginRequest) -> TokenResponse:
        """Authenticate user with email + password."""
        result = await self.db.execute(
            select(User).where(User.email == req.email, User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(req.password, user.hashed_password):
            raise ValueError("Invalid email or password")

        # Get org membership
        result = await self.db.execute(
            select(Membership).where(Membership.user_id == user.id)
        )
        membership = result.scalar_one_or_none()
        org_id = membership.organization_id if membership else None

        logger.info("user_logged_in", user_id=user.id)
        return self._create_tokens(user.id, org_id)

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """Issue new access + refresh tokens from a valid refresh token."""
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        user_id = payload.get("sub")
        org_id = payload.get("org_id")

        # Verify user still exists and is active
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        if not result.scalar_one_or_none():
            raise ValueError("User not found")

        return self._create_tokens(user_id, org_id)

    async def get_current_user_info(self, user: User) -> UserWithOrgResponse:
        """Get current user with organization details."""
        result = await self.db.execute(
            select(Membership, Organization)
            .join(Organization, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user.id)
        )
        row = result.first()

        return UserWithOrgResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at,
            organization_id=row[0].organization_id if row else None,
            organization_name=row[1].name if row else None,
            role=row[0].role if row else None,
        )

    async def create_invitation(
        self, org_id: str, req: InviteRequest, invited_by: str
    ) -> InvitationResponse:
        """Create an invitation for a new team member."""
        # Check if user already in org
        result = await self.db.execute(
            select(User).where(User.email == req.email)
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            result = await self.db.execute(
                select(Membership).where(
                    Membership.user_id == existing_user.id,
                    Membership.organization_id == org_id,
                )
            )
            if result.scalar_one_or_none():
                raise ValueError("User is already a member of this organization")

        token = secrets.token_urlsafe(32)
        invitation = Invitation(
            organization_id=org_id,
            email=req.email,
            role=req.role,
            token=token,
            invited_by=invited_by,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.db.add(invitation)
        await self.db.flush()

        logger.info("invitation_created", org_id=org_id, email=req.email)
        return InvitationResponse.model_validate(invitation)

    async def accept_invitation(self, token: str, password: str, full_name: str) -> TokenResponse:
        """Accept an invitation and create user + membership."""
        result = await self.db.execute(
            select(Invitation).where(
                Invitation.token == token,
                Invitation.accepted == False,
            )
        )
        invitation = result.scalar_one_or_none()
        if not invitation:
            raise ValueError("Invalid or expired invitation")

        if invitation.expires_at < datetime.now(timezone.utc):
            raise ValueError("Invitation has expired")

        # Check if user already exists
        result = await self.db.execute(
            select(User).where(User.email == invitation.email)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                email=invitation.email,
                full_name=full_name,
                hashed_password=hash_password(password),
                is_active=True,
                is_verified=True,
            )
            self.db.add(user)
            await self.db.flush()

        # Create membership
        membership = Membership(
            user_id=user.id,
            organization_id=invitation.organization_id,
            role=invitation.role,
        )
        self.db.add(membership)

        # Mark invitation as accepted
        invitation.accepted = True
        await self.db.flush()

        logger.info("invitation_accepted", user_id=user.id, org_id=invitation.organization_id)
        return self._create_tokens(user.id, invitation.organization_id)

    async def list_org_members(self, org_id: str) -> list[MemberResponse]:
        """List all members of an organization."""
        result = await self.db.execute(
            select(Membership, User)
            .join(User, Membership.user_id == User.id)
            .where(Membership.organization_id == org_id)
        )
        rows = result.all()
        return [
            MemberResponse(
                id=m.id,
                user_id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=m.role,
                joined_at=m.joined_at,
            )
            for m, u in rows
        ]

    async def update_member_role(self, org_id: str, member_id: str, new_role: str) -> None:
        """Update a member's role in the organization."""
        result = await self.db.execute(
            select(Membership).where(
                Membership.id == member_id,
                Membership.organization_id == org_id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise ValueError("Member not found")
        if membership.role == "owner":
            raise ValueError("Cannot change owner role")
        membership.role = new_role
        await self.db.flush()

    def _create_tokens(self, user_id: str, org_id: str = None) -> TokenResponse:
        data = {"sub": user_id}
        if org_id:
            data["org_id"] = org_id
        return TokenResponse(
            access_token=create_access_token(data),
            refresh_token=create_refresh_token(data),
        )
