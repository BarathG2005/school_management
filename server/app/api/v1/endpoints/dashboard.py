"""
app/api/v1/endpoints/dashboard.py
Dashboard statistics endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends
from datetime import date, timedelta
from app.models.schemas import TokenPayload, UserRole
from app.core.security import get_current_user
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/admin")
async def get_admin_dashboard(
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Admin dashboard statistics
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Total counts
        total_students = len(await db.select_all("students", {}))
        total_teachers = len(await db.select_all("teachers", {}))
        total_classes = len(await db.select_all("classes", {}))
        total_parents = len(await db.select_all("parents", {}))
        
        # Today's attendance
        today = date.today()
        today_attendance = supabase.table("attendance").select("*").eq("date", str(today)).execute()
        present_today = sum(1 for a in today_attendance.data if a["status"] == "present")
        total_today = len(today_attendance.data)
        attendance_percentage = (present_today / total_today * 100) if total_today > 0 else 0
        
        # Upcoming exams (next 7 days)
        next_week = date.today() + timedelta(days=7)
        upcoming_exams = supabase.table("exams").select("*").gte(
            "date", str(today)
        ).lte("date", str(next_week)).execute()
        
        # Recent announcements (last 5)
        recent_announcements = supabase.table("announcements").select(
            "*, teachers(name)"
        ).order("date", desc=True).limit(5).execute()
        
        # Fee collection status
        fees = await db.select_all("fees", {})
        total_expected = sum(f["amount"] for f in fees)
        total_collected = sum(f.get("amount_paid", 0) for f in fees)
        collection_percentage = (total_collected / total_expected * 100) if total_expected > 0 else 0
        
        # Pending leave requests
        pending_leaves = supabase.table("leave_requests").select("*").eq("status", "pending").execute()
        
        return {
            "overview": {
                "total_students": total_students,
                "total_teachers": total_teachers,
                "total_classes": total_classes,
                "total_parents": total_parents
            },
            "attendance_today": {
                "total": total_today,
                "present": present_today,
                "percentage": round(attendance_percentage, 2)
            },
            "upcoming_exams": {
                "count": len(upcoming_exams.data),
                "exams": upcoming_exams.data
            },
            "recent_announcements": recent_announcements.data,
            "fee_collection": {
                "total_expected": total_expected,
                "total_collected": total_collected,
                "percentage": round(collection_percentage, 2),
                "pending": total_expected - total_collected
            },
            "pending_leave_requests": len(pending_leaves.data),
            "quick_actions": [
                {"label": "Mark Attendance", "route": "/attendance/bulk"},
                {"label": "Create Announcement", "route": "/announcements"},
                {"label": "Add Student", "route": "/students"},
                {"label": "Generate Reports", "route": "/reports"}
            ]
        }
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )

@router.get("/teacher")
async def get_teacher_dashboard(
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Teacher dashboard statistics
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Get teacher info
        teacher_data = await db.select_all("teachers", {"user_id": current_user.sub})
        if not teacher_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher profile not found"
            )
        
        teacher_id = teacher_data[0]["teacher_id"]
        
        # My classes
        my_classes = await db.select_all("classes", {"teacher_id": teacher_id})
        
        # Today's schedule
        today = date.today()
        day_name = today.strftime("%A")
        today_schedule = supabase.table("timetable").select(
            "*, subjects(subject_name), classes(class_name, section)"
        ).eq("teacher_id", teacher_id).eq("day", day_name).order("period_number").execute()
        
        # Pending homework submissions
        my_homework = supabase.table("homework").select("*").eq("teacher_id", teacher_id).execute()
        total_homework = len(my_homework.data)
        
        pending_submissions = 0
        for hw in my_homework.data:
            submissions = supabase.table("submissions").select("*").eq("hw_id", hw["hw_id"]).execute()
            students = await db.select_all("students", {"class_id": hw["class_id"]})
            pending_submissions += len(students) - len(submissions.data)
        
        # Recent exams
        recent_exams = supabase.table("exams").select(
            "*, classes(class_name, section), subjects(subject_name)"
        ).order("date", desc=True).limit(5).execute()
        
        return {
            "teacher_info": {
                "name": teacher_data[0]["name"],
                "subject": teacher_data[0].get("subject_id")
            },
            "my_classes": {
                "count": len(my_classes),
                "classes": my_classes
            },
            "today_schedule": {
                "day": day_name,
                "periods": today_schedule.data
            },
            "homework_status": {
                "total_assignments": total_homework,
                "pending_submissions": pending_submissions
            },
            "recent_exams": recent_exams.data,
            "quick_actions": [
                {"label": "Mark Attendance", "route": "/attendance/bulk"},
                {"label": "Create Homework", "route": "/homework"},
                {"label": "Enter Marks", "route": "/exams/marks"},
                {"label": "Make Announcement", "route": "/announcements"}
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Teacher dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )

@router.get("/student")
async def get_student_dashboard(
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Student dashboard
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Get student info
        student_data = await db.select_all("students", {"user_id": current_user.sub})
        if not student_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student profile not found"
            )
        
        student = student_data[0]
        student_id = student["student_id"]
        
        # My attendance
        attendance = supabase.table("attendance").select("*").eq("student_id", student_id).execute()
        total_days = len(attendance.data)
        present_days = sum(1 for a in attendance.data if a["status"] == "present")
        attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0
        
        # My timetable (today)
        if student.get("class_id"):
            today = date.today()
            day_name = today.strftime("%A")
            timetable = supabase.table("timetable").select(
                "*, subjects(subject_name), teachers(name)"
            ).eq("class_id", student["class_id"]).eq("day", day_name).order("period_number").execute()
        else:
            timetable = {"data": []}
        
        # Upcoming exams
        today = date.today()
        next_month = today + timedelta(days=30)
        upcoming_exams = supabase.table("exams").select(
            "*, subjects(subject_name)"
        ).eq("class_id", student.get("class_id")).gte(
            "date", str(today)
        ).lte("date", str(next_month)).order("date").execute()
        
        # Pending homework
        pending_homework = supabase.table("homework").select(
            "*, subjects(subject_name)"
        ).eq("class_id", student.get("class_id")).gte("due_date", str(today)).execute()
        
        # Filter out submitted homework
        my_submissions = supabase.table("submissions").select("hw_id").eq("student_id", student_id).execute()
        submitted_ids = {s["hw_id"] for s in my_submissions.data}
        pending = [hw for hw in pending_homework.data if hw["hw_id"] not in submitted_ids]
        
        # Recent marks
        recent_marks = supabase.table("marks").select(
            "*, exams(exam_name, max_marks, subjects(subject_name))"
        ).eq("student_id", student_id).order("created_at", desc=True).limit(5).execute()
        
        # Recent announcements
        announcements = supabase.table("announcements").select(
            "*, teachers(name)"
        ).order("date", desc=True).limit(5).execute()
        
        return {
            "student_info": {
                "name": student["name"],
                "class": student.get("class_id")
            },
            "attendance": {
                "total_days": total_days,
                "present_days": present_days,
                "percentage": round(attendance_percentage, 2)
            },
            "today_timetable": {
                "day": date.today().strftime("%A"),
                "periods": timetable.data
            },
            "upcoming_exams": {
                "count": len(upcoming_exams.data),
                "exams": upcoming_exams.data
            },
            "pending_homework": {
                "count": len(pending),
                "homework": pending
            },
            "recent_marks": recent_marks.data,
            "announcements": announcements.data,
            "quick_actions": [
                {"label": "View Timetable", "route": "/timetable"},
                {"label": "Submit Homework", "route": "/homework"},
                {"label": "View Marks", "route": "/marks"},
                {"label": "Check Attendance", "route": "/attendance"}
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Student dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )

@router.get("/parent")
async def get_parent_dashboard(
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Parent dashboard
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Get parent info
        parent_data = await db.select_all("parents", {"user_id": current_user.sub})
        if not parent_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent profile not found"
            )
        
        parent_id = parent_data[0]["parent_id"]
        
        # Get children
        children_response = supabase.table("parent_student").select(
            "*, students(*, classes(class_name, section))"
        ).eq("parent_id", parent_id).execute()
        
        children_summary = []
        for child_record in children_response.data:
            child = child_record["students"]
            student_id = child["student_id"]
            
            # Get attendance
            attendance = supabase.table("attendance").select("*").eq("student_id", student_id).execute()
            total_days = len(attendance.data)
            present_days = sum(1 for a in attendance.data if a["status"] == "present")
            attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0
            
            # Get recent marks
            marks = supabase.table("marks").select(
                "*, exams(max_marks)"
            ).eq("student_id", student_id).execute()
            
            total_percentage = 0
            for mark in marks.data:
                percentage = (mark["marks_scored"] / mark["exams"]["max_marks"]) * 100
                total_percentage += percentage
            avg_percentage = total_percentage / len(marks.data) if marks.data else 0
            
            children_summary.append({
                "student_id": student_id,
                "name": child["name"],
                "class": f"{child['classes']['class_name']} - {child['classes']['section']}" if child.get("classes") else None,
                "attendance_percentage": round(attendance_percentage, 2),
                "average_marks": round(avg_percentage, 2)
            })
        
        # Recent announcements
        announcements = supabase.table("announcements").select(
            "*, teachers(name)"
        ).in_("target_audience", ["all", "parents"]).order("date", desc=True).limit(5).execute()
        
        return {
            "parent_info": {
                "name": parent_data[0]["name"],
                "email": parent_data[0]["email"]
            },
            "children": {
                "count": len(children_summary),
                "summary": children_summary
            },
            "announcements": announcements.data,
            "quick_actions": [
                {"label": "View Child Performance", "route": "/parents/children/performance"},
                {"label": "Check Attendance", "route": "/attendance"},
                {"label": "View Fees", "route": "/fees"},
                {"label": "Submit Leave Request", "route": "/leave-requests"}
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Parent dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )