"""
app/api/v1/endpoints/attendance.py
Attendance tracking endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from datetime import date, datetime
from app.models.schemas import (
    AttendanceCreate, AttendanceBulkCreate, AttendanceResponse,
    AttendanceStatus, TokenPayload
)
from app.core.security import require_teacher, get_current_user
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
async def mark_attendance(
    attendance_data: AttendanceCreate,
    current_user: TokenPayload = Depends(require_teacher)
):
    """
    Mark attendance for a single student (Teacher/Admin)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Check if attendance already exists for this student and date
        existing = supabase.table("attendance").select("*").eq(
            "student_id", attendance_data.student_id
        ).eq("date", str(attendance_data.date)).execute()
        
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attendance already marked for this date"
            )
        
        # Create attendance record
        attendance_dict = attendance_data.model_dump()
        attendance_dict["date"] = str(attendance_dict["date"])
        
        new_attendance = await db.insert_one("attendance", attendance_dict)
        
        # Get student name
        student = await db.select_by_id("students", "student_id", attendance_data.student_id)
        student_name = student.get("name") if student else None
        
        logger.info(f"Attendance marked for student {attendance_data.student_id} on {attendance_data.date}")
        
        return AttendanceResponse(
            **new_attendance,
            student_name=student_name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mark attendance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark attendance"
        )

@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def mark_bulk_attendance(
    bulk_data: AttendanceBulkCreate,
    current_user: TokenPayload = Depends(require_teacher)
):
    """
    Mark attendance for multiple students at once (Teacher/Admin)
    Useful for marking entire class attendance
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Get all students in the class
        students = await db.select_all("students", {"class_id": bulk_data.class_id})
        student_ids = {s["student_id"] for s in students}
        
        # Validate all student_ids belong to the class
        for record in bulk_data.attendance_records:
            if record.get("student_id") not in student_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Student {record.get('student_id')} not in class {bulk_data.class_id}"
                )
        
        # Check if attendance already exists for this class and date
        existing = supabase.table("attendance").select(
            "student_id"
        ).in_(
            "student_id", [r["student_id"] for r in bulk_data.attendance_records]
        ).eq("date", str(bulk_data.date)).execute()
        
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attendance already marked for some students on this date"
            )
        
        # Prepare bulk insert data
        attendance_records = []
        for record in bulk_data.attendance_records:
            attendance_records.append({
                "student_id": record["student_id"],
                "date": str(bulk_data.date),
                "status": record["status"],
                "remarks": record.get("remarks")
            })
        
        # Bulk insert
        result = await db.insert_many("attendance", attendance_records)
        
        logger.info(f"Bulk attendance marked for class {bulk_data.class_id} on {bulk_data.date}")
        
        return {
            "message": f"Attendance marked for {len(result)} students",
            "class_id": bulk_data.class_id,
            "date": bulk_data.date,
            "records_created": len(result)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk attendance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark bulk attendance"
        )

@router.get("/", response_model=List[AttendanceResponse])
async def get_attendance(
    class_id: Optional[str] = None,
    student_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[AttendanceStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get attendance records with filters
    """
    supabase = get_supabase_client()
    
    try:
        # Build query with filters
        query = supabase.table("attendance").select(
            "*, students(name, class_id)"
        )
        
        if student_id:
            query = query.eq("student_id", student_id)
        
        if class_id:
            # Filter by class through students table
            students = await SupabaseQueries(supabase).select_all(
                "students", {"class_id": class_id}
            )
            student_ids = [s["student_id"] for s in students]
            if student_ids:
                query = query.in_("student_id", student_ids)
        
        if start_date:
            query = query.gte("date", str(start_date))
        
        if end_date:
            query = query.lte("date", str(end_date))
        
        if status:
            query = query.eq("status", status.value)
        
        # Pagination
        start = (page - 1) * page_size
        end = start + page_size - 1
        
        response = query.order("date", desc=True).range(start, end).execute()
        
        # Format response
        attendance_list = []
        for record in response.data:
            attendance_list.append(AttendanceResponse(
                attendance_id=record["attendance_id"],
                student_id=record["student_id"],
                date=record["date"],
                status=AttendanceStatus(record["status"]),
                remarks=record.get("remarks"),
                student_name=record["students"]["name"] if record.get("students") else None,
                created_at=record["created_at"]
            ))
        
        return attendance_list
        
    except Exception as e:
        logger.error(f"Get attendance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve attendance"
        )

@router.get("/statistics")
async def get_attendance_statistics(
    class_id: Optional[str] = None,
    student_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get attendance statistics
    """
    supabase = get_supabase_client()
    
    try:
        # Build query
        query = supabase.table("attendance").select("*")
        
        if student_id:
            query = query.eq("student_id", student_id)
        
        if class_id:
            students = await SupabaseQueries(supabase).select_all(
                "students", {"class_id": class_id}
            )
            student_ids = [s["student_id"] for s in students]
            if student_ids:
                query = query.in_("student_id", student_ids)
        
        if start_date:
            query = query.gte("date", str(start_date))
        
        if end_date:
            query = query.lte("date", str(end_date))
        
        response = query.execute()
        records = response.data
        
        # Calculate statistics
        total = len(records)
        present = sum(1 for r in records if r["status"] == "present")
        absent = sum(1 for r in records if r["status"] == "absent")
        late = sum(1 for r in records if r["status"] == "late")
        excused = sum(1 for r in records if r["status"] == "excused")
        
        return {
            "total_records": total,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "attendance_percentage": round((present / total * 100), 2) if total > 0 else 0,
            "filters": {
                "class_id": class_id,
                "student_id": student_id,
                "start_date": str(start_date) if start_date else None,
                "end_date": str(end_date) if end_date else None
            }
        }
        
    except Exception as e:
        logger.error(f"Get attendance statistics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve attendance statistics"
        )

@router.put("/{attendance_id}", response_model=AttendanceResponse)
async def update_attendance(
    attendance_id: str,
    status: AttendanceStatus,
    remarks: Optional[str] = None,
    current_user: TokenPayload = Depends(require_teacher)
):
    """
    Update attendance record (Teacher/Admin)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Check if attendance exists
        existing = await db.select_by_id("attendance", "attendance_id", attendance_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attendance record not found"
            )
        
        # Update attendance
        update_data = {
            "status": status.value,
            "remarks": remarks
        }
        
        updated = await db.update_by_id(
            "attendance",
            "attendance_id",
            attendance_id,
            update_data
        )
        
        # Get student name
        student = await db.select_by_id("students", "student_id", updated["student_id"])
        student_name = student.get("name") if student else None
        
        logger.info(f"Attendance updated: {attendance_id}")
        
        return AttendanceResponse(
            **updated,
            student_name=student_name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update attendance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update attendance"
        )

@router.delete("/{attendance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attendance(
    attendance_id: str,
    current_user: TokenPayload = Depends(require_teacher)
):
    """
    Delete attendance record (Teacher/Admin)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Check if attendance exists
        existing = await db.select_by_id("attendance", "attendance_id", attendance_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attendance record not found"
            )
        
        await db.delete_by_id("attendance", "attendance_id", attendance_id)
        
        logger.info(f"Attendance deleted: {attendance_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete attendance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete attendance"
        )

@router.get("/defaulters")
async def get_attendance_defaulters(
    class_id: Optional[str] = None,
    threshold: int = Query(75, ge=0, le=100, description="Minimum attendance percentage"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: TokenPayload = Depends(require_teacher)
):
    """
    Get list of students with attendance below threshold (Teacher/Admin)
    """
    supabase = get_supabase_client()
    
    try:
        # Get students
        filters = {}
        if class_id:
            filters["class_id"] = class_id
        
        students = await SupabaseQueries(supabase).select_all("students", filters)
        
        defaulters = []
        
        for student in students:
            # Get attendance for this student
            query = supabase.table("attendance").select("*").eq(
                "student_id", student["student_id"]
            )
            
            if start_date:
                query = query.gte("date", str(start_date))
            if end_date:
                query = query.lte("date", str(end_date))
            
            attendance_records = query.execute().data
            
            if attendance_records:
                total = len(attendance_records)
                present = sum(1 for r in attendance_records if r["status"] == "present")
                percentage = round((present / total * 100), 2)
                
                if percentage < threshold:
                    defaulters.append({
                        "student_id": student["student_id"],
                        "name": student["name"],
                        "class_id": student.get("class_id"),
                        "total_days": total,
                        "present_days": present,
                        "attendance_percentage": percentage
                    })
        
        # Sort by attendance percentage (lowest first)
        defaulters.sort(key=lambda x: x["attendance_percentage"])
        
        return {
            "threshold": threshold,
            "total_defaulters": len(defaulters),
            "defaulters": defaulters
        }
        
    except Exception as e:
        logger.error(f"Get attendance defaulters error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve attendance defaulters"
        )