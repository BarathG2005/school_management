# [File: server/app/api/v1/endpoints/admin.py]
"""
app/api/v1/endpoints/admin.py
Endpoints for Master role to manage Admin users.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.models.schemas import UserCreate, UserResponse, TokenPayload, UserRole
from app.core.security import require_master, hash_password
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/create-admin", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin(
    user_data: UserCreate,
    current_user: TokenPayload = Depends(require_master)
):
    """
    Create a new Admin user (Master only).
    The new Admin is created as 'is_active = False' by default.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    if user_data.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint can only create users with the 'admin' role."
        )

    try:
        existing = await db.select_one("users", {"email": user_data.email})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        hashed_password = hash_password(user_data.password)
        
        user_dict = {
            "email": user_data.email,
            "password_hash": hashed_password,
            "role": UserRole.ADMIN.value,
            "is_active": False  # Admin created as inactive by default
        }
        
        new_user = await db.insert_one("users", user_dict)
        logger.info(f"Master {current_user.sub} created new Admin {new_user['user_id']}")
        
        return UserResponse(**new_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create admin error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create admin: {str(e)}"
        )

@router.get("/list-admins", response_model=List[UserResponse])
async def list_admins(current_user: TokenPayload = Depends(require_master)):
    """
    List all Admin users (Master only).
    """
    db = SupabaseQueries(get_supabase_client())
    try:
        admins = await db.select_all("users", {"role": UserRole.ADMIN.value})
        return [UserResponse(**admin) for admin in admins]
    except Exception as e:
        logger.error(f"List admins error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve admins"
        )

@router.put("/{admin_user_id}/approve", response_model=UserResponse)
async def approve_admin(
    admin_user_id: str,
    current_user: TokenPayload = Depends(require_master)
):
    """
    Approve (activate) a new Admin (Master only).
    """
    db = SupabaseQueries(get_supabase_client())
    try:
        admin = await db.select_by_id("users", "user_id", admin_user_id)
        if not admin or admin["role"] != UserRole.ADMIN.value:
            raise HTTPException(status_code=404, detail="Admin user not found")
            
        updated_admin = await db.update_by_id(
            "users", "user_id", admin_user_id, {"is_active": True}
        )
        logger.info(f"Admin {admin_user_id} approved by Master {current_user.sub}")
        return UserResponse(**updated_admin)
    except Exception as e:
        logger.error(f"Approve admin error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve admin"
        )

@router.put("/{admin_user_id}/deactivate", response_model=UserResponse)
async def deactivate_admin(
    admin_user_id: str,
    current_user: TokenPayload = Depends(require_master)
):
    """
    Deactivate an Admin user (Master only).
    """
    db = SupabaseQueries(get_supabase_client())
    try:
        admin = await db.select_by_id("users", "user_id", admin_user_id)
        if not admin or admin["role"] != UserRole.ADMIN.value:
            raise HTTPException(status_code=404, detail="Admin user not found")
            
        updated_admin = await db.update_by_id(
            "users", "user_id", admin_user_id, {"is_active": False}
        )
        logger.info(f"Admin {admin_user_id} deactivated by Master {current_user.sub}")
        return UserResponse(**updated_admin)
    except Exception as e:
        logger.error(f"Deactivate admin error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate admin"
        )

@router.delete("/{admin_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(
    admin_user_id: str,
    current_user: TokenPayload = Depends(require_master)
):
    """
    Delete an Admin user (Master only).
    """
    db = SupabaseQueries(get_supabase_client())
    try:
        admin = await db.select_by_id("users", "user_id", admin_user_id)
        if not admin or admin["role"] != UserRole.ADMIN.value:
            raise HTTPException(status_code=404, detail="Admin user not found")
        
        # Note: You may want to handle related data (e.g., reassign classes)
        # before deleting the associated user.
        await db.delete_by_id("users", "user_id", admin_user_id)
        logger.info(f"Admin {admin_user_id} deleted by Master {current_user.sub}")
        
    except Exception as e:
        logger.error(f"Delete admin error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete admin"
        )