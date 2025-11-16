"""
app/api/v1/endpoints/teachers.py
Fixed Teacher management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from app.models.schemas import (
    TeacherCreate, TeacherUpdate, TeacherResponse, TokenPayload
)
from app.core.security import require_admin, get_current_user, require_teacher
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_data: TeacherCreate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Create a new teacher (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Check if email already exists
        if teacher_data.email:
            existing = await db.select_all("teachers", {"email": teacher_data.email})
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Teacher with this email already exists"
                )
        
        # Convert to dict (now all fields are already strings, no UUID conversion needed)
        teacher_dict = teacher_data.model_dump()
        
        # Insert into database
        new_teacher = await db.insert_one("teachers", teacher_dict)
        
        # Get subject name if subject_id exists
        subject_name = None
        if new_teacher.get("subject_id"):
            subject = await db.select_by_id("subjects", "subject_id", new_teacher["subject_id"])
            if subject:
                subject_name = subject.get("subject_name")
        
        logger.info(f"Teacher created: {new_teacher['teacher_id']}")
        
        return TeacherResponse(**new_teacher, subject_name=subject_name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create teacher error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create teacher: {str(e)}"
        )

@router.get("/", response_model=List[TeacherResponse])
async def get_teachers(
    subject_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get list of teachers with optional filtering
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        filters = {}
        if subject_id:
            filters["subject_id"] = subject_id
        
        result = await db.paginate("teachers", page, page_size, filters, "name")
        
        teachers = []
        for teacher in result["data"]:
            subject_name = None
            if teacher.get("subject_id"):
                subject = await db.select_by_id("subjects", "subject_id", teacher["subject_id"])
                if subject:
                    subject_name = subject.get("subject_name")
            
            teachers.append(TeacherResponse(**teacher, subject_name=subject_name))
        
        return teachers
        
    except Exception as e:
        logger.error(f"Get teachers error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve teachers: {str(e)}"
        )

@router.get("/{teacher_id}", response_model=TeacherResponse)
async def get_teacher(
    teacher_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get teacher by ID
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        teacher = await db.select_by_id("teachers", "teacher_id", teacher_id)
        
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found"
            )
        
        # Get subject name
        subject_name = None
        if teacher.get("subject_id"):
            subject = await db.select_by_id("subjects", "subject_id", teacher["subject_id"])
            if subject:
                subject_name = subject.get("subject_name")
        
        return TeacherResponse(**teacher, subject_name=subject_name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get teacher error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve teacher: {str(e)}"
        )

@router.put("/{teacher_id}", response_model=TeacherResponse)
async def update_teacher(
    teacher_id: str,
    teacher_data: TeacherUpdate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Update teacher information (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        existing = await db.select_by_id("teachers", "teacher_id", teacher_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found"
            )
        
        update_data = teacher_data.model_dump(exclude_unset=True)
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        updated_teacher = await db.update_by_id(
            "teachers",
            "teacher_id",
            teacher_id,
            update_data
        )
        
        # Get subject name
        subject_name = None
        if updated_teacher.get("subject_id"):
            subject = await db.select_by_id("subjects", "subject_id", updated_teacher["subject_id"])
            if subject:
                subject_name = subject.get("subject_name")
        
        logger.info(f"Teacher updated: {teacher_id}")
        
        return TeacherResponse(**updated_teacher, subject_name=subject_name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update teacher error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update teacher: {str(e)}"
        )

@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teacher(
    teacher_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Delete teacher (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        existing = await db.select_by_id("teachers", "teacher_id", teacher_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found"
            )
        
        await db.delete_by_id("teachers", "teacher_id", teacher_id)
        logger.info(f"Teacher deleted: {teacher_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete teacher error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete teacher: {str(e)}"
        )

@router.get("/{teacher_id}/classes")
async def get_teacher_classes(
    teacher_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get classes assigned to a teacher
    """
    supabase = get_supabase_client()
    
    try:
        # Check if teacher exists
        teacher = await SupabaseQueries(supabase).select_by_id("teachers", "teacher_id", teacher_id)
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found"
            )
        
        # Get classes where teacher is class teacher
        response = supabase.table("classes").select("*").eq("teacher_id", teacher_id).execute()
        
        return {
            "teacher_id": teacher_id,
            "teacher_name": teacher["name"],
            "classes": response.data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get teacher classes error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve teacher classes: {str(e)}"
        )

@router.get("/{teacher_id}/schedule")
async def get_teacher_schedule(
    teacher_id: str,
    day: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get teacher's timetable schedule
    """
    supabase = get_supabase_client()
    
    try:
        # Check if teacher exists
        teacher = await SupabaseQueries(supabase).select_by_id("teachers", "teacher_id", teacher_id)
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found"
            )
        
        query = supabase.table("timetable").select(
            "*, classes(class_name, section), subjects(subject_name)"
        ).eq("teacher_id", teacher_id)
        
        if day:
            query = query.eq("day", day)
        
        response = query.order("day").order("period_number").execute()
        
        # Group by day
        schedule = {}
        for entry in response.data:
            day_name = entry["day"]
            if day_name not in schedule:
                schedule[day_name] = []
            
            schedule[day_name].append({
                "period_number": entry["period_number"],
                "start_time": entry["start_time"],
                "end_time": entry["end_time"],
                "class": f"{entry['classes']['class_name']} - {entry['classes']['section']}",
                "subject": entry["subjects"]["subject_name"]
            })
        
        return {
            "teacher_id": teacher_id,
            "teacher_name": teacher["name"],
            "schedule": schedule
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get teacher schedule error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve teacher schedule: {str(e)}"
        )

@router.get("/{teacher_id}/homework")
async def get_teacher_homework(
    teacher_id: str,
    class_id: Optional[str] = None,
    current_user: TokenPayload = Depends(require_teacher)
):
    """
    Get homework assignments created by teacher
    """
    supabase = get_supabase_client()
    
    try:
        query = supabase.table("homework").select(
            "*, classes(class_name, section), subjects(subject_name)"
        ).eq("teacher_id", teacher_id)
        
        if class_id:
            query = query.eq("class_id", class_id)
        
        response = query.order("due_date", desc=True).execute()
        
        return {
            "teacher_id": teacher_id,
            "homework_count": len(response.data),
            "homework": response.data
        }
        
    except Exception as e:
        logger.error(f"Get teacher homework error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve teacher homework: {str(e)}"
        )