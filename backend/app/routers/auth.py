"""
Authentication & user management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_with_org, require_admin
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    UserWithOrgResponse,
    InviteRequest,
    InvitationResponse,
    MemberResponse,
    UpdateMemberRoleRequest,
    AcceptInviteRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and create an organization."""
    try:
        service = AuthService(db)
        return await service.register(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password."""
    try:
        service = AuthService(db)
        return await service.login(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token."""
    try:
        service = AuthService(db)
        return await service.refresh_tokens(req.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.get("/me", response_model=UserWithOrgResponse)
async def get_me(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user info with organization."""
    service = AuthService(db)
    return await service.get_current_user_info(user)


@router.post("/invite", response_model=InvitationResponse)
async def invite_member(
    req: InviteRequest,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Invite a new member to the organization (admin+ only)."""
    try:
        service = AuthService(db)
        return await service.create_invitation(
            user.current_membership.organization_id,
            req,
            user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/accept-invite", response_model=TokenResponse)
async def accept_invite(req: AcceptInviteRequest, db: AsyncSession = Depends(get_db)):
    """Accept an invitation and create account."""
    try:
        service = AuthService(db)
        return await service.accept_invitation(req.token, req.password, req.full_name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/members", response_model=list[MemberResponse])
async def list_members(
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """List all members of the current organization."""
    service = AuthService(db)
    return await service.list_org_members(user.current_membership.organization_id)


@router.patch("/members/{member_id}/role")
async def update_member_role(
    member_id: str,
    req: UpdateMemberRoleRequest,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a member's role (admin+ only)."""
    try:
        service = AuthService(db)
        await service.update_member_role(
            user.current_membership.organization_id,
            member_id,
            req.role,
        )
        return {"status": "updated"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
