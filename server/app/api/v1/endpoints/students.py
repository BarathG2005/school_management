from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from app.models.schemas import (StudentCreate, StudentUpdate, StudentResponse, PaginationParams, TokenPayload, UserRole)
from app.core.security import get_current_user, require_admin, require_teacher, hash_password
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_data: StudentCreate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Admin creates a new student.
    - Creates user in `users` table with DOB as initial password (hashed)
    - Creates student profile in `students` table
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)

    try:
         
        existing = supabase.table("users").select("*").eq("email", student_data.email).execute()
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

       
        if not student_data.dob:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Date of Birth (DOB) is required to set initial password"
            )
        
        hashed_password = hash_password(str(student_data.dob.isoformat()))

        
        user_dict = {
            "email": student_data.email,
            "password_hash": hashed_password,
            "role": "student",
            "is_active": True
        }
        new_user = await db.insert_one("users", user_dict)

     
        student_dict = student_data.model_dump()
        
       
        if student_dict.get("dob"):
            student_dict["dob"] = student_dict["dob"].isoformat()
            
        
        if student_dict.get("class_id"):
            student_dict["class_id"] = str(student_dict["class_id"])
            
        
        student_dict["user_id"] = str(new_user["user_id"])
        

        new_student = await db.insert_one("students", student_dict)  

        
        class_name = None
        if new_student.get("class_id"):
            class_data = await db.select_by_id("classes", "class_id", new_student["class_id"])
            if class_data:
                class_name = class_data.get("class_name")

        logger.info(f"Student created: {new_student['student_id']}")

        
        return StudentResponse(
            **new_student,
            class_name=class_name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create student error: {e}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create student: {str(e)}"
        )
# # //////////////////////
@router.get("/", response_model=List[StudentResponse])
async def get_students(
    class_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: TokenPayload = Depends(get_current_user)
):
    
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        filters = {}
        
        
        if current_user.role == UserRole.STUDENT:
            
            filters["user_id"] = current_user.sub
        elif current_user.role == UserRole.PARENT:
            
            parent_data = await db.select_all(
                "parent_student",
                {"parent_id": current_user.sub}
            )
            student_ids = [p["student_id"] for p in parent_data]
             
            filters = None   
        elif class_id:
            filters["class_id"] = class_id
        
      
        result = await db.paginate("students", page, page_size, filters, "name")
        
        # Enrich with class names
        students = []
        for student in result["data"]:
            class_name = None
            if student.get("class_id"):
                class_data = await db.select_by_id("classes", "class_id", student["class_id"])
                if class_data:
                    class_name = f"{class_data['class_name']} - {class_data['section']}"
            
            students.append(StudentResponse(**student, class_name=class_name))
        
        return students
        
    except Exception as e:
        logger.error(f"Get students error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve students"
        )

@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(
    student_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get student by ID
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        student = await db.select_by_id("students", "student_id", student_id)
        
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found"
            )
        
        # Authorization check
        if current_user.role == UserRole.STUDENT:
            if student.get("user_id") != current_user.sub:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
        
        # Get class name
        class_name = None
        if student.get("class_id"):
            class_data = await db.select_by_id("classes", "class_id", student["class_id"])
            if class_data:
                class_name = f"{class_data['class_name']} - {class_data['section']}"
        
        return StudentResponse(**student, class_name=class_name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get student error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve student"
        )

@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: str,
    student_data: StudentUpdate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Update student information (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Check if student exists
        existing = await db.select_by_id("students", "student_id", student_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found"
            )
        
        # Update only provided fields
        update_data = student_data.model_dump(exclude_unset=True)
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        updated_student = await db.update_by_id(
            "students",
            "student_id",
            student_id,
            update_data
        )
        
        # Get class name
        class_name = None
        if updated_student.get("class_id"):
            class_data = await db.select_by_id("classes", "class_id", updated_student["class_id"])
            if class_data:
                class_name = f"{class_data['class_name']} - {class_data['section']}"
        
        logger.info(f"Student updated: {student_id}")
        
        return StudentResponse(**updated_student, class_name=class_name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update student error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update student"
        )

@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(
    student_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Delete student (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Check if student exists
        existing = await db.select_by_id("students", "student_id", student_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found"
            )
        
        await db.delete_by_id("students", "student_id", student_id)
        
        logger.info(f"Student deleted: {student_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete student error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete student"
        )

@router.get("/{student_id}/attendance")
async def get_student_attendance(
    student_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get attendance records for a student
    """
    supabase = get_supabase_client()
    
    try:
        # Authorization check
        if current_user.role == UserRole.STUDENT:
            student = await SupabaseQueries(supabase).select_by_id(
                "students", "student_id", student_id
            )
            if student.get("user_id") != current_user.sub:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
        
        query = supabase.table("attendance").select("*").eq("student_id", student_id)
        
        if start_date:
            query = query.gte("date", start_date)
        if end_date:
            query = query.lte("date", end_date)
        
        response = query.order("date", desc=True).execute()
        
        # Calculate statistics
        total = len(response.data)
        present = sum(1 for r in response.data if r["status"] == "present")
        absent = sum(1 for r in response.data if r["status"] == "absent")
        
        return {
            "student_id": student_id,
            "records": response.data,
            "statistics": {
                "total_days": total,
                "present": present,
                "absent": absent,
                "attendance_percentage": round((present / total * 100), 2) if total > 0 else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get student attendance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve attendance"
        )

@router.get("/{student_id}/marks")
async def get_student_marks(
    student_id: str,
    exam_id: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get marks/grades for a student
    """
    supabase = get_supabase_client()
    
    try:
        # Authorization check
        if current_user.role == UserRole.STUDENT:
            student = await SupabaseQueries(supabase).select_by_id(
                "students", "student_id", student_id
            )
            if student.get("user_id") != current_user.sub:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
        
        query = supabase.table("marks").select(
            "*, exams(exam_name, max_marks, date, subjects(subject_name))"
        ).eq("student_id", student_id)
        
        if exam_id:
            query = query.eq("exam_id", exam_id)
        
        response = query.execute()
        
        # Calculate overall performance
        marks_data = response.data
        total_marks = sum(m["marks_scored"] for m in marks_data)
        total_max = sum(m["exams"]["max_marks"] for m in marks_data)
        
        return {
            "student_id": student_id,
            "marks": marks_data,
            "overall_performance": {
                "total_marks_scored": total_marks,
                "total_max_marks": total_max,
                "percentage": round((total_marks / total_max * 100), 2) if total_max > 0 else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get student marks error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve marks"
        )