from fastapi import APIRouter, HTTPException, status, Depends, Form
from pydantic import EmailStr
from app.models.schemas import (UserCreate, UserLogin, Token, UserResponse, UserRole, TokenPayload)
from app.core.security import (hash_password, verify_password, create_access_token, create_refresh_token,get_current_user, verify_token)
from app.db.supabase import get_supabase_client, SupabaseQueries
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# @router.post("/register", status_code=status.HTTP_201_CREATED)
# async def register_user(user_data: dict):
#     """
#     Register a new user (Admin only in production)
#     Creates user in auth system and users table
#     """
#     supabase = get_supabase_client()
#     db = SupabaseQueries(supabase)
    
#     try:
#         # Basic validation manually
#         if "email" not in user_data or "password" not in user_data or "role" not in user_data:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Missing required fields: email, password, role"
#             )
        
#         # Check if user already exists
#         existing = supabase.table("users").select("*").eq("email", user_data["email"]).execute()
#         if existing.data:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="User with this email already exists"
#             )
        
#         # Hash password
#         hashed_password = hash_password(user_data["password"])
        
#         # Create user record
#         user_dict = {
#             "email": user_data["email"],
#             "password_hash": hashed_password,
#             "role": user_data["role"],  # assuming role is string
#             "is_active": user_data.get("is_active", True)
#         }
        
#         new_user = await db.insert_one("users", user_dict)
        
#         logger.info(f"User registered: {user_data['email']} with role {user_data['role']}")
        
#         # Return raw dict (no schema)
#         return {
#             "user_id": new_user["user_id"],
#             "email": new_user["email"],
#             "role": new_user["role"],
#             "is_active": new_user["is_active"],
#             "created_at": new_user["created_at"]
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Registration error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Registration failed"
#         )
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate):
    """
    Register a new user (Admin only in production)
    Creates user in auth system and users table
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Check if user already exists
        existing = supabase.table("users").select("*").eq("email", user_data.email).execute()
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Hash password
        hashed_password = hash_password(user_data.password)
        
        # Create user record
        user_dict = {
            "email": user_data.email,
            "password_hash": hashed_password,
            "role": user_data.role.value,
            "is_active": user_data.is_active
        }
        
        new_user = await db.insert_one("users", user_dict)
        
        logger.info(f"User registered: {user_data.email} with role {user_data.role}")
        
        return UserResponse(
            user_id=new_user["user_id"],
            email=new_user["email"],
            role=UserRole(new_user["role"]),
            is_active=new_user["is_active"],
            created_at=new_user["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@router.post("/login")
async def login(credentials: UserLogin):
    """
    Login endpoint - returns JWT tokens
    """
    supabase = get_supabase_client()
    
    try:
        # Get user by email
        response = supabase.table("users").select("*").eq("email", credentials.email).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        user = response.data[0]
        
        # Check if user is active
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive"
            )
        
        # Verify password
        if not verify_password(credentials.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Create tokens
        token_data = {
            "sub": user["user_id"],
            "role": user["role"]
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        logger.info(f"User logged in: {credentials.email}")
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str):
    """
    Refresh access token using refresh token
    """
    try:
        # Verify refresh token
        payload = verify_token(refresh_token)
        
        # Create new access token
        token_data = {
            "sub": payload.sub,
            "role": payload.role.value
        }
        
        new_access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token(token_data)
        
        return Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenPayload = Depends(get_current_user)):
    """
    Get current user information
    """
    supabase = get_supabase_client()
    
    try:
        response = supabase.table("users").select("*").eq("user_id", current_user.sub).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user = response.data[0]
        
        return UserResponse(
            user_id=user["user_id"],
            email=user["email"],
            role=UserRole(user["role"]),
            is_active=user["is_active"],
            created_at=user["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user info error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )

@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Change user password
    """
    supabase = get_supabase_client()
    
    try:
        # Get user
        response = supabase.table("users").select("*").eq("user_id", current_user.sub).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user = response.data[0]
        
        # Verify old password
        if not verify_password(old_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid current password"
            )
        
        # Hash new password
        new_hashed_password = hash_password(new_password)
        
        # Update password
        supabase.table("users").update({
            "password_hash": new_hashed_password
        }).eq("user_id", current_user.sub).execute()
        
        logger.info(f"Password changed for user: {current_user.sub}")
        
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )
    
    # [File: server/app/api/v1/endpoints/auth.py]
# ... (imports)
from app.models.schemas import (UserCreate, UserLogin, Token, UserResponse, UserRole, TokenPayload)
# ...

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate):
    """
    Register a new user (e.g., Student or Parent).
    Admin and Master accounts cannot be created via this public endpoint.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Always force public registrations to be regular students
        # (ignore any role provided by the client to avoid accidental admin creation)
        if user_data.role in [UserRole.ADMIN]:
            # log and ignore if client attempted to set admin role
            logger.warning(f"Public registration attempted with elevated role: {user_data.role}. Forcing to STUDENT.")


        # Check if user already exists
        existing = supabase.table("users").select("*").eq("email", user_data.email).execute()
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Hash password
        hashed_password = hash_password(user_data.password)
        
        # Create user record
        # Force role to STUDENT for public registrations
        user_dict = {
            "email": user_data.email,
            "password_hash": hashed_password,
            "role": UserRole.STUDENT.value,
            "is_active": user_data.is_active
        }
        
        new_user = await db.insert_one("users", user_dict)
        
        logger.info(f"User registered: {user_data.email} with role {user_data.role}")
        
        return UserResponse(
            user_id=new_user["user_id"],
            email=new_user["email"],
            role=UserRole(new_user["role"]),
            is_active=new_user["is_active"],
            created_at=new_user["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

# ... (rest of the file is unchanged)