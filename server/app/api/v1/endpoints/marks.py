"""
app/api/v1/endpoints/marks.py
Marks management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import List, Optional, Dict, Any
from app.models.schemas import (
    MarksCreate, MarksUpdate, MarksResponse, TokenPayload, UserRole
)
from app.core.security import require_admin, get_current_user, require_teacher
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _enrich_mark_response(mark: dict, db: SupabaseQueries) -> dict:
    """Helper to add student_name, exam_name, max_marks, and percentage."""
    
    student_name, exam_name, max_marks, percentage = None, None, None, None
    
    # 1. Get Student
    if mark.get("student_id"):
        student = await db.select_by_id("students", "student_id", mark["student_id"])
        if student:
            student_name = student.get("name")
            
    # 2. Get Exam
    if mark.get("exam_id"):
        exam = await db.select_by_id("exams", "exam_id", mark["exam_id"])
        if exam:
            exam_name = exam.get("exam_name")
            max_marks = exam.get("max_marks")
    
    # 3. Calculate Percentage
    if max_marks is not None and max_marks > 0 and mark.get("marks_scored") is not None:
        percentage = round((mark["marks_scored"] / max_marks) * 100, 2)
            
    return {
        "student_name": student_name,
        "exam_name": exam_name,
        "max_marks": max_marks,
        "percentage": percentage
    }


@router.post("/", response_model=MarksResponse, status_code=status.HTTP_201_CREATED)
async def create_mark(
    mark_data: MarksCreate,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins can create
):
    """
    Create a new mark entry for a student.
    (Admin or Teacher only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Verify foreign keys and get exam details
        exam = await db.select_by_id("exams", "exam_id", str(mark_data.exam_id))
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
            
        if not await db.select_by_id("students", "student_id", str(mark_data.student_id)):
            raise HTTPException(status_code=404, detail="Student not found")

        # 2. Check for duplicate entry
        existing = await db.select_one("marks", {
            "exam_id": str(mark_data.exam_id),
            "student_id": str(mark_data.student_id)
        })
        if existing:
            raise HTTPException(status_code=400, detail="Marks for this student and exam already exist.")

        # 3. Validate marks_scored against max_marks
        max_marks = exam.get("max_marks", 0)
        if mark_data.marks_scored > max_marks:
            raise HTTPException(
                status_code=400, 
                detail=f"Marks scored ({mark_data.marks_scored}) cannot be greater than max marks ({max_marks})"
            )

        # 4. Prepare data for insertion
        mark_dict = mark_data.model_dump()
        mark_dict["exam_id"] = str(mark_dict["exam_id"])
        mark_dict["student_id"] = str(mark_dict["student_id"])
        
        # 5. Insert new mark
        new_mark = await db.insert_one("marks", mark_dict)
        
        logger.info(f"Mark created: {new_mark['mark_id']}")
        
        # 6. Enrich and return response
        enriched_data = await _enrich_mark_response(new_mark, db)
        return MarksResponse(**new_mark, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create mark error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create mark: {str(e)}"
        )

@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def create_bulk_marks(
    marks_list: List[MarksCreate],
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Create multiple mark entries at once.
    (Admin or Teacher only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    created_count = 0
    errors = []
    
    if not marks_list:
        raise HTTPException(status_code=400, detail="No marks data provided.")

    # Fetch exam details once if all marks are for the same exam
    first_exam_id = str(marks_list[0].exam_id)
    exam = await db.select_by_id("exams", "exam_id", first_exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with ID {first_exam_id} not found.")
    max_marks = exam.get("max_marks", 0)
    
    records_to_insert = []
    
    for i, mark_data in enumerate(marks_list):
        # Basic validation
        if str(mark_data.exam_id) != first_exam_id:
            errors.append({"index": i, "error": "All marks in a bulk upload must be for the same exam."})
            continue
            
        if mark_data.marks_scored > max_marks:
            errors.append({"index": i, "student_id": str(mark_data.student_id), "error": f"Marks ({mark_data.marks_scored}) exceed max marks ({max_marks})."})
            continue
            
        mark_dict = mark_data.model_dump()
        mark_dict["exam_id"] = str(mark_dict["exam_id"])
        mark_dict["student_id"] = str(mark_dict["student_id"])
        records_to_insert.append(mark_dict)

    if records_to_insert:
        try:
            new_marks = await db.insert_many("marks", records_to_insert)
            created_count = len(new_marks)
            logger.info(f"Bulk marks created: {created_count} records.")
        except Exception as e:
            logger.error(f"Bulk create marks error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create marks in bulk: {str(e)}"
            )
            
    return {
        "message": "Bulk marks processed.",
        "created_count": created_count,
        "errors": errors
    }


@router.get("/", response_model=List[MarksResponse])
async def get_marks(
    student_id: Optional[str] = None,
    exam_id: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a list of all marks, with optional filters.
    - Students can only see their own marks.
    - Admins/Teachers can filter by student or exam.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    filters = {}
    
    # Role-based filtering
    if current_user.role == UserRole.STUDENT:
        student_profile = await db.select_one("students", {"user_id": current_user.sub})
        if not student_profile:
            return [] # This user has no student profile
        filters["student_id"] = student_profile["student_id"]
    elif current_user.role == UserRole.PARENT:
        # Logic to get children's student_ids
        parent_profile = await db.select_one("parents", {"user_id": current_user.sub})
        if not parent_profile:
            return []
        
        child_links = await db.select_all("parent_student", {"parent_id": parent_profile["parent_id"]})
        child_ids = [link["student_id"] for link in child_links]
        if not child_ids:
            return []
        
        # This endpoint doesn't support "IN" filter, so we filter by student if one is provided,
        # otherwise we fetch all and filter in Python (less efficient, but works for now)
        if student_id and student_id in child_ids:
            filters["student_id"] = student_id
        elif student_id:
             raise HTTPException(status_code=403, detail="You do not have permission to view this student's marks.")
        else:
            # Parent is asking for all their children's marks
             pass # We'll filter later
    
    # Admin/Teacher filters
    elif student_id:
        filters["student_id"] = student_id
    
    if exam_id:
        filters["exam_id"] = exam_id
        
    try:
        marks_list = await db.select_all("marks", filters=filters, order_by="created_at", ascending=False)
        
        response_list = []
        for mark in marks_list:
            # Post-fetch filter for Parent role if student_id wasn't specified
            if current_user.role == UserRole.PARENT and not student_id:
                if mark.get("student_id") not in child_ids:
                    continue
                    
            enriched_data = await _enrich_mark_response(mark, db)
            response_list.append(MarksResponse(**mark, **enriched_data))
            
        return response_list
        
    except Exception as e:
        logger.error(f"Get marks error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve marks: {str(e)}"
        )

@router.get("/{mark_id}", response_model=MarksResponse)
async def get_mark(
    mark_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a single mark entry by its ID.
    - Students/Parents can only get marks they have access to.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        mark = await db.select_by_id("marks", "mark_id", mark_id)
        if not mark:
            raise HTTPException(status_code=404, detail="Mark not found")

        # --- Authorization Check ---
        if current_user.role == UserRole.STUDENT:
            student_profile = await db.select_one("students", {"user_id": current_user.sub})
            if not student_profile or mark.get("student_id") != student_profile["student_id"]:
                raise HTTPException(status_code=403, detail="Access denied")

        if current_user.role == UserRole.PARENT:
            parent_profile = await db.select_one("parents", {"user_id": current_user.sub})
            child_links = await db.select_all("parent_student", {"parent_id": parent_profile["parent_id"]})
            child_ids = [link["student_id"] for link in child_links]
            if mark.get("student_id") not in child_ids:
                 raise HTTPException(status_code=403, detail="Access denied")
        # --- End Auth Check ---

        enriched_data = await _enrich_mark_response(mark, db)
        return MarksResponse(**mark, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get mark error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve mark: {str(e)}"
        )

@router.put("/{mark_id}", response_model=MarksResponse)
async def update_mark(
    mark_id: str,
    mark_data: MarksUpdate,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Update a mark's score or remarks.
    (Admin or Teacher only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        existing_mark = await db.select_by_id("marks", "mark_id", mark_id)
        if not existing_mark:
            raise HTTPException(status_code=404, detail="Mark not found")

        update_data = mark_data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # If marks_scored is being updated, we must re-validate it
        if "marks_scored" in update_data:
            exam = await db.select_by_id("exams", "exam_id", existing_mark["exam_id"])
            if not exam:
                raise HTTPException(status_code=404, detail="Associated exam not found. Cannot validate marks.")
            
            max_marks = exam.get("max_marks", 0)
            if update_data["marks_scored"] > max_marks:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Marks scored ({update_data['marks_scored']}) cannot be greater than max marks ({max_marks})"
                )

        # Update the mark
        updated_mark = await db.update_by_id("marks", "mark_id", mark_id, update_data)
        
        logger.info(f"Mark updated: {updated_mark['mark_id']}")

        # Enrich and return response
        enriched_data = await _enrich_mark_response(updated_mark, db)
        return MarksResponse(**updated_mark, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update mark error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update mark: {str(e)}"
        )

@router.delete("/{mark_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mark(
    mark_id: str,
    current_user: TokenPayload = Depends(require_admin) # Only Admins can delete
):
    """
    Delete a mark entry (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        if not await db.select_by_id("marks", "mark_id", mark_id):
            raise HTTPException(status_code=404, detail="Mark not found")
            
        await db.delete_by_id("marks", "mark_id", mark_id)
        
        logger.info(f"Mark deleted: {mark_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete mark error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete mark: {str(e)}"
        )