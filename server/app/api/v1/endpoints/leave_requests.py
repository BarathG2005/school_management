"""
app/api/v1/endpoints/leave_requests.py
Leave Request management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import List, Optional
from datetime import datetime
from app.models.schemas import (
    LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestResponse, TokenPayload, UserRole, LeaveStatus
)
from app.core.security import require_admin, get_current_user, require_teacher
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _enrich_leave_response(request: dict, db: SupabaseQueries) -> dict:
    """Helper to add student_name."""
    student_name = None
    if request.get("student_id"):
        student = await db.select_by_id("students", "student_id", request["student_id"])
        if student:
            student_name = student.get("name")
    return {"student_name": student_name}


@router.post("/", response_model=LeaveRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_leave_request(
    request_data: LeaveRequestCreate,
    current_user: TokenPayload = Depends(get_current_user) # Students, Parents, Admins
):
    """
    Create a new leave request.
    - Students can only submit for themselves.
    - Parents can only submit for their own children.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    student_id_to_use = None
    
    try:
        # 1. Authorize who is creating the request
        if current_user.role == UserRole.STUDENT:
            student = await db.select_one("students", {"user_id": current_user.sub})
            if not student:
                raise HTTPException(status_code=404, detail="Student profile not found for this user.")
            if request_data.student_id != student["student_id"]:
                 raise HTTPException(status_code=403, detail="Students can only submit leave requests for themselves.")
            student_id_to_use = student["student_id"]

        elif current_user.role == UserRole.PARENT:
            parent = await db.select_one("parents", {"user_id": current_user.sub})
            if not parent:
                raise HTTPException(status_code=404, detail="Parent profile not found for this user.")
            
            links = await db.select_all("parent_student", {"parent_id": parent["parent_id"]})
            child_ids = [link["student_id"] for link in links]
            
            if request_data.student_id not in child_ids:
                raise HTTPException(status_code=403, detail="Parents can only submit requests for their own children.")
            student_id_to_use = request_data.student_id
        
        elif current_user.role == UserRole.ADMIN:
             student_id_to_use = str(request_data.student_id)
             if not await db.select_by_id("students", "student_id", student_id_to_use):
                 raise HTTPException(status_code=404, detail="Student not found.")
        
        else:
             raise HTTPException(status_code=403, detail="Only Students, Parents, or Admins can create leave requests.")

        # 2. Prepare data for insertion
        request_dict = request_data.model_dump()
        
        # 3. Fix serialization for non-string types
        request_dict["student_id"] = str(student_id_to_use)
        request_dict["start_date"] = request_dict["start_date"].isoformat()
        request_dict["end_date"] = request_dict["end_date"].isoformat()
        request_dict["status"] = request_dict["status"].value
        
        # 4. Insert new request
        new_request = await db.insert_one("leave_requests", request_dict)
        
        logger.info(f"Leave request created: {new_request['request_id']}")
        
        # 5. Enrich and return response
        enriched_data = await _enrich_leave_response(new_request, db)
        return LeaveRequestResponse(**new_request, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create leave request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create request: {str(e)}"
        )

@router.get("/", response_model=List[LeaveRequestResponse])
async def get_leave_requests(
    status: Optional[LeaveStatus] = None,
    student_id: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a list of all leave requests.
    - Admins/Teachers see all.
    - Students see only their own.
    - Parents see only their children's.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    filters = {}
    student_ids_allowed = None
    
    try:
        # --- Role-based security ---
        if current_user.role == UserRole.STUDENT:
            student = await db.select_one("students", {"user_id": current_user.sub})
            if not student: return []
            filters["student_id"] = student["student_id"]
            
        elif current_user.role == UserRole.PARENT:
            parent = await db.select_one("parents", {"user_id": current_user.sub})
            if not parent: return []
            links = await db.select_all("parent_student", {"parent_id": parent["parent_id"]})
            student_ids_allowed = [link["student_id"] for link in links]
            if not student_ids_allowed: return []
            
            if student_id and student_id in student_ids_allowed:
                filters["student_id"] = student_id
            elif student_id: # Parent trying to access a student not their own
                 raise HTTPException(status_code=403, detail="Access denied")

        elif student_id: # Admin/Teacher filtering
            filters["student_id"] = student_id
        # --- End security ---

        if status:
            filters["status"] = status.value
            
        requests_list = await db.select_all("leave_requests", filters, "created_at", ascending=False)
        
        response_list = []
        for req in requests_list:
            # Post-fetch filter for Parent role
            if current_user.role == UserRole.PARENT and not student_id:
                if req.get("student_id") not in student_ids_allowed:
                    continue

            enriched_data = await _enrich_leave_response(req, db)
            response_list.append(LeaveRequestResponse(**req, **enriched_data))
            
        return response_list
        
    except Exception as e:
        logger.error(f"Get leave requests error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve requests: {str(e)}"
        )

@router.get("/{request_id}", response_model=LeaveRequestResponse)
async def get_leave_request(
    request_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a single leave request by its ID.
    - Students/Parents can only get requests they have access to.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        request = await db.select_by_id("leave_requests", "request_id", request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Leave request not found")

        # --- Authorization Check ---
        if current_user.role == UserRole.STUDENT:
            student = await db.select_one("students", {"user_id": current_user.sub})
            if not student or request.get("student_id") != student["student_id"]:
                raise HTTPException(status_code=403, detail="Access denied")
                
        elif current_user.role == UserRole.PARENT:
            parent = await db.select_one("parents", {"user_id": current_user.sub})
            if not parent:
                raise HTTPException(status_code=403, detail="Access denied")
            links = await db.select_all("parent_student", {"parent_id": parent["parent_id"]})
            student_ids_allowed = [link["student_id"] for link in links]
            if request.get("student_id") not in student_ids_allowed:
                raise HTTPException(status_code=403, detail="Access denied")
        # --- End Auth Check ---

        enriched_data = await _enrich_leave_response(request, db)
        return LeaveRequestResponse(**request, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get leave request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve request: {str(e)}"
        )

@router.put("/{request_id}", response_model=LeaveRequestResponse)
async def update_leave_request_status(
    request_id: str,
    update_data: LeaveRequestUpdate,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Approve or reject a leave request.
    (Admin or Teacher only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        existing_request = await db.select_by_id("leave_requests", "request_id", request_id)
        if not existing_request:
            raise HTTPException(status_code=404, detail="Leave request not found")
        
        # Prepare data for update
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict["status"] = update_dict["status"].value # Convert enum
        update_dict["updated_at"] = datetime.now().isoformat()
            
        updated_request = await db.update_by_id("leave_requests", "request_id", request_id, update_dict)
        
        logger.info(f"Leave request updated: {request_id}")
        
        enriched_data = await _enrich_leave_response(updated_request, db)
        return LeaveRequestResponse(**updated_request, **enriched_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update leave request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update request: {str(e)}"
        )

@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_leave_request(
    request_id: str,
    current_user: TokenPayload = Depends(require_admin) # Only Admins can delete
):
    """
    Delete a leave request (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        if not await db.select_by_id("leave_requests", "request_id", request_id):
            raise HTTPException(status_code=404, detail="Leave request not found")
            
        await db.delete_by_id("leave_requests", "request_id", request_id)
        
        logger.info(f"Leave request deleted: {request_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete leave request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete request: {str(e)}"
        )