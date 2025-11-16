from fastapi import Depends, HTTPException, status
from app.core.security import get_current_user # You'll need to implement this
from app.models.schemas import TokenPayload, UserRole

def get_admin_user(current_user: TokenPayload = Depends(get_current_user)):
    """
    Dependency to check if the current user is an admin.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have administrative privileges"
        )
    return current_user