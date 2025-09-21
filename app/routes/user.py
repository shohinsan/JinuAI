"""User Routes
===========
Handles user profile management, search, and account recovery.

Endpoints:
- GET /me: Get current authenticated user.
- GET /{account}: Get user by account name.
- GET /search: Search users by name, account, or email.
- POST /delete: Soft delete current user.
- POST /recover: Recover a previously deleted user account.
- POST /update: Update current user profile information.
"""

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.utils.delegate import CurrentUser, UserServiceDep
from app.utils.models import Message, UserPublic, UsersPublic, UserUpdate

router = APIRouter()


@router.get("/whoami")
def get_user_me(current_user: CurrentUser, response: Response) -> UserPublic:
    """Get current user info"""
    response.status_code = status.HTTP_200_OK
    return current_user


@router.get("/search")
def search_users(
    user_service: UserServiceDep,
    _: CurrentUser,
    q: str = Query(..., min_length=2),
    skip: int = 0,
    limit: int = 20,
    response: Response = None,
) -> UsersPublic:
    """Search users"""
    response.status_code = status.HTTP_200_OK
    return user_service.search_users(q, skip, limit)


@router.get("/{account}/lookup")
def get_user_by_account(
    account: str, user_service: UserServiceDep, _: CurrentUser, response: Response
) -> UserPublic:
    """Get user by account"""
    user = user_service.get_user_by_account(account)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    response.status_code = status.HTTP_200_OK
    return user


@router.post("/delete")
def soft_delete_user(
    user_service: UserServiceDep, current_user: CurrentUser, response: Response
) -> Message:
    """Soft delete current user"""
    try:
        user_service.soft_delete_user(current_user.id)
        response.status_code = status.HTTP_202_ACCEPTED
        return Message(message="SCHEDULED_FOR_DELETION")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/recover")
def recover_user_account(
    user_service: UserServiceDep, current_user: CurrentUser, response: Response
) -> Message:
    """Recover user account"""
    success = user_service.recover_user(current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot recover account."
        )

    response.status_code = status.HTTP_200_OK
    return Message(message="Account successfully recovered!")


@router.post("/update")
def update_user_profile(
    user_service: UserServiceDep,
    user_in: UserUpdate,
    current_user: CurrentUser,
    response: Response,
) -> UserPublic:
    """Update current user profile"""
    try:
        updated_user = user_service.update_user(current_user.id, user_in)
        response.status_code = status.HTTP_200_OK
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
