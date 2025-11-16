"""
app/api/v1/endpoints/classes.py
Complete Class management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from datetime import date
from app.models.schemas import (
    ClassCreate, ClassResponse, TokenPayload, UserRole
)
from app.core.security import require_admin, get_current_user
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
async def create_class(
    class_data: ClassCreate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Create a new class (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Check if class with same name, section, and academic year exists
        existing = supabase.table("classes").select("*").eq(
            "class_name", class_data.class_name
        ).eq("section", class_data.section).eq(
            "academic_year", class_data.academic_year
        ).execute()
        
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Class {class_data.class_name} - {class_data.section} already exists for academic year {class_data.academic_year}"
            )
        
        # Verify teacher exists if provided
        teacher_name = None
        if class_data.teacher_id:
            teacher = await db.select_by_id("teachers", "teacher_id", class_data.teacher_id)
            if not teacher:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Teacher not found"
                )
            teacher_name = teacher.get("name")
        
        # Create class
        class_dict = class_data.model_dump()
        new_class = await db.insert_one("classes", class_dict)
        
        logger.info(f"Class created: {new_class['class_id']} - {class_data.class_name} {class_data.section}")
        
        return ClassResponse(
            **new_class,
            teacher_name=teacher_name,
            student_count=0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create class error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create class: {str(e)}"
        )

@router.get("/", response_model=List[ClassResponse])
async def get_classes(
    academic_year: Optional[str] = None,
    teacher_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get list of classes with optional filtering
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        filters = {}
        if academic_year:
            filters["academic_year"] = academic_year
        if teacher_id:
            filters["teacher_id"] = teacher_id
        
        result = await db.paginate("classes", page, page_size, filters, "class_name")
        
        classes = []
        for cls in result["data"]:
            # Get teacher name
            teacher_name = None
            if cls.get("teacher_id"):
                teacher = await db.select_by_id("teachers", "teacher_id", cls["teacher_id"])
                if teacher:
                    teacher_name = teacher.get("name")
            
            # Get student count
            students = await db.select_all("students", {"class_id": cls["class_id"]})
            student_count = len(students)
            
            classes.append(ClassResponse(
                **cls,
                teacher_name=teacher_name,
                student_count=student_count
            ))
        
        return classes
        
    except Exception as e:
        logger.error(f"Get classes error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve classes: {str(e)}"
        )

@router.get("/{class_id}", response_model=ClassResponse)
async def get_class(
    class_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get class by ID
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        cls = await db.select_by_id("classes", "class_id", class_id)
        
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        # Get teacher name
        teacher_name = None
        if cls.get("teacher_id"):
            teacher = await db.select_by_id("teachers", "teacher_id", cls["teacher_id"])
            if teacher:
                teacher_name = teacher.get("name")
        
        # Get student count
        students = await db.select_all("students", {"class_id": class_id})
        student_count = len(students)
        
        return ClassResponse(
            **cls,
            teacher_name=teacher_name,
            student_count=student_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get class error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve class: {str(e)}"
        )

@router.put("/{class_id}", response_model=ClassResponse)
async def update_class(
    class_id: str,
    class_name: Optional[str] = None,
    section: Optional[str] = None,
    teacher_id: Optional[str] = None,
    academic_year: Optional[str] = None,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Update class information (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        existing = await db.select_by_id("classes", "class_id", class_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        update_data = {}
        if class_name is not None:
            update_data["class_name"] = class_name
        if section is not None:
            update_data["section"] = section
        if teacher_id is not None:
            # Verify teacher exists
            teacher = await db.select_by_id("teachers", "teacher_id", teacher_id)
            if not teacher:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Teacher not found"
                )
            update_data["teacher_id"] = teacher_id
        if academic_year is not None:
            update_data["academic_year"] = academic_year
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        updated_class = await db.update_by_id("classes", "class_id", class_id, update_data)
        
        # Get teacher name
        teacher_name = None
        if updated_class.get("teacher_id"):
            teacher = await db.select_by_id("teachers", "teacher_id", updated_class["teacher_id"])
            if teacher:
                teacher_name = teacher.get("name")
        
        # Get student count
        students = await db.select_all("students", {"class_id": class_id})
        student_count = len(students)
        
        logger.info(f"Class updated: {class_id}")
        
        return ClassResponse(
            **updated_class,
            teacher_name=teacher_name,
            student_count=student_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update class error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update class: {str(e)}"
        )

@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(
    class_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Delete class (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        existing = await db.select_by_id("classes", "class_id", class_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        # Check if class has students
        students = await db.select_all("students", {"class_id": class_id})
        if students:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete class with {len(students)} enrolled students. Please reassign students first."
            )
        
        await db.delete_by_id("classes", "class_id", class_id)
        logger.info(f"Class deleted: {class_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete class error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete class: {str(e)}"
        )

@router.get("/{class_id}/students")
async def get_class_students(
    class_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get all students in a class
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Verify class exists
        cls = await db.select_by_id("classes", "class_id", class_id)
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        # Get students
        students = await db.select_all("students", {"class_id": class_id})
        
        return {
            "class_id": class_id,
            "class_name": cls["class_name"],
            "section": cls["section"],
            "academic_year": cls["academic_year"],
            "student_count": len(students),
            "students": students
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get class students error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve class students: {str(e)}"
        )

@router.get("/{class_id}/subjects")
async def get_class_subjects(
    class_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get all subjects for a class
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Verify class exists
        cls = await db.select_by_id("classes", "class_id", class_id)
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        # Get subjects
        subjects = await db.select_all("subjects", {"class_id": class_id})
        
        return {
            "class_id": class_id,
            "class_name": cls["class_name"],
            "section": cls["section"],
            "subject_count": len(subjects),
            "subjects": subjects
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get class subjects error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve class subjects: {str(e)}"
        )

@router.get("/{class_id}/timetable")
async def get_class_timetable(
    class_id: str,
    day: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get timetable for a class
    """
    supabase = get_supabase_client()
    
    try:
        # Verify class exists
        cls = await SupabaseQueries(supabase).select_by_id("classes", "class_id", class_id)
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        query = supabase.table("timetable").select(
            "*, subjects(subject_name), teachers(name)"
        ).eq("class_id", class_id)
        
        if day:
            query = query.eq("day", day)
        
        response = query.order("day").order("period_number").execute()
        
        # Group by day
        timetable = {}
        for entry in response.data:
            day_name = entry["day"]
            if day_name not in timetable:
                timetable[day_name] = []
            
            timetable[day_name].append({
                "timetable_id": entry["timetable_id"],
                "period_number": entry["period_number"],
                "start_time": entry["start_time"],
                "end_time": entry["end_time"],
                "subject": entry["subjects"]["subject_name"] if entry.get("subjects") else None,
                "teacher": entry["teachers"]["name"] if entry.get("teachers") else None
            })
        
        return {
            "class_id": class_id,
            "class_name": cls["class_name"],
            "section": cls["section"],
            "timetable": timetable
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get class timetable error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve class timetable: {str(e)}"
        )

@router.get("/{class_id}/attendance/summary")
async def get_class_attendance_summary(
    class_id: str,
    date_param: Optional[str] = Query(None, alias="date"),
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get attendance summary for a class
    """
    supabase = get_supabase_client()
    
    try:
        # Verify class exists
        cls = await SupabaseQueries(supabase).select_by_id("classes", "class_id", class_id)
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        # Get all students in class
        students = await SupabaseQueries(supabase).select_all("students", {"class_id": class_id})
        student_ids = [s["student_id"] for s in students]
        
        if not student_ids:
            return {
                "class_id": class_id,
                "class_name": f"{cls['class_name']} - {cls['section']}",
                "total_students": 0,
                "present": 0,
                "absent": 0,
                "late": 0,
                "attendance_percentage": 0,
                "date": date_param or "All dates"
            }
        
        # Get attendance records
        query = supabase.table("attendance").select("*").in_("student_id", student_ids)
        
        if date_param:
            query = query.eq("date", date_param)
        
        response = query.execute()
        
        # Calculate statistics
        total = len(response.data)
        present = sum(1 for r in response.data if r["status"] == "present")
        absent = sum(1 for r in response.data if r["status"] == "absent")
        late = sum(1 for r in response.data if r["status"] == "late")
        
        attendance_percentage = (present / total * 100) if total > 0 else 0
        
        return {
            "class_id": class_id,
            "class_name": f"{cls['class_name']} - {cls['section']}",
            "total_students": len(students),
            "total_records": total,
            "present": present,
            "absent": absent,
            "late": late,
            "attendance_percentage": round(attendance_percentage, 2),
            "date": date_param or "All dates"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get class attendance summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve attendance summary: {str(e)}"
        )

@router.get("/{class_id}/performance")
async def get_class_performance(
    class_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get overall performance statistics for a class
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Verify class exists
        cls = await db.select_by_id("classes", "class_id", class_id)
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        # Get all students
        students = await db.select_all("students", {"class_id": class_id})
        student_ids = [s["student_id"] for s in students]
        
        if not student_ids:
            return {
                "class_id": class_id,
                "class_name": f"{cls['class_name']} - {cls['section']}",
                "total_students": 0,
                "average_attendance": 0,
                "average_marks": 0
            }
        
        # Calculate attendance percentage
        attendance_records = supabase.table("attendance").select("*").in_(
            "student_id", student_ids
        ).execute()
        
        total_attendance = len(attendance_records.data)
        present_count = sum(1 for a in attendance_records.data if a["status"] == "present")
        avg_attendance = (present_count / total_attendance * 100) if total_attendance > 0 else 0
        
        # Calculate average marks
        marks_records = supabase.table("marks").select(
            "*, exams(max_marks)"
        ).in_("student_id", student_ids).execute()
        
        total_percentage = 0
        for mark in marks_records.data:
            if mark.get("exams") and mark["exams"].get("max_marks"):
                percentage = (mark["marks_scored"] / mark["exams"]["max_marks"]) * 100
                total_percentage += percentage
        
        avg_marks = total_percentage / len(marks_records.data) if marks_records.data else 0
        
        return {
            "class_id": class_id,
            "class_name": f"{cls['class_name']} - {cls['section']}",
            "academic_year": cls["academic_year"],
            "total_students": len(students),
            "attendance": {
                "average_percentage": round(avg_attendance, 2),
                "total_records": total_attendance
            },
            "academic": {
                "average_percentage": round(avg_marks, 2),
                "total_exams": len(marks_records.data)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get class performance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve class performance: {str(e)}"
        )

@router.post("/{class_id}/assign-teacher/{teacher_id}")
async def assign_teacher_to_class(
    class_id: str,
    teacher_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Assign a class teacher (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Verify class exists
        cls = await db.select_by_id("classes", "class_id", class_id)
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        # Verify teacher exists
        teacher = await db.select_by_id("teachers", "teacher_id", teacher_id)
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found"
            )
        
        # Assign teacher
        await db.update_by_id("classes", "class_id", class_id, {"teacher_id": teacher_id})
        
        logger.info(f"Teacher {teacher_id} assigned to class {class_id}")
        
        return {
            "message": "Teacher assigned successfully",
            "class_id": class_id,
            "class_name": f"{cls['class_name']} - {cls['section']}",
            "teacher_id": teacher_id,
            "teacher_name": teacher["name"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Assign teacher error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign teacher: {str(e)}"
        )

@router.delete("/{class_id}/remove-teacher")
async def remove_teacher_from_class(
    class_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Remove class teacher (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Verify class exists
        cls = await db.select_by_id("classes", "class_id", class_id)
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
        
        # Remove teacher
        await db.update_by_id("classes", "class_id", class_id, {"teacher_id": None})
        
        logger.info(f"Teacher removed from class {class_id}")
        
        return {
            "message": "Teacher removed successfully",
            "class_id": class_id,
            "class_name": f"{cls['class_name']} - {cls['section']}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove teacher error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove teacher: {str(e)}"
        )