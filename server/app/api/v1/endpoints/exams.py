"""
app/api/v1/endpoints/exams.py
Exam management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import List, Optional
from datetime import date
from app.models.schemas import (
    ExamCreate, ExamUpdate, ExamResponse, TokenPayload, UserRole
)
from app.core.security import require_admin, get_current_user
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _enrich_exam_response(exam: dict, db: SupabaseQueries) -> dict:
    """Helper to add class_name and subject_name to an exam response."""
    class_name = None
    subject_name = None

    if exam.get("class_id"):
        cls = await db.select_by_id("classes", "class_id", exam["class_id"])
        if cls:
            class_name = f"{cls.get('class_name', '')} - {cls.get('section', '')}"
    
    if exam.get("subject_id"):
        subject = await db.select_by_id("subjects", "subject_id", exam["subject_id"])
        if subject:
            subject_name = subject.get("subject_name")
            
    return {
        "class_name": class_name,
        "subject_name": subject_name
    }


@router.post("/", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(
    exam_data: ExamCreate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Create a new exam (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Verify foreign keys
        if not await db.select_by_id("classes", "class_id", str(exam_data.class_id)):
            raise HTTPException(status_code=404, detail="Class not found")
        if not await db.select_by_id("subjects", "subject_id", str(exam_data.subject_id)):
            raise HTTPException(status_code=404, detail="Subject not found")

        # 2. Convert data for insertion
        exam_dict = exam_data.model_dump()
        
        # 3. Fix serialization for non-string types
        exam_dict["date"] = exam_dict["date"].isoformat()
        exam_dict["class_id"] = str(exam_dict["class_id"])
        exam_dict["subject_id"] = str(exam_dict["subject_id"])
        
        # 4. Insert new exam
        new_exam = await db.insert_one("exams", exam_dict)
        
        logger.info(f"Exam created: {new_exam['exam_id']}")
        
        # 5. Enrich and return response
        enriched_data = await _enrich_exam_response(new_exam, db)
        return ExamResponse(**new_exam, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create exam error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create exam: {str(e)}"
        )

@router.get("/", response_model=List[ExamResponse])
async def get_exams(
    class_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a list of all exams, with optional filters
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        filters = {}
        if class_id:
            filters["class_id"] = class_id
        if subject_id:
            filters["subject_id"] = subject_id
        
        exams = await db.select_all("exams", filters=filters, order_by="date", ascending=False)
        
        # Enrich all exams in the list
        response_list = []
        for exam in exams:
            enriched_data = await _enrich_exam_response(exam, db)
            response_list.append(ExamResponse(**exam, **enriched_data))
            
        return response_list
        
    except Exception as e:
        logger.error(f"Get exams error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve exams: {str(e)}"
        )

@router.get("/{exam_id}", response_model=ExamResponse)
async def get_exam(
    exam_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a single exam by its ID
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        exam = await db.select_by_id("exams", "exam_id", exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        
        enriched_data = await _enrich_exam_response(exam, db)
        return ExamResponse(**exam, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get exam error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve exam: {str(e)}"
        )

@router.put("/{exam_id}", response_model=ExamResponse)
async def update_exam(
    exam_id: str,
    exam_data: ExamUpdate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Update an exam's details (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        if not await db.select_by_id("exams", "exam_id", exam_id):
            raise HTTPException(status_code=404, detail="Exam not found")

        update_data = exam_data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # 1. Verify foreign keys if they are being changed
        if "class_id" in update_data:
            if not await db.select_by_id("classes", "class_id", str(update_data["class_id"])):
                raise HTTPException(status_code=404, detail="Class not found")
            update_data["class_id"] = str(update_data["class_id"])
            
        if "subject_id" in update_data:
            if not await db.select_by_id("subjects", "subject_id", str(update_data["subject_id"])):
                raise HTTPException(status_code=404, detail="Subject not found")
            update_data["subject_id"] = str(update_data["subject_id"])

        # 2. Fix serialization
        if "date" in update_data:
            update_data["date"] = update_data["date"].isoformat()

        # 3. Update exam
        updated_exam = await db.update_by_id("exams", "exam_id", exam_id, update_data)
        
        logger.info(f"Exam updated: {updated_exam['exam_id']}")

        # 4. Enrich and return response
        enriched_data = await _enrich_exam_response(updated_exam, db)
        return ExamResponse(**updated_exam, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update exam error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update exam: {str(e)}"
        )

@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Delete an exam (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        if not await db.select_by_id("exams", "exam_id", exam_id):
            raise HTTPException(status_code=404, detail="Exam not found")
        
        # Check for related marks before deleting
        existing_marks = await db.select_all("marks", {"exam_id": exam_id})
        if existing_marks:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete exam: {len(existing_marks)} marks are already associated with it."
            )
            
        await db.delete_by_id("exams", "exam_id", exam_id)
        
        logger.info(f"Exam deleted: {exam_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete exam error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete exam: {str(e)}"
        )